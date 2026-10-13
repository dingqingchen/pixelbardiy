"""RAM-only HPL2 transport for the locally commissioned display MCU.

The USB bridge ACK is transport evidence, not a firmware readback. A matching
local installation record is required; the stock 1.3.7 version alone is unsafe.
There is one outstanding request, one active frame and one replaceable target.
"""
from __future__ import annotations
import binascii
from collections import deque
import json
import logging
from pathlib import Path
import secrets
import struct
import time
from .device import HaloLink
from . import vendor_core as core
from . import ram_codec

CANDIDATE_SHA = 'fe18bc92afd790cd2f2248b98091033f8d8d76cac674b60540cbf5c644f389ae'
ACQUIRE, HEARTBEAT, BEGIN, DATA, RELEASE = range(1, 6)


def body(op, sid, frame=0, index=0, data=b''):
    if op not in range(1, 6) or not 0 < sid <= 0xffffffff:
        raise ValueError('Invalid HPL2 session')
    if not 0 <= frame <= 65535 or not 0 <= index <= 255 or len(data) > 37:
        raise ValueError('Invalid HPL2 fragment')
    if op != DATA and data:
        raise ValueError('Unexpected control data')
    return b'HPL2' + bytes([op]) + struct.pack('>IHB', sid, frame, index) + bytes([len(data)]) + data


def fragments(sid, number, pixels):
    if len(pixels) != 1024:
        raise ValueError('Expected 256 x 32 packed pixels')
    raw = pixels + binascii.crc_hqx(pixels, 0).to_bytes(2, 'big')
    return [body(BEGIN, sid, number)] + [
        body(DATA, sid, number, i, raw[offset:offset+37])
        for i, offset in enumerate(range(0, len(raw), 37))]


def validate_installation(path: Path, devices):
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise core.HaloError('缺少本机 MCU 直绘验证记录，已停止连接；不会退回图片上传。') from exc
    if len(devices) != 1:
        raise core.HaloError('请仅连接一台已验证的 Halo PixelBar')
    device = devices[0]
    if (record.get('candidate_sha256') not in (CANDIDATE_SHA, ram_codec.FIRMWARE_SHA) or
            record.get('graphics_visually_confirmed') is not True or
            record.get('serial') != device.serial_number or
            record.get('hid_path', '').casefold() != device.path.decode().casefold()):
        raise core.HaloError('音响与本机 MCU 验证记录不一致，RAM 直绘未启用。')
    return record


def restore_clock(link, color, *, clock=time.monotonic, sleep=time.sleep):
    """Run only AFTER release/lease expiry; verify main-controller mode settles.

    Clock selection during a lease can be suppressed at the display MCU while
    the main controller later replays stale DIY text. Retry a rebound and require
    2.5 seconds of stable clock selection before allowing another engine to run.
    """
    deadline = clock() + 7.0
    observations = []
    while clock() < deadline:
        link.native_clock(color)
        stable_since = clock()
        for delay in (.35, .65, 1.5):
            sleep(delay)
            observed = link.query(0xEE)
            observations.append(observed.hex())
            if len(observed) < 8 or observed[5:8] != b'\x01\x00\x00':
                break
        else:
            if clock() - stable_since >= 2.49:
                logging.info('Stock clock restored and stable: %s', observations)
                return observations
    raise core.HaloError('原厂时钟状态未稳定；请退出其他控制音响的软件后重试。')


class RamDisplay(HaloLink):
    def __init__(self, installation: Path):
        super().__init__(allow_resource_upload=True)
        self.installation = installation
        self.authorized = False
        self.sid = 0
        self.owned = False
        self.frame_number = 0
        self.packets = deque()
        self.request = None
        self.current = None
        self.target = None
        self.committed = None
        self.frame_seconds = 0.0
        self.started = 0.0
        self.next_heartbeat = 0.0
        self.frames_sent = 0
        self.restore_color = '#8DF5B4'
        self.last_usb_write = 0.0
        self.last_usb_command = None
        self.palette = None
        self.offered_color = None
        self.color_changed_at = 0.0
        self.target_time = self.current_time = 0.0
        self.supersede = False
        self.frames_dropped = 0
        self.frame_age = 0.0
        self.palette_seconds = 0.0
        self.codec_enabled = False
        self.committed_number = 0
        self.target_animation = 0
        self.frame_codec = 'raw'
        self.frame_bytes = 1024
        self.frame_packets = 29
        self.current_encoding = ('raw', 1024, 29)

    def _write(self, packet):
        command = packet[3]
        # A hard allow-list also prevents accidental use of inherited stock
        # image upload, text, audio-volume or firmware-upgrade methods.
        if command not in (0x17, 0x66, 0x6A, 0x6B, 0xEE, 0xEF, 0xC6):
            raise core.HaloError(f'RAM 通道禁止命令 0x{command:02X}')
        if command == 0xEF and self.owned:
            raise core.HaloError('必须先释放 RAM 显示权才能更改原厂屏幕设置')
        if command == 0x17:
            payload = packet[6:6+int.from_bytes(packet[4:6], 'big')]
            if (not self.authorized or len(payload) < 17 or
                    payload[:8] != b'\x00\x02\xff\xffHPL2' or
                    payload[8] not in range(1, 8 if self.codec_enabled else 6) or len(payload) != 17+payload[16]):
                raise core.HaloError('已阻止非 HPL2 RAM 数据包；原图像资源写入不可用。')
        # The bridge occasionally rejects a lighting report immediately next
        # to a DATA report. Keep a small separation, and retry only idempotent
        # light settings. Never blindly replay a RAM fragment or control ACK.
        if command == 0x6B or self.last_usb_command == 0x6B:
            gap = .007-(time.monotonic()-self.last_usb_write)
            if gap > 0: time.sleep(gap)
        for attempt in range(3 if command == 0x6B else 1):
            try:
                super()._write(packet)
                self.last_usb_write = time.monotonic(); self.last_usb_command = command
                return
            except core.HaloError:
                if command != 0x6B or attempt == 2: raise
                time.sleep(.008*(attempt+1))

    def connect(self, color=None):
        record = validate_installation(self.installation, core.enumerate_halo_devices())
        self.codec_enabled = record['candidate_sha256'] == ram_codec.FIRMWARE_SHA
        info = super().connect()
        try:
            if self.query(0xC6) != b'\x01\x03\x07':
                raise core.HaloError('固件版本已改变；需重新验证 RAM 协议。')
            self.authorized = True
            # A previous crashed process may still own its two-second lease.
            time.sleep(2.2)
            screen = self.query(0xEE)
            if len(screen) < 8:
                raise core.HaloError('未知屏幕状态，未开始直绘。')
            self.restore_color = '#' + screen[1:4].hex()
            self.screen_color(color or self.restore_color)
            restore_clock(self, color or self.restore_color)
            self.sid = secrets.randbits(32) or 1
            self.frame_number = 0
            # Mark possibly-owned BEFORE sending, even if the reply gets lost.
            self.owned = True
            self._control(body(ACQUIRE, self.sid), 3)
            self.next_heartbeat = time.monotonic() + .5
            self.committed = None
            self.committed_number = 0
            logging.info('HPL2 acquired sid=%08x', self.sid)
            return info
        except Exception:
            self.shutdown()
            raise

    def _control(self, request, expected):
        ack = self.query(0x17, b'\x00\x02\xff\xff' + request, timeout=1.5)
        self._check_ack(ack, expected)

    @staticmethod
    def _check_ack(ack, expected):
        # Fragment ACK echoes the reserved sequence; completion/release has
        # only a status word. Both forms are recorded in the live smoke trace.
        wanted = b'\x00\x05' if expected == 5 else b'\x00\x03\xff\xff'
        if ack != wanted:
            raise core.HaloError(f'HPL2 响应异常：{ack.hex()}')

    @property
    def busy(self):
        return bool(self.palette or self.current or self.request is not None or self.packets)

    @property
    def ready_for_lights(self):
        return self.owned and self.palette is None and self.request is None

    @property
    def native_animation(self):
        return self.codec_enabled

    def offer(self, frame, color, *, urgent=False, animation=0):
        if len(frame.pixels) != 1024:
            raise ValueError('Invalid pixel frame')
        # Palette handoffs leave this target replaceable; do not freeze a lyric
        # before releasing/reacquiring the lease. Ordinary clock/animation ticks
        # finish atomically; a newer lyric or selected theme may supersede them.
        now = time.monotonic()
        if color != self.offered_color:
            self.offered_color = color; self.color_changed_at = now
        self.target = (frame, color)
        self.target_animation = animation if self.codec_enabled else 0
        self.target_time = now
        if self.current and self.target != self.current and urgent:
            self.supersede = True
        elif self.target == self.current:
            self.supersede = False

    def _palette_tick(self, now, send):
        """Coalesced, nonblocking colour handoff; media keeps polling throughout.

        The clock fallback was stabilized at connect. A theme change does not
        introduce native text, so a colour/mode readback suffices here. The full
        2.5-second stable-clock check remains mandatory at connect and shutdown.
        """
        state = self.palette
        if self.request is not None:
            ack = self._pixel_query(state['command'], state['payload'])
            if ack is None: return
            self.request = None
            if state['phase'] == 'release':
                self._check_ack(ack, 5); self.owned = False
                self.committed = None; state['phase'] = 'color'
            elif state['phase'] == 'verify':
                expected_color = bytes(core.parse_color(state['color']))
                if len(ack) < 8 or ack[5:8] != b'\x01\x00\x00' or ack[1:4] != expected_color:
                    state['retries'] += 1
                    if state['retries'] >= 3:
                        raise core.HaloError('主题换色后屏幕状态未确认')
                    state['phase'] = 'color'; self.pixel_color = None
                else:
                    state['phase'] = 'acquire'
            elif state['phase'] == 'acquire':
                self._check_ack(ack, 3); self.frame_number = 0
                self.next_heartbeat = now+.5
                self.palette_seconds = now-state['started']
                logging.info('HPL2 palette ready color=%s seconds=%.3f', state['color'], self.palette_seconds)
                self.palette = None
                return  # Give the engine another poll/render before freezing a frame.
        if not send: return
        wanted = self.target[1] if self.target else self.offered_color or self.pixel_color
        if state['phase'] in ('clock', 'verify', 'acquire') and wanted != state.get('color'):
            state['phase'] = 'color'
        phase = state['phase']
        if phase == 'color':
            # Only the latest colour survives a rapid series of theme clicks.
            if now < self.color_changed_at+.18: return
            self.screen_color(wanted)
            state.update(color=wanted, phase='clock', due=now+.03)
            return
        if phase == 'clock':
            if now < state['due']: return
            self.native_clock(state['color'])
            state.update(phase='verify', due=now+.1)
            return
        if phase == 'verify':
            if now < state['due']: return
            command, payload = 0xEE, b''
        else:
            if phase == 'acquire':
                self.sid = secrets.randbits(32) or 1
                # Conservatively assume owned even if the reply is lost.
                self.owned = True
            command = 0x17
            payload = b'\x00\x02\xff\xff'+body(ACQUIRE if phase == 'acquire' else RELEASE, self.sid)
        state.update(command=command, payload=payload)
        self.request = payload
        self._pixel_query(command, payload)

    def tick(self, now, *, send=True):
        if self.palette is not None:
            self._palette_tick(now, send)
            return
        if not self.owned:
            return
        if self.request is not None:
            ack = self._pixel_query(0x17, b'\x00\x02\xff\xff' + self.request)
            if ack is None:
                return
            last = self.request[4] in (DATA, ram_codec.EXT_DATA) and not self.packets
            self._check_ack(ack, 5 if last else 3)
            self.request = None
            self.next_heartbeat = now + .5
            if last:
                self.committed = self.current
                self.committed_number = self.frame_number
                self.current = None
                self.frame_seconds = now-self.started
                self.frame_age = now-self.current_time
                self.frame_codec, self.frame_bytes, self.frame_packets = self.current_encoding
                self.frames_sent += 1
                logging.info('HPL2 frame=%d text=%r seconds=%.3f age=%.3f codec=%s bytes=%d packets=%d',
                             self.frame_number, self.committed[0].text, self.frame_seconds, self.frame_age,
                             self.frame_codec, self.frame_bytes, self.frame_packets)
        if not send:
            return
        if self.supersede and self.current and self.packets:
            # BEGIN(N+1) resets only the RAM staging buffer. Never interrupt a
            # HID request, reuse an ID, or write an incomplete framebuffer.
            logging.info('HPL2 superseded frame=%d text=%r', self.frame_number, self.current[0].text)
            self.current = None; self.packets.clear(); self.frames_dropped += 1
        self.supersede = False
        if not self.packets and self.target is not None and self.target != self.committed:
            if self.target[1] != self.pixel_color or self.frame_number == 65535:
                self.current = None
                self.palette = dict(phase='release', started=now, retries=0)
                self._palette_tick(now, True)
                return
            self.current, self.target = self.target, None
            self.current_time = self.target_time
            self.frame_number += 1
            if self.codec_enabled:
                base = self.committed[0].pixels if self.committed and self.frame_number % 64 else None
                encoded = ram_codec.encode(self.current[0].pixels, base, self.committed_number, self.target_animation)
                outgoing = ram_codec.packets(self.sid, self.frame_number, encoded)
                self.current_encoding = (('raw', 'rle', 'xor-rle')[encoded.codec], len(encoded.data), len(outgoing))
            else:
                outgoing = fragments(self.sid, self.frame_number, self.current[0].pixels)
                self.current_encoding = ('raw', 1024, len(outgoing))
            self.packets.extend(outgoing)
            self.started = now
        elif self.target == self.committed:
            self.target = None
        if self.packets:
            self.request = self.packets.popleft()
        elif now >= self.next_heartbeat:
            self.request = body(HEARTBEAT, self.sid)
        if self.request is not None:
            self._pixel_query(0x17, b'\x00\x02\xff\xff' + self.request)

    def shutdown(self, after_release=None):
        """Discard queued frames, settle the in-flight reply, release, then clock.

        On uncertain delivery wait for lease expiry before touching stock mode.
        Closing this method is the handoff barrier for the UI mode coordinator.
        """
        had_display = self.owned or self.palette is not None
        self.target = None
        self.packets.clear()
        try:
            if self.handle and had_display:
                try:
                    if self.pending_query is not None:
                        deadline = time.monotonic() + 1.6
                        while self.pending_query and time.monotonic() < deadline:
                            pending = self.pending_query
                            ack = self._pixel_query(pending['command'], pending['payload'])
                            if ack is not None and self.palette and self.palette['phase'] == 'release':
                                self._check_ack(ack, 5); self.owned = False
                            time.sleep(.005)
                        if self.pending_query:
                            raise core.HaloError('未完成的 RAM 请求')
                    if self.owned:
                        self._control(body(RELEASE, self.sid), 5)
                        logging.info('HPL2 release acknowledged sid=%08x', self.sid)
                except Exception:
                    logging.exception('Release uncertain; waiting for MCU lease expiry')
                    self.pending_query = None
                    time.sleep(2.2)
                self.owned = False
                self.screen_color(self.restore_color)
                restore_clock(self, self.restore_color)
            if self.handle and after_release:
                after_release()
        finally:
            self.owned = False
            self.authorized = False
            self.request = self.current = self.target = None
            self.palette = None; self.supersede = False
            self.packets.clear()
            super().close()
