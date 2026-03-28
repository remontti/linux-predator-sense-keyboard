import array
import fcntl
import os
import re
from pathlib import Path

from .constants import (
    DEVICE_IDS,
    DIRECTION_IDS,
    EFFECT_IDS,
    FEATURE_LENGTHS,
    PREFERRED_RGB_CONTROLLERS,
    RGB_FEATURE_ID,
    SUPPORTED_EFFECTS_BY_DEVICE,
    ZONE_IDS,
)
from .models import HidrawDevice, KeyboardState, LidState


IOC_NRBITS = 8
IOC_TYPEBITS = 8
IOC_SIZEBITS = 14
IOC_DIRBITS = 2

IOC_NRSHIFT = 0
IOC_TYPESHIFT = IOC_NRSHIFT + IOC_NRBITS
IOC_SIZESHIFT = IOC_TYPESHIFT + IOC_TYPEBITS
IOC_DIRSHIFT = IOC_SIZESHIFT + IOC_SIZEBITS

IOC_WRITE = 1
IOC_READ = 2


def _IOC(direction: int, ioc_type: str, nr: int, size: int) -> int:
    return (
        (direction << IOC_DIRSHIFT)
        | (ord(ioc_type) << IOC_TYPESHIFT)
        | (nr << IOC_NRSHIFT)
        | (size << IOC_SIZESHIFT)
    )


def HIDIOCGFEATURE(length: int) -> int:
    return _IOC(IOC_READ | IOC_WRITE, "H", 0x07, length)


def HIDIOCSFEATURE(length: int) -> int:
    return _IOC(IOC_READ | IOC_WRITE, "H", 0x06, length)


def hexdump(data: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in data)


def parse_uevent(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def list_hidraw_devices() -> list[HidrawDevice]:
    devices: list[HidrawDevice] = []
    for entry in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        uevent_path = entry / "device" / "uevent"
        if not uevent_path.exists():
            continue
        info = parse_uevent(uevent_path)
        devices.append(
            HidrawDevice(
                devnode=f"/dev/{entry.name}",
                sysfs_name=entry.name,
                hid_id=info.get("HID_ID", ""),
                hid_name=info.get("HID_NAME", ""),
                hid_phys=info.get("HID_PHYS", ""),
            )
        )
    return devices


def detect_rgb_device(manual_path: str | None = None) -> HidrawDevice:
    if manual_path is None and os.path.exists("/dev/acer-rgb"):
        manual_path = "/dev/acer-rgb"

    if manual_path:
        devnode = manual_path
        resolved = Path(devnode).resolve()
        sysfs_name = resolved.name
        uevent_path = Path("/sys/class/hidraw") / sysfs_name / "device" / "uevent"
        info = parse_uevent(uevent_path) if uevent_path.exists() else {}
        return HidrawDevice(
            devnode=devnode,
            sysfs_name=sysfs_name,
            hid_id=info.get("HID_ID", ""),
            hid_name=info.get("HID_NAME", ""),
            hid_phys=info.get("HID_PHYS", ""),
        )

    devices = list_hidraw_devices()
    for vendor, product, _label in PREFERRED_RGB_CONTROLLERS:
        for device in devices:
            dev_vendor, dev_product = device.vendor_product
            if dev_vendor == vendor and dev_product == product:
                return device
    raise RuntimeError("no supported Acer RGB HID controller found")


def get_feature_report(fd: int, report_id: int, length: int) -> bytes:
    buf = array.array("B", bytes([report_id]) + b"\x00" * (length - 1))
    fcntl.ioctl(fd, HIDIOCGFEATURE(length), buf, True)
    return bytes(buf)


def set_feature_report(fd: int, data: bytes) -> bytes:
    buf = array.array("B", data)
    fcntl.ioctl(fd, HIDIOCSFEATURE(len(data)), buf, True)
    return bytes(buf)


def validate_brightness(value: int) -> None:
    if value < 0 or value > 100:
        raise ValueError("brightness must be between 0 and 100")


def validate_speed(value: int) -> None:
    if value < 0 or value > 9:
        raise ValueError("speed must be between 0 and 9")


def parse_hex_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lower()
    if len(value) != 6:
        raise ValueError(f"invalid hex color: {value}")
    try:
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"invalid hex color: {value}") from exc
    return red, green, blue


def normalize_hex_color(value: str) -> str:
    value = value.strip().lower()
    parse_hex_color(value)
    return value


def normalize_profile_name(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("profile name cannot be empty")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized):
        raise ValueError("profile name must use only a-z, 0-9, _ or -")
    return normalized


def build_payload(
    device: str,
    effect: str,
    brightness: int,
    speed: int,
    direction: str,
    red: int,
    green: int,
    blue: int,
    zone: str | int,
) -> bytes:
    validate_brightness(brightness)
    validate_speed(speed)
    if effect not in SUPPORTED_EFFECTS_BY_DEVICE[device]:
        raise ValueError(f"effect {effect} is not supported for {device}")
    zone_value = zone if isinstance(zone, int) else ZONE_IDS[zone]
    return bytes(
        [
            RGB_FEATURE_ID,
            DEVICE_IDS[device],
            EFFECT_IDS[effect],
            brightness,
            speed,
            DIRECTION_IDS[direction],
            red,
            green,
            blue,
            zone_value,
            0x00,
        ]
    )


def send_payloads(
    device: HidrawDevice,
    payloads: list[bytes],
    dry_run: bool = False,
) -> dict:
    result = {
        "device": device,
        "payloads": [hexdump(payload) for payload in payloads],
        "write_returns": [],
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    if not os.path.exists(device.devnode):
        raise FileNotFoundError(f"device path does not exist: {device.devnode}")

    try:
        with open(device.devnode, "rb+", buffering=0) as handle:
            fd = handle.fileno()
            for payload in payloads:
                returned = set_feature_report(fd, payload)
                result["write_returns"].append(hexdump(returned))
    except PermissionError as exc:
        raise PermissionError(
            f"permission denied for {device.devnode}; run with sudo/pkexec or install the udev rule"
        ) from exc
    return result


def build_zone_payloads(zone_colors: list[str], brightness: int) -> list[bytes]:
    payloads: list[bytes] = []
    for zone, color in zip(("1", "2", "3", "4"), zone_colors):
        red, green, blue = parse_hex_color(color)
        payloads.append(
            build_payload(
                device="keyboard",
                effect="static",
                brightness=brightness,
                speed=0,
                direction="none",
                red=red,
                green=green,
                blue=blue,
                zone=zone,
            )
        )
    return payloads


def apply_keyboard_static(
    hidraw: str | None,
    zone_colors: list[str],
    brightness: int,
    dry_run: bool = False,
) -> dict:
    device = detect_rgb_device(hidraw)
    payloads = build_zone_payloads([normalize_hex_color(color) for color in zone_colors], brightness)
    return send_payloads(device, payloads, dry_run=dry_run)


def apply_keyboard_single_color(
    hidraw: str | None,
    color: str,
    brightness: int,
    dry_run: bool = False,
) -> dict:
    device = detect_rgb_device(hidraw)
    red, green, blue = parse_hex_color(normalize_hex_color(color))
    payload = build_payload(
        device="keyboard",
        effect="static",
        brightness=brightness,
        speed=0,
        direction="none",
        red=red,
        green=green,
        blue=blue,
        zone="all",
    )
    return send_payloads(device, [payload], dry_run=dry_run)


def apply_keyboard_zone(
    hidraw: str | None,
    zone: str,
    color: str,
    brightness: int,
    dry_run: bool = False,
) -> dict:
    device = detect_rgb_device(hidraw)
    red, green, blue = parse_hex_color(normalize_hex_color(color))
    payload = build_payload(
        device="keyboard",
        effect="static",
        brightness=brightness,
        speed=0,
        direction="none",
        red=red,
        green=green,
        blue=blue,
        zone=zone,
    )
    return send_payloads(device, [payload], dry_run=dry_run)


def apply_keyboard_effect(
    hidraw: str | None,
    effect: str,
    brightness: int,
    speed: int,
    direction: str,
    dry_run: bool = False,
) -> dict:
    device = detect_rgb_device(hidraw)
    payload = build_payload(
        device="keyboard",
        effect=effect,
        brightness=brightness,
        speed=speed,
        direction=direction,
        red=0,
        green=0,
        blue=0,
        zone="all",
    )
    return send_payloads(device, [payload], dry_run=dry_run)


def apply_lid_static(
    hidraw: str | None,
    color: str,
    brightness: int,
    dry_run: bool = False,
) -> dict:
    device = detect_rgb_device(hidraw)
    red, green, blue = parse_hex_color(normalize_hex_color(color))
    payload = build_payload(
        device="lid",
        effect="static",
        brightness=brightness,
        speed=0,
        direction="none",
        red=red,
        green=green,
        blue=blue,
        zone=0x00,
    )
    return send_payloads(device, [payload], dry_run=dry_run)


def apply_lid_effect(
    hidraw: str | None,
    effect: str,
    brightness: int,
    speed: int,
    dry_run: bool = False,
) -> dict:
    device = detect_rgb_device(hidraw)
    payload = build_payload(
        device="lid",
        effect=effect,
        brightness=brightness,
        speed=speed,
        direction="none",
        red=0,
        green=0,
        blue=0,
        zone=0x00,
    )
    return send_payloads(device, [payload], dry_run=dry_run)


def feature_status(hidraw: str | None) -> dict:
    device = detect_rgb_device(hidraw)
    reports = {}
    if os.geteuid() != 0:
        return {"device": device, "reports": reports, "needs_root": True}
    if not os.path.exists(device.devnode):
        raise FileNotFoundError(f"device path does not exist: {device.devnode}")
    with open(device.devnode, "rb+", buffering=0) as handle:
        fd = handle.fileno()
        for report_id, length in FEATURE_LENGTHS.items():
            try:
                reports[report_id] = hexdump(get_feature_report(fd, report_id, length))
            except OSError as exc:
                reports[report_id] = f"error:{exc}"
    return {"device": device, "reports": reports, "needs_root": False}


def apply_keyboard_state(hidraw: str | None, state: KeyboardState, dry_run: bool = False) -> dict:
    if state.effect == "static":
        return apply_keyboard_static(hidraw, state.zones, state.brightness, dry_run=dry_run)
    return apply_keyboard_effect(
        hidraw,
        state.effect,
        state.brightness,
        state.speed,
        state.direction,
        dry_run=dry_run,
    )


def apply_lid_state(hidraw: str | None, state: LidState, dry_run: bool = False) -> dict:
    if state.effect == "static":
        return apply_lid_static(hidraw, state.color, state.brightness, dry_run=dry_run)
    return apply_lid_effect(hidraw, state.effect, state.brightness, state.speed, dry_run=dry_run)
