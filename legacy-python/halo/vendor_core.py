from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import time
from typing import Iterable

import hid


VENDOR_ID = 0x2D99
PRODUCT_ID = 0xA106
INTERFACE_NUMBER = 4
PACKET_LENGTH = 64
CONTROL_USAGE_PAGE = 0xFF14
CONTROL_USAGE = 0x01
EDIFIER_DEVICE_TYPE = 0xED
LIGHTING_WRITE_REPETITIONS = 3
LIGHTING_WRITE_DELAY_SECONDS = 0.03
MAX_HARDWARE_VOLUME = 16


class HaloError(RuntimeError):
    pass


class TextColor(IntEnum):
    white = 0
    red = 1
    green = 2
    blue = 3
    yellow = 4
    cyan = 5
    magenta = 6


SCENES = {
    "clock": 0,
    "game": 1,
    "work": 2,
    "read": 3,
    "cats": 4,
    "dogs": 5,
    "memes": 6,
    "cyber": 7,
    "waves": 8,
}

LAYOUTS = {
    "left": (0, 0),
    "center": (0, 1),
    "right": (0, 2),
    "stretch": (0, 3),
    "scroll_left_to_right": (1, 0),
    "scroll_right_to_left": (1, 1),
}

EFFECTS = {
    "breathing": 1,
    "color_tide": 2,
    "static": 3,
    "ripple": 4,
    "flow": 5,
    "dynamic": 6,
}

BRIGHTNESS = {"low": 0x14, "medium": 0x28, "high": 0x3C}


@dataclass(frozen=True)
class HaloDevice:
    path: bytes
    product: str
    manufacturer: str
    serial_number: str
    usage_page: int
    usage: int
    interface_number: int

    def public_info(self) -> dict[str, object]:
        return {
            "product": self.product,
            "manufacturer": self.manufacturer,
            "vendor_id": f"0x{VENDOR_ID:04X}",
            "product_id": f"0x{PRODUCT_ID:04X}",
            "interface_number": self.interface_number,
            "usage_page": f"0x{self.usage_page:04X}",
            "usage": self.usage,
        }


def enumerate_halo_devices() -> list[HaloDevice]:
    devices: list[HaloDevice] = []
    for item in hid.enumerate(VENDOR_ID, PRODUCT_ID):
        interface_number = int(item.get("interface_number", -1))
        product = str(item.get("product_string") or "")
        if interface_number != INTERFACE_NUMBER:
            continue
        if int(item.get("usage_page", 0)) != CONTROL_USAGE_PAGE:
            continue
        if int(item.get("usage", 0)) != CONTROL_USAGE:
            continue
        if "halo" not in product.casefold() and "pixelbar" not in product.casefold():
            continue
        path = item.get("path", b"")
        if not isinstance(path, bytes):
            path = str(path).encode("utf-8")
        devices.append(
            HaloDevice(
                path=path,
                product=product,
                manufacturer=str(item.get("manufacturer_string") or ""),
                serial_number=str(item.get("serial_number") or ""),
                usage_page=int(item.get("usage_page", 0)),
                usage=int(item.get("usage", 0)),
                interface_number=interface_number,
            )
        )
    return sorted(devices, key=lambda device: device.usage_page)


def _pad(data: Iterable[int]) -> bytes:
    packet = bytes(data)
    if len(packet) > PACKET_LENGTH:
        raise HaloError(f"Packet is too large: {len(packet)} bytes")
    return packet + bytes(PACKET_LENGTH - len(packet))


def _edifier_packet(command: int, payload: Iterable[int]) -> bytes:
    body = bytes(payload)
    packet = bytearray(
        [
            0x2E,
            0xAA,
            EDIFIER_DEVICE_TYPE,
            command,
            (len(body) >> 8) & 0xFF,
            len(body) & 0xFF,
        ]
    )
    packet.extend(body)
    packet.append(sum(packet[1:]) & 0xFF)
    return _pad(packet)


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    cleaned = value.strip().removeprefix("#")
    if len(cleaned) != 6:
        raise HaloError("Color must be a six-digit hex value such as #F0B4C8")
    try:
        return tuple(int(cleaned[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise HaloError("Color contains non-hexadecimal characters") from exc


def _truncate_utf8(text: str, max_chars: int = 16, max_bytes: int = 48) -> bytes:
    if not text.strip():
        raise HaloError("Text cannot be empty")
    text = text.strip()[:max_chars]
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return encoded
    while len(encoded) > max_bytes:
        text = text[:-1]
        encoded = text.encode("utf-8")
    return encoded


def build_text_packet(text: str, color: str = "white") -> bytes:
    # Text color belongs to the separate 0xEF pixel-screen setting. Keep the
    # old argument for API compatibility, but do not encode it into 0xE8.
    if color not in TextColor.__members__:
        raise HaloError(f"Unsupported text color: {color}")
    text_bytes = _truncate_utf8(text)
    return _edifier_packet(0xE8, [0x00, len(text_bytes), *text_bytes])


def build_layout_packet(layout: str, rgb: tuple[int, int, int]) -> bytes:
    try:
        scroll, mode = LAYOUTS[layout]
    except KeyError as exc:
        raise HaloError(f"Unsupported text layout: {layout}") from exc
    payload = [0x01, *rgb, 0x00, 0x02, scroll, mode, 0xFF]
    return _edifier_packet(0xEF, payload)


def build_scene_packet(scene: str, rgb: tuple[int, int, int]) -> bytes:
    try:
        scene_id = SCENES[scene]
    except KeyError as exc:
        raise HaloError(f"Unsupported scene: {scene}") from exc
    return _edifier_packet(0xEF, [0x02, *rgb, 0x00, 0x01, scene_id, 0xFF, 0xFF])


def build_screen_color_packet(color: str) -> bytes:
    return _edifier_packet(
        0xEF, [0x03, *_parse_hex_color(color), 0x00, 0x00, 0xFF, 0xFF, 0xFF]
    )


def build_ambient_packet(
    effect: str, color: str, brightness: str, speed: int
) -> bytes:
    if effect not in EFFECTS:
        raise HaloError(f"Unsupported ambient effect: {effect}")
    if brightness not in BRIGHTNESS:
        raise HaloError(f"Unsupported brightness: {brightness}")
    if not 1 <= speed <= 10:
        raise HaloError("Speed must be between 1 and 10")
    return _edifier_packet(
        0x6B,
        [0x13, EFFECTS[effect], *_parse_hex_color(color), BRIGHTNESS[brightness], speed],
    )


def build_ambient_power_packet(enabled: bool) -> bytes:
    return _edifier_packet(0x6B, [0x00, 0x00, 0x00, 0x00, int(enabled), 0xFF, 0xFF])


def build_volume_query_packet() -> bytes:
    return _edifier_packet(0x66, [])


def build_hardware_volume_packet(volume: int) -> bytes:
    if not 0 <= volume <= MAX_HARDWARE_VOLUME:
        raise HaloError(
            f"Hardware volume must be between 0 and {MAX_HARDWARE_VOLUME}"
        )
    return _edifier_packet(0x67, [volume])


def parse_volume_response(report: Iterable[int]) -> dict[str, int]:
    packet = bytes(report)
    if len(packet) < 9 or packet[:4] != bytes([0x2F, 0xBB, 0xEC, 0x66]):
        raise HaloError("Unexpected Halo hardware-volume response")
    payload_length = (packet[4] << 8) | packet[5]
    if payload_length < 2 or len(packet) < 7 + payload_length:
        raise HaloError("Incomplete Halo hardware-volume response")
    payload = packet[6 : 6 + payload_length]
    return {"maximum": payload[0], "current": payload[1]}


def get_hardware_volume(timeout_ms: int = 1000) -> dict[str, object]:
    devices = enumerate_halo_devices()
    if not devices:
        raise HaloError("Halo PixelBar HID control interface was not found")

    errors: list[str] = []
    for candidate in devices:
        device = None
        try:
            device = hid.device()
            device.open_path(candidate.path)
            if int(device.write(build_volume_query_packet())) < 0:
                raise HaloError("HID write returned an error")
            response = device.read(PACKET_LENGTH, timeout_ms)
            volume = parse_volume_response(response)
            return {**volume, "device": candidate.public_info()}
        except Exception as exc:
            errors.append(f"usage_page=0x{candidate.usage_page:04X}: {exc}")
        finally:
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass
    raise HaloError("Could not read Halo hardware volume: " + "; ".join(errors))


def set_hardware_volume(volume: int) -> dict[str, object]:
    result = send_packets(build_hardware_volume_packet(volume))
    observed = get_hardware_volume()
    if observed["current"] != volume:
        raise HaloError(
            f"Halo reported hardware volume {observed['current']} after setting {volume}"
        )
    return {**result, "hardware_volume": volume, "maximum": observed["maximum"]}


def send_packets(*packets: bytes) -> dict[str, object]:
    devices = enumerate_halo_devices()
    if not devices:
        raise HaloError("Halo PixelBar HID control interface was not found")

    errors: list[str] = []
    for candidate in devices:
        device = None
        try:
            device = hid.device()
            device.open_path(candidate.path)
            written: list[int] = []
            for packet in packets:
                repetitions = (
                    LIGHTING_WRITE_REPETITIONS
                    if packet[:4] == bytes([0x2E, 0xAA, EDIFIER_DEVICE_TYPE, 0x6B])
                    else 1
                )
                for attempt in range(repetitions):
                    count = int(device.write(packet))
                    if count < 0:
                        raise HaloError("HID write returned an error")
                    written.append(count)
                    if attempt + 1 < repetitions:
                        time.sleep(LIGHTING_WRITE_DELAY_SECONDS)
            return {"success": True, "device": candidate.public_info(), "written": written}
        except Exception as exc:
            errors.append(f"usage_page=0x{candidate.usage_page:04X}: {exc}")
        finally:
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass
    raise HaloError("No writable Halo PixelBar HID channel: " + "; ".join(errors))


def parse_color(value: str) -> tuple[int, int, int]:
    return _parse_hex_color(value)
