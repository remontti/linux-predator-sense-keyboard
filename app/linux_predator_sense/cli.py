import argparse
import sys

from .constants import BUILTIN_PRESETS, FEATURE_LENGTHS, SUPPORTED_EFFECTS_BY_DEVICE
from .hid_backend import (
    apply_keyboard_effect,
    apply_keyboard_single_color,
    apply_keyboard_static,
    apply_keyboard_zone,
    apply_lid_effect,
    apply_lid_static,
    feature_status,
    list_hidraw_devices,
)
from .profile_store import (
    list_keyboard_profiles,
    load_keyboard_profile,
    save_keyboard_profile,
)


def die(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


def print_device(device) -> None:
    print(f"device={device.devnode}")
    print(f"sysfs={device.sysfs_name}")
    print(f"hid_id={device.hid_id or '<unknown>'}")
    print(f"hid_name={device.hid_name or '<unknown>'}")
    print(f"hid_phys={device.hid_phys or '<unknown>'}")


def print_zone_summary(zone_colors: list[str], brightness: int) -> None:
    for index, color in enumerate(zone_colors, start=1):
        print(f"zone{index}={color}")
    print(f"brightness={brightness}")


def print_send_result(result: dict) -> None:
    print_device(result["device"])
    for index, payload in enumerate(result["payloads"], start=1):
        print(f"payload_{index}={payload}")
    if result.get("dry_run"):
        print("dry_run=yes")
    for index, payload in enumerate(result.get("write_returns", []), start=1):
        print(f"write_return_{index}={payload}")


def command_detect(args: argparse.Namespace) -> int:
    devices = list_hidraw_devices()
    if not devices:
        return die("no hidraw devices found in /sys/class/hidraw")
    for device in devices:
        print(f"[{device.sysfs_name}]")
        print_device(device)
        print()
    return 0


def command_status(args: argparse.Namespace) -> int:
    try:
        status = feature_status(args.hidraw)
    except (RuntimeError, FileNotFoundError) as exc:
        return die(str(exc))
    print_device(status["device"])
    if status.get("needs_root"):
        print("note: run with sudo to read feature reports")
        return 0
    for report_id in sorted(FEATURE_LENGTHS):
        print(f"feature_0x{report_id:02x}={status['reports'].get(report_id, '')}")
    return 0


def command_set_all(args: argparse.Namespace) -> int:
    try:
        result = apply_keyboard_single_color(
            args.hidraw,
            args.color,
            args.brightness,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        return die(str(exc))
    print_send_result(result)
    return 0


def command_set_zone(args: argparse.Namespace) -> int:
    try:
        result = apply_keyboard_zone(
            args.hidraw,
            args.zone,
            args.color,
            args.brightness,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        return die(str(exc))
    print_send_result(result)
    return 0


def command_set_zones(args: argparse.Namespace) -> int:
    try:
        result = apply_keyboard_static(
            args.hidraw,
            [args.zone1, args.zone2, args.zone3, args.zone4],
            args.brightness,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        return die(str(exc))
    print_send_result(result)
    return 0


def command_list_presets(args: argparse.Namespace) -> int:
    for name, preset in BUILTIN_PRESETS.items():
        print(f"[{name}]")
        print_zone_summary(preset["zones"], preset["brightness"])
        print()
    return 0


def command_preset(args: argparse.Namespace) -> int:
    preset = BUILTIN_PRESETS[args.name]
    brightness = args.brightness if args.brightness is not None else preset["brightness"]
    try:
        result = apply_keyboard_static(
            args.hidraw,
            preset["zones"],
            brightness,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        return die(str(exc))
    print(f"preset={args.name}")
    print_zone_summary(preset["zones"], brightness)
    print_send_result(result)
    return 0


def command_list_profiles(args: argparse.Namespace) -> int:
    profiles = list_keyboard_profiles()
    if not profiles:
        print("no keyboard profiles found")
        return 0
    for path in profiles:
        try:
            data = load_keyboard_profile(path.stem)
            print(f"[{path.stem}]")
            print_zone_summary(data["zones"], data["brightness"])
            print()
        except RuntimeError as exc:
            print(f"[{path.stem}]")
            print(f"error={exc}")
            print()
    return 0


def command_save_profile(args: argparse.Namespace) -> int:
    try:
        path = save_keyboard_profile(
            args.name,
            args.brightness,
            [args.zone1, args.zone2, args.zone3, args.zone4],
        )
        data = load_keyboard_profile(path.stem)
    except Exception as exc:
        return die(str(exc))
    print(f"saved_profile={path}")
    print_zone_summary(data["zones"], data["brightness"])
    return 0


def command_show_profile(args: argparse.Namespace) -> int:
    try:
        data = load_keyboard_profile(args.name)
    except Exception as exc:
        return die(str(exc))
    print(f"profile={data['name']}")
    print(f"path={data['path']}")
    print_zone_summary(data["zones"], data["brightness"])
    return 0


def command_apply_profile(args: argparse.Namespace) -> int:
    try:
        data = load_keyboard_profile(args.name)
        result = apply_keyboard_static(
            args.hidraw,
            data["zones"],
            data["brightness"],
            dry_run=args.dry_run,
        )
    except Exception as exc:
        return die(str(exc))
    print(f"profile={data['name']}")
    print(f"path={data['path']}")
    print_zone_summary(data["zones"], data["brightness"])
    print_send_result(result)
    return 0


def command_effect(args: argparse.Namespace) -> int:
    try:
        if args.device == "keyboard":
            if args.effect == "static":
                result = apply_keyboard_single_color(
                    args.hidraw,
                    args.color,
                    args.brightness,
                    dry_run=args.dry_run,
                )
            else:
                result = apply_keyboard_effect(
                    args.hidraw,
                    args.effect,
                    args.brightness,
                    args.speed,
                    args.direction,
                    dry_run=args.dry_run,
                )
        elif args.device == "lid":
            if args.effect == "static":
                result = apply_lid_static(
                    args.hidraw,
                    args.color,
                    args.brightness,
                    dry_run=args.dry_run,
                )
            else:
                result = apply_lid_effect(
                    args.hidraw,
                    args.effect,
                    args.brightness,
                    args.speed,
                    dry_run=args.dry_run,
                )
        else:
            return die(f"device not supported yet by CLI: {args.device}")
    except Exception as exc:
        return die(str(exc))
    print_send_result(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Linux Predator Sense Keyboard CLI for Acer Predator RGB control."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect", help="list hidraw devices")
    detect_parser.set_defaults(func=command_detect)

    status_parser = subparsers.add_parser("status", help="show detected RGB device and feature reports")
    status_parser.add_argument("--hidraw", help="manual hidraw device path, for example /dev/hidraw2")
    status_parser.set_defaults(func=command_status)

    set_all_parser = subparsers.add_parser("set-all", help="set a single static color on all keyboard zones")
    set_all_parser.add_argument("color", help="hex color, for example 00aaff")
    set_all_parser.add_argument("brightness", nargs="?", type=int, default=100)
    set_all_parser.add_argument("--hidraw", help="manual hidraw device path")
    set_all_parser.add_argument("--dry-run", action="store_true")
    set_all_parser.set_defaults(func=command_set_all)

    set_zone_parser = subparsers.add_parser("set-zone", help="set one keyboard zone and turn the others off")
    set_zone_parser.add_argument("zone", choices=("1", "2", "3", "4"))
    set_zone_parser.add_argument("color")
    set_zone_parser.add_argument("brightness", nargs="?", type=int, default=100)
    set_zone_parser.add_argument("--hidraw", help="manual hidraw device path")
    set_zone_parser.add_argument("--dry-run", action="store_true")
    set_zone_parser.set_defaults(func=command_set_zone)

    set_zones_parser = subparsers.add_parser("set-zones", help="set four keyboard zones")
    set_zones_parser.add_argument("zone1")
    set_zones_parser.add_argument("zone2")
    set_zones_parser.add_argument("zone3")
    set_zones_parser.add_argument("zone4")
    set_zones_parser.add_argument("brightness", nargs="?", type=int, default=100)
    set_zones_parser.add_argument("--hidraw", help="manual hidraw device path")
    set_zones_parser.add_argument("--dry-run", action="store_true")
    set_zones_parser.set_defaults(func=command_set_zones)

    list_presets_parser = subparsers.add_parser("list-presets", help="show built-in static keyboard presets")
    list_presets_parser.set_defaults(func=command_list_presets)

    preset_parser = subparsers.add_parser("preset", help="apply a built-in static keyboard preset")
    preset_parser.add_argument("name", choices=tuple(BUILTIN_PRESETS))
    preset_parser.add_argument("brightness", nargs="?", type=int)
    preset_parser.add_argument("--hidraw", help="manual hidraw device path")
    preset_parser.add_argument("--dry-run", action="store_true")
    preset_parser.set_defaults(func=command_preset)

    list_profiles_parser = subparsers.add_parser("list-profiles", help="list saved keyboard profiles")
    list_profiles_parser.set_defaults(func=command_list_profiles)

    save_profile_parser = subparsers.add_parser("save-profile", help="save a 4-zone keyboard profile")
    save_profile_parser.add_argument("name")
    save_profile_parser.add_argument("zone1")
    save_profile_parser.add_argument("zone2")
    save_profile_parser.add_argument("zone3")
    save_profile_parser.add_argument("zone4")
    save_profile_parser.add_argument("brightness", nargs="?", type=int, default=100)
    save_profile_parser.set_defaults(func=command_save_profile)

    show_profile_parser = subparsers.add_parser("show-profile", help="show one keyboard profile")
    show_profile_parser.add_argument("name")
    show_profile_parser.set_defaults(func=command_show_profile)

    apply_profile_parser = subparsers.add_parser("apply-profile", help="apply one keyboard profile")
    apply_profile_parser.add_argument("name")
    apply_profile_parser.add_argument("--hidraw", help="manual hidraw device path")
    apply_profile_parser.add_argument("--dry-run", action="store_true")
    apply_profile_parser.set_defaults(func=command_apply_profile)

    effect_parser = subparsers.add_parser("effect", help="send an effect to keyboard or lid")
    effect_parser.add_argument("effect", choices=tuple({*SUPPORTED_EFFECTS_BY_DEVICE["keyboard"], *SUPPORTED_EFFECTS_BY_DEVICE["lid"]}))
    effect_parser.add_argument("--device", choices=("keyboard", "lid", "button"), default="keyboard")
    effect_parser.add_argument("--brightness", type=int, required=True)
    effect_parser.add_argument("--speed", type=int, default=0)
    effect_parser.add_argument("--direction", choices=("none", "right", "left"), default="none")
    effect_parser.add_argument("--color", default="000000", help="hex color for static")
    effect_parser.add_argument("--hidraw", help="manual hidraw device path")
    effect_parser.add_argument("--dry-run", action="store_true")
    effect_parser.set_defaults(func=command_effect)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)
