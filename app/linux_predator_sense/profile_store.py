import json
from pathlib import Path

from .constants import APP_PROFILES_DIR, KEYBOARD_PROFILES_DIR, SETTINGS_PATH
from .hid_backend import normalize_hex_color, normalize_profile_name, validate_brightness
from .models import AppProfile


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def keyboard_profile_path(name: str) -> Path:
    return KEYBOARD_PROFILES_DIR / f"{normalize_profile_name(name)}.json"


def list_keyboard_profiles() -> list[Path]:
    ensure_dir(KEYBOARD_PROFILES_DIR)
    return sorted(KEYBOARD_PROFILES_DIR.glob("*.json"))


def save_keyboard_profile(name: str, brightness: int, zones: list[str]) -> Path:
    ensure_dir(KEYBOARD_PROFILES_DIR)
    normalized_name = normalize_profile_name(name)
    validate_brightness(brightness)
    payload = {
        "name": normalized_name,
        "kind": "keyboard-static-4zone",
        "brightness": brightness,
        "zones": [normalize_hex_color(zone) for zone in zones],
    }
    path = keyboard_profile_path(normalized_name)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def load_keyboard_profile(name: str) -> dict:
    path = keyboard_profile_path(name)
    if not path.exists():
        raise RuntimeError(f"profile not found: {path.name}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid profile json: {path.name}") from exc
    zones = data.get("zones")
    brightness = data.get("brightness")
    if not isinstance(zones, list) or len(zones) != 4:
        raise RuntimeError(f"profile must contain 4 zones: {path.name}")
    if not isinstance(brightness, int):
        raise RuntimeError(f"profile must contain numeric brightness: {path.name}")
    return {
        "name": data.get("name", normalize_profile_name(name)),
        "brightness": brightness,
        "zones": [normalize_hex_color(zone) for zone in zones],
        "path": str(path),
    }


def app_profile_path(name: str) -> Path:
    return APP_PROFILES_DIR / f"{normalize_profile_name(name)}.json"


def list_app_profiles() -> list[Path]:
    ensure_dir(APP_PROFILES_DIR)
    return sorted(APP_PROFILES_DIR.glob("*.json"))


def save_app_profile(profile: AppProfile) -> Path:
    ensure_dir(APP_PROFILES_DIR)
    path = app_profile_path(profile.name)
    path.write_text(json.dumps(profile.to_dict(), indent=2) + "\n")
    return path


def delete_app_profile(name: str) -> Path:
    path = app_profile_path(name)
    if not path.exists():
        raise RuntimeError(f"app profile not found: {path.name}")
    path.unlink()
    return path


def load_app_profile(name: str) -> AppProfile:
    path = app_profile_path(name)
    if not path.exists():
        raise RuntimeError(f"app profile not found: {path.name}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid app profile json: {path.name}") from exc
    return AppProfile.from_dict(data)


def load_settings() -> dict:
    ensure_dir(SETTINGS_PATH.parent)
    if not SETTINGS_PATH.exists():
        return {"language": "pt_BR"}
    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except json.JSONDecodeError:
        return {"language": "pt_BR"}
    if not isinstance(data, dict):
        return {"language": "pt_BR"}
    return {
        "language": data.get("language", "pt_BR"),
    }


def save_settings(settings: dict) -> Path:
    ensure_dir(SETTINGS_PATH.parent)
    payload = {
        "language": settings.get("language", "pt_BR"),
    }
    SETTINGS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    return SETTINGS_PATH
