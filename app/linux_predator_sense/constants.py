import os
from pathlib import Path


RGB_FEATURE_ID = 0xA4

APP_DISPLAY_NAME = "Linux Predator Sense Keyboard"
APP_SHORT_NAME = "Linux"
APP_SLUG = "linux-predator-sense-keyboard"

DEVICE_IDS = {
    "keyboard": 0x21,
    "lid": 0x83,
    "button": 0x65,
}

EFFECT_IDS = {
    "static": 0x02,
    "breathing": 0x04,
    "neon": 0x05,
    "wave": 0x07,
    "ripple": 0x08,
    "zoom": 0x09,
    "snake": 0x0A,
    "disco": 0x0B,
    "shifting": 0xFF,
}

DIRECTION_IDS = {
    "none": 0x00,
    "right": 0x01,
    "left": 0x02,
}

ZONE_IDS = {
    "all": 0x0F,
    "1": 0x01,
    "2": 0x02,
    "3": 0x04,
    "4": 0x08,
}

FEATURE_LENGTHS = {
    0xA1: 5,
    0xA2: 2,
    0xA3: 9,
    0xA4: 11,
}

PREFERRED_RGB_CONTROLLERS = [
    ("0cf2", "5130", "ENEK5130 RGB controller"),
    ("1025", "174b", "Embedded keyboard RGB controller"),
]

SUPPORTED_EFFECTS_BY_DEVICE = {
    "keyboard": (
        "static",
        "breathing",
        "neon",
        "wave",
        "ripple",
        "zoom",
        "snake",
        "disco",
        "shifting",
    ),
    "lid": (
        "static",
        "breathing",
        "neon",
    ),
}

BUILTIN_PRESETS = {
    "predator": {
        "brightness": 100,
        "zones": ["ff2a00", "ff5a00", "ff2a00", "ff5a00"],
    },
    "ocean": {
        "brightness": 70,
        "zones": ["003cff", "00aaff", "00d4ff", "7ae7ff"],
    },
    "forest": {
        "brightness": 70,
        "zones": ["0f5c2e", "1f8f49", "33bb66", "94ffb4"],
    },
    "sunset": {
        "brightness": 80,
        "zones": ["ff4d00", "ff7a00", "ff2f6d", "ffd166"],
    },
    "ice": {
        "brightness": 75,
        "zones": ["dff6ff", "9be7ff", "56cfe1", "80ffdb"],
    },
    "violet": {
        "brightness": 70,
        "zones": ["5a189a", "7b2cbf", "9d4edd", "e0aaff"],
    },
    "off": {
        "brightness": 0,
        "zones": ["000000", "000000", "000000", "000000"],
    },
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
ICON_PATH = ASSETS_DIR / "linux-predator-sense-keyboard.svg"
AUTHOR_LOGO_PATH = ASSETS_DIR / "logo-remontti.svg"

_xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
if _xdg_config_home:
    APP_CONFIG_DIR = Path(_xdg_config_home) / APP_SLUG
else:
    APP_CONFIG_DIR = Path.home() / ".config" / APP_SLUG

KEYBOARD_PROFILES_DIR = APP_CONFIG_DIR / "keyboard-profiles"
APP_PROFILES_DIR = APP_CONFIG_DIR / "profiles"
SETTINGS_PATH = APP_CONFIG_DIR / "settings.json"
