import binascii
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from halo.device import HaloLink
from halo.pixels import PixelFrame
from halo.ram_display import (RamDisplay, fragments, body, ACQUIRE, HEARTBEAT,
    BEGIN, DATA, RELEASE, restore_clock, validate_installation, CANDIDATE_SHA)
from halo import vendor_core as core


class FakeRam(RamDisplay):
    def __init__(self):
        super().__init__(Path('unused'))
        self.owned = self.authorized = True
        self.sid = 123; self.handle = SimpleNamespace(close=lambda: None)
        self.pixel_color = '#FFFFFF'; self.sent = []; self.events = []
        self.pending_payload = None

    def _pixel_query(self, command, payload=(), **kwargs):
        assert command == 0xEE or (command == 0x17 and payload[:8] == b'\x00\x02\xff\xffHPL2')
        if self.pending_payload is None:
            self.pending_payload = bytes(payload)
            self.pending_query = {'command': command, 'payload': bytes(payload)}
            if command == 0x17:
                self.sent.append(bytes(payload))
                if payload[8] in (RELEASE, ACQUIRE): self.events.append(('control', payload[8], 5 if payload[8] == RELEASE else 3))
                if payload[8] == 6: self.encoded_left = int.from_bytes(payload[21:23], 'big')
                if payload[8] == 7: self.encoded_left -= payload[16]
            return None
        assert self.pending_payload == bytes(payload)
        self.pending_payload = self.pending_query = None
        if command == 0xEE: return self.query(command)
        return b'\x00\x05' if payload[8] == RELEASE or (payload[8] == DATA and payload[15] == 27) or (payload[8] == 7 and self.encoded_left == 0) else b'\x00\x03\xff\xff'

    def _control(self, request, expected):
        self.events.append(('control', request[4], expected)); self.sent.append(b'\x00\x02\xff\xff'+request)

    def native_clock(self, color):
        assert not self.owned
        self.events.append(('clock', color))

    def screen_color(self, color):
        if color != self.pixel_color:
            assert not self.owned
            self.events.append(('color', color)); self.pixel_color = color

    def query(self, command, *args, **kwargs):
        assert command == 0xEE
        self.events.append(('query', command))
        return b'\x00'+bytes(core.parse_color(self.pixel_color))+b'\x00\x01\x00\x00\xff'


def frame(n): return PixelFrame(bytes([n])*1024, str(n), 'test:'+str(n))


def test_ram_fragments_have_crc_and_reserved_route_never_resource_markers():
    packets = fragments(123, 9, bytes(range(256))*4)
    assert len(packets) == 29 and packets[0] == body(BEGIN, 123, 9)
    assert [p[11] for p in packets[1:]] == list(range(28))
    raw = b''.join(p[13:] for p in packets[1:])
    assert raw[:-2] == bytes(range(256))*4
    assert int.from_bytes(raw[-2:], 'big') == binascii.crc_hqx(raw[:-2], 0)
    assert all(len(p) <= 50 for p in packets)


def test_last_wins_no_partial_commit_and_heartbeat():
    d = FakeRam(); d.offer(frame(1), '#FFFFFF'); d.tick(0)
    assert d.committed is None
    d.offer(frame(2), '#FFFFFF'); d.offer(frame(3), '#FFFFFF')
    for i in range(1, 62): d.tick(i*.06)
    assert d.committed == (frame(3), '#FFFFFF') and d.frames_sent == 2
    d.tick(4.2)
    raw = [p for p in d.sent if p[8] == BEGIN]
    assert len(raw) == 2
    assert any(p[8] == HEARTBEAT for p in d.sent)
    assert d.current is None and d.target is None


def test_guard_rejects_all_stock_resource_and_upgrade_commands():
    d = RamDisplay(Path('unused')); d.authorized = True
    writes = []; d.handle = SimpleNamespace(write=lambda p: writes.append(p) or 64)
    for command, payload in ((0x17, [0, 0]), (0x17, [0, 4]), (0x17, [0, 2, 0, 0]), (0x10, []), (0x11, []), (0xE8, [0])):
        with pytest.raises(core.HaloError): d._write(core._edifier_packet(command, payload))
    d._write(core._edifier_packet(0x17, b'\x00\x02\xff\xff'+body(ACQUIRE, 12)))
    assert len(writes) == 1
    d.authorized = False
    with pytest.raises(core.HaloError): d._write(core._edifier_packet(0x17, b'\x00\x02\xff\xff'+body(ACQUIRE, 12)))
    d.owned = True
    with pytest.raises(core.HaloError): d.native_clock('#FFFFFF')


def test_installation_identity_is_required_not_just_stock_version(tmp_path):
    path = tmp_path/'mcu.json'; device = SimpleNamespace(serial_number='123', path=b'usb:path')
    with pytest.raises(core.HaloError): validate_installation(path, [device])
    record = dict(candidate_sha256=CANDIDATE_SHA, graphics_visually_confirmed=True, serial='123', hid_path='usb:path')
    path.write_text(json.dumps(record)); assert validate_installation(path, [device]) == record
    for key, bad in [('serial', '456'), ('hid_path', 'another'), ('candidate_sha256', 'unknown'), ('graphics_visually_confirmed', False)]:
        path.write_text(json.dumps({**record, key: bad}))
        with pytest.raises(core.HaloError): validate_installation(path, [device])


def test_shutdown_discards_frames_releases_before_clock_and_closes(monkeypatch):
    import halo.ram_display as module
    d = FakeRam(); d.offer(frame(1), '#FFFFFF'); d.tick(0)
    d.offer(frame(2), '#FFFFFF')
    def restore(link, color):
        assert not link.owned
        link.native_clock(color); return ['stable']
    monkeypatch.setattr(module, 'restore_clock', restore)
    d.shutdown()
    assert d.events[0] == ('control', RELEASE, 5)
    assert d.events[-1][0] == 'clock'
    assert not d.handle and not d.owned and not d.target and not d.packets
    assert not any(p[8] == DATA for p in d.sent)  # incomplete frame is discarded


def test_clock_retries_stale_mode_rebound_then_requires_stability():
    now = [0.0]; events = []; reads = iter([True, False, True, True, True])
    link = SimpleNamespace(native_clock=lambda color: events.append(('clock', now[0])),
        query=lambda command: b'12345'+(b'\x01\x00\x00' if next(reads) else b'\x02\x00\x01'))
    result = restore_clock(link, '#FFFFFF', clock=lambda: now[0], sleep=lambda t: now.__setitem__(0, now[0]+t))
    assert len(events) == 2 and len(result) == 5 and now[0] >= 3.5


def test_bad_ack_does_not_publish_frame():
    d = FakeRam(); d.offer(frame(1), '#FFFFFF'); d.tick(0)
    d._pixel_query = lambda *args, **kwargs: b'\x00\x05'
    with pytest.raises(core.HaloError): d.tick(.1)
    assert d.committed is None


def test_palette_changes_outside_lease(monkeypatch):
    import halo.ram_display as module
    now = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(module, 'restore_clock', lambda *args: pytest.fail('Theme change must not block on exit verification'))
    d = FakeRam(); d.offer(frame(1), '#D6BBFF'); d.tick(0)
    for i in range(1, 61):
        now[0] = i*.05
        if i in (2, 3): d.offer(frame(i), '#86D8F6' if i == 3 else '#CCDDFF', urgent=True)
        d.tick(now[0])
    assert [event[0] for event in d.events] == ['control', 'color', 'clock', 'query', 'control']
    assert d.events[0][1] == RELEASE and d.events[-1][1] == ACQUIRE
    assert d.committed == (frame(3), '#86D8F6') and d.frames_sent == 1
    assert d.palette_seconds < .8


def test_new_lyric_supersedes_partial_frame_only_after_inflight_ack():
    d = FakeRam(); d.offer(frame(1), '#FFFFFF'); d.tick(0)
    for i in range(1, 8): d.tick(i*.05)
    old_id = d.frame_number
    d.offer(frame(2), '#FFFFFF', urgent=True)
    d.tick(.4, send=False)
    assert d.current[0] == frame(1) and d.request is None
    d.tick(.41)
    assert d.frame_number == old_id+1 and d.current[0] == frame(2)
    for i in range(9, 45): d.tick(i*.05)
    assert d.committed == (frame(2), '#FFFFFF') and d.frames_sent == 1 and d.frames_dropped == 1
    assert len([p for p in d.sent if p[8] == DATA and int.from_bytes(p[13:15], 'big') == old_id]) < 28


@pytest.mark.parametrize('phase', ['release', 'color', 'clock', 'verify', 'acquire'])
def test_shutdown_during_palette_handoff_restores_clock(phase, monkeypatch):
    import halo.ram_display as module
    now = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: now[0])
    monkeypatch.setattr(module.time, 'sleep', lambda delay: now.__setitem__(0, now[0]+delay))
    monkeypatch.setattr(module, 'restore_clock', lambda link, color: link.native_clock(color))
    d = FakeRam(); d.offer(frame(1), '#D6BBFF')
    for i in range(30):
        now[0] = i*.05; d.tick(now[0])
        if d.palette and d.palette['phase'] == phase:
            # Exercise actual in-flight EE/acquire, not merely the next phase.
            if phase in ('verify', 'acquire') and d.request is None: continue
            break
    else: pytest.fail('Did not reach palette phase')
    assert not d.ready_for_lights
    d.shutdown()
    assert not d.handle and not d.owned and d.palette is None
    assert d.events[-1] == ('clock', d.restore_color)


def test_ack_layout_matches_recorded_hardware_replies():
    RamDisplay._check_ack(bytes.fromhex('0003ffff'), 3)
    RamDisplay._check_ack(bytes.fromhex('0005'), 5)
    for invalid, expected in [('0003', 3), ('00030000', 3), ('0005ffff', 5), ('0005', 3)]:
        with pytest.raises(core.HaloError): RamDisplay._check_ack(bytes.fromhex(invalid), expected)


def test_short_lighting_write_is_retried_but_ram_fragment_is_not():
    d = RamDisplay(Path('unused')); results = iter([-1, 64]); writes = []
    d.handle = SimpleNamespace(write=lambda p: writes.append(p) or next(results))
    d.rhythm_frame('#FFFFFF', 'high')
    assert len(writes) == 2 and writes[0] == writes[1] and d.write_count == 1
    d.authorized = True; results = iter([-1, 64]); writes.clear()
    with pytest.raises(core.HaloError): d._write(core._edifier_packet(0x17, b'\x00\x02\xff\xff'+body(ACQUIRE, 12)))
    assert len(writes) == 1


def test_drain_phase_leaves_a_gap_for_lights_before_next_fragment():
    d = FakeRam(); d.offer(frame(1), '#FFFFFF'); d.tick(0)
    assert len(d.sent) == 1 and d.request is not None
    d.tick(.05, send=False)
    assert len(d.sent) == 1 and d.request is None and d.packets
    d.tick(.06)
    assert len(d.sent) == 2 and d.request[4] == DATA


def test_codec_transport_uses_last_committed_base_after_abandoning_frame():
    from halo.ram_codec import Encoded, decode
    d = FakeRam(); d.codec_enabled = True
    a = PixelFrame(bytes(range(256))*4, 'first', 'lyric:first')
    import random
    b = PixelFrame(random.Random(7).randbytes(1024), 'discard', 'lyric:discard')
    pixels = bytearray(a.pixels); pixels[42:46] = b'abcd'
    c = PixelFrame(bytes(pixels), 'latest', 'lyric:latest')
    d.offer(a, '#FFFFFF')
    for i in range(32): d.tick(i*.05)
    assert d.committed == (a, '#FFFFFF') and d.committed_number == 1
    d.offer(b, '#FFFFFF'); d.tick(2); d.tick(2.05)
    d.offer(c, '#FFFFFF', urgent=True, animation=1)
    for i in range(42,62): d.tick(i*.05)
    assert d.committed == (c, '#FFFFFF') and d.committed_number == 3
    last = [p for p in d.sent if p[8] in (6,7) and p[13:15] == b'\x00\x03']
    metadata = last[0][17:]; data = b''.join(p[17:] for p in last[1:])
    assert metadata[0] == 2 and metadata[1] == 1 and metadata[6:8] == b'\x00\x01'
    assert decode(Encoded(2, data, metadata), a.pixels, 1) == c.pixels
    assert d.frame_packets < 5 and d.frames_dropped == 1


def test_codec_commands_require_commissioned_extension():
    from halo.ram_codec import encode, packets
    d = RamDisplay(Path('unused')); d.authorized = True
    writes=[]; d.handle=SimpleNamespace(write=lambda p: writes.append(p) or 64)
    wire = core._edifier_packet(0x17, b'\x00\x02\xff\xff'+packets(1,1,encode(bytes(1024)))[0])
    with pytest.raises(core.HaloError): d._write(wire)
    d.codec_enabled=True; d._write(wire)
    assert len(writes)==1


def test_display_statistics_remain_bound_to_completed_frame():
    d = FakeRam(); d.codec_enabled = True
    d.offer(PixelFrame(bytes(1024), 'blank', 'blank'), '#FFFFFF')
    for i in range(8): d.tick(i*.05)
    completed = (d.frame_codec, d.frame_bytes, d.frame_packets, d.frame_seconds)
    assert completed[0]=='rle' and completed[2]==2
    import random
    d.offer(PixelFrame(random.Random(12).randbytes(1024), 'noise', 'noise'), '#FFFFFF')
    d.tick(1); d.tick(1.05)
    assert d.current and d.current_encoding[0]=='raw'
    assert (d.frame_codec,d.frame_bytes,d.frame_packets,d.frame_seconds)==completed
    for i in range(22,55): d.tick(i*.05)
    assert d.frame_codec=='raw' and d.frame_packets==29 and d.frames_sent==2
