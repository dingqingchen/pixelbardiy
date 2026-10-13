"""Validated Halo PixelBar transport; packet builders derive from the MIT reference.

Only this device's display/light commands are written. Audio volume is untouched.
"""
from __future__ import annotations
import time
import hid
from . import vendor_core as core


def parse_response(report: bytes, command: int) -> bytes:
    if len(report) < 7 or report[:4] != bytes((0x2F, 0xBB, 0xEC, command)):
        raise core.HaloError("响应帧不匹配")
    length = int.from_bytes(report[4:6], "big")
    if length > 57 or len(report) < length + 7:
        raise core.HaloError("响应长度无效")
    if report[6 + length] != sum(report[1:6 + length]) & 255:
        raise core.HaloError("响应校验失败")
    return report[6:6 + length]


class HaloLink:
    def __init__(self, *, allow_resource_upload=False):
        self.handle = None
        self.info = {}
        self.last_display = None
        self.write_count = 0
        self.pixel_job = None
        self.pixel_frame = None
        self.pixel_color = None
        self.pixel_seconds = 0
        self.pending_query = None
        self.allow_resource_upload = allow_resource_upload

    def connect(self):
        self.close()
        devices = core.enumerate_halo_devices()
        if not devices:
            raise core.HaloError("未找到 Halo PixelBar，请接入 USB 数据线")
        if len(devices) != 1:
            raise core.HaloError("检测到多台 PixelBar，请仅保留一台连接")
        self.handle = hid.device()
        try:
            self.handle.open_path(devices[0].path)
            self.handle.set_nonblocking(True)
            self.info = devices[0].public_info()
            self.query(0x66)
        except Exception:
            self.close()
            raise
        return self.info

    def close(self):
        if self.handle:
            self.handle.close()
        self.handle = None
        self.last_display = None
        self.pixel_job = None
        self.pixel_frame = None
        self.pixel_color = None
        self.pending_query = None

    def release_display(self, color="#86D8F6"):
        """Best-effort return to the stock clock, then always close the link.

        Only release a display this link actually used. This is the stock-firmware
        exit path, NOT a RAM-stream lease or protection from another HID client.
        A future firmware lease must also recover when no exit packet arrives.
        """
        try:
            if self.handle and (self.last_display is not None or
                                self.pixel_frame is not None or self.pixel_job is not None):
                self.native_clock(color)
        finally:
            self.close()

    def _write(self, packet):
        if packet[3] == 0x17 and not self.allow_resource_upload:
            raise core.HaloError('实时显示已禁止图片上传命令 (0x17)')
        if not self.handle:
            raise core.HaloError("设备未连接")
        if self.handle.write(packet) != 64:
            raise core.HaloError("HID 数据未完整写入")
        self.write_count += 1

    def query(self, command, payload=(), timeout=0.7):
        if not self.handle:
            raise core.HaloError("设备未连接")
        for _ in range(64):
            response=bytes(self.handle.read(64))
            if not response:break
            self._buffer_response(response)
        self._write(core._edifier_packet(command, payload))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = bytes(self.handle.read(64))
            if response[:4] == bytes((0x2F, 0xBB, 0xEC, command)):
                return parse_response(response, command)
            self._buffer_response(response)
            time.sleep(.002)
        raise core.HaloError(f"设备响应超时 (0x{command:02X})，请退出 TempoHub 后重试")

    def _buffer_response(self,response):
        pending=self.pending_query
        if pending and response[:4]==bytes((0x2F,0xBB,0xEC,pending['command'])):
            pending['response']=parse_response(response,pending['command'])

    def _pixel_query(self,command,payload=(),timeout=1.5):
        """Advance one request without waiting for the device's 50–250 ms ACK.

        Keep its response when an ordinary health/light query reads it first.
        There is exactly one in-flight pixel request, so fragments stay ordered.
        """
        if self.pending_query is None:
            self.pending_query={'command':command,'payload':bytes(payload),
                                'deadline':time.monotonic()+timeout,'response':None}
            self._write(core._edifier_packet(command,payload))
            return None
        pending=self.pending_query
        if (pending['command'],pending['payload'])!=(command,bytes(payload)):
            raise core.HaloError('图案请求顺序错误')
        for _ in range(64):
            response=bytes(self.handle.read(64))
            if not response:break
            self._buffer_response(response)
        if pending['response'] is not None:
            self.pending_query=None
            return pending['response']
        if time.monotonic()>=pending['deadline']:
            self.pending_query=None
            raise core.HaloError(f'图案响应超时 (0x{command:02X})')
        return None

    def status(self):
        return {"device": self.info, "volume": list(self.query(0x66)),
                "ambient": list(self.query(0x6A)), "screen": list(self.query(0xEE)),
                "text_hex": self.query(0xE7, [0]).hex()}

    def show_text(self, text, color="#86D8F6", layout="center", verify=False):
        if not text.strip():
            text = " "
        native = layout == 'native_lyric_up'
        content = text if text.strip() else "·"
        raw = core._truncate_utf8(content)
        packet = (core._edifier_packet(0xE8, [0x0E, len(raw), *raw])
                  if native else core.build_text_packet(content))
        rgb = core.parse_color(color)
        signature = (packet, color, layout)
        if signature == self.last_display and not verify:
            return
        layout_changed = not self.last_display or self.last_display[2] != layout
        if native and layout_changed:
            # E8/0E enters the native LRC RAM buffer; E8/00 enters DIY instead.
            self._write(core._edifier_packet(0xEF, [1, *rgb, 0, 0, 1, 0, 0]))
            time.sleep(0.025)
        if not self.last_display or packet != self.last_display[0]:
            self._write(packet)
        if not native and layout_changed:
            time.sleep(0.025)
            self._write(core.build_layout_packet(layout, rgb))
        if not self.last_display or self.last_display[1] != color:
            # Color-only commands preserve the device's scrolling position.
            self.screen_color(color)
        if verify and native:
            # E7/00 reads DIY, not LRC. This query confirms connectivity only.
            self.query(0x66)
        elif verify:
            observed = self.query(0xE7, [0])
            if raw not in observed:
                raise core.HaloError("屏幕文字回读不匹配")
        self.last_display = signature

    def set_ambient(self, effect, color, brightness, speed, enabled=True):
        speed = 8 if effect == "color_tide" else speed
        packets = [core.build_ambient_packet(effect, color, brightness, speed),
                   core.build_ambient_power_packet(enabled)]
        for packet in packets:
            for _ in range(3):
                self._write(packet)
                time.sleep(0.03)
        observed=list(self.query(0x6A))
        if len(observed)<2 or observed[1]!=core.EFFECTS[effect]:
            raise core.HaloError('灯效模式未生效，请检查其他控制程序')
        return observed

    def rhythm_frame(self,color,brightness):
        packet=core.build_ambient_packet("static",color,brightness,8)
        # Enter static mode with set_ambient once. Streaming updates need one write;
        # do not sleep 90 ms in every audio sample or saturate the USB queue.
        self._write(packet)

    def screen_color(self,color):
        if color!=self.pixel_color:
            self._write(core.build_screen_color_packet(color))
            self.pixel_color=color

    def begin_pixels(self,frame,color,transition=False):
        if not self.allow_resource_upload:
            raise core.HaloError('实时显示不使用图片资源上传；仅保留离线协议测试代码')
        from .pixels import encode
        if self.pixel_job:raise core.HaloError('上一个图案仍在上传')
        self.pixel_job={'data':encode(frame.pixels),'frame':frame,'color':color,
                        'part':-1,'size':0,'fade':0,'transition':transition,
                        'started':time.monotonic(),'due':0}

    def step_pixels(self,now):
        """Nonblocking transfer: audio runs while each fragment awaits its ACK."""
        from .themes import mix_color
        from .pixels import SCENE
        job=self.pixel_job
        if not job or now<job['due']:return
        if job['part']==-1:
            ack=self._pixel_query(0x17,[0,0,*len(job['data']).to_bytes(4,'big')])
            if ack is None:return
            if len(ack)<4 or ack[:2]!=b'\x00\x01':raise core.HaloError('图案上传握手失败')
            size=int.from_bytes(ack[2:4],'big')
            if not 1<=size<=53:raise core.HaloError(f'未支持的图案分片大小：{size}')
            job.update(part=0,size=size);return
        if job['part']>=0:
            index=job['part'];offset=index*job['size']
            chunk=job['data'][offset:offset+job['size']];last=offset+len(chunk)==len(job['data'])
            ack=self._pixel_query(0x17,[0,2,*index.to_bytes(2,'big'),*chunk])
            if ack is None:return
            if last:
                # This firmware commits on the last fragment. Other revisions
                # request the explicit end marker used by TempoHub.
                if ack[:2]==b'\x00\x03':job['part']=-3;return
                if ack[:2]!=b'\x00\x05':raise core.HaloError('设备未确认图案完整接收')
                job['part']=-4
            elif ack[:2]!=b'\x00\x03':raise core.HaloError('图案分片未被接受')
            else:job['part']+=1
            return
        if job['part']==-3:
            ack=self._pixel_query(0x17,[0,4])
            if ack is None:return
            if ack[:2]!=b'\x00\x05':raise core.HaloError('设备未确认图案完整接收')
            job['part']=-4;return
        if job['part']==-4:
            self.screen_color(mix_color('#000000',job['color'],.12) if job['transition'] else job['color'])
            self._write(core._edifier_packet(0xEF,[1,*core.parse_color(job['color']),0,1,SCENE,0,255]))
            job['part']=-5;return
        if job['part']==-5:
            observed=self._pixel_query(0xEE)
            if observed is None:return
            if len(observed)<8 or observed[5:8]!=bytes([1,SCENE,0]):raise core.HaloError('设备未进入图案显示模式')
            self.pixel_frame=job['frame'];self.last_display=None
            self.pixel_seconds=time.monotonic()-job['started']
            if job['transition']:job.update(part=-2,due=now+.06)
            else:self.pixel_job=None
            return
        job['fade']+=1
        self.screen_color(mix_color('#000000',job['color'],min(1,job['fade']/4)))
        job['due']=now+.08
        if job['fade']>=4:self.pixel_job=None

    def ambient_power(self,enabled):
        for _ in range(3):
            self._write(core.build_ambient_power_packet(enabled))
            time.sleep(.03)

    def native_clock(self, color="#86D8F6"):
        self._write(core._edifier_packet(0xEF, [1, *core.parse_color(color), 0, 1, 0, 0, 255]))
        self.last_display = None
