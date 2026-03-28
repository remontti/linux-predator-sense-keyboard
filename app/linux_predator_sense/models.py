from dataclasses import dataclass, field


@dataclass
class HidrawDevice:
    devnode: str
    sysfs_name: str
    hid_id: str
    hid_name: str
    hid_phys: str

    @property
    def vendor_product(self) -> tuple[str, str]:
        parts = self.hid_id.split(":")
        if len(parts) != 3:
            return "", ""
        return parts[1][-4:].lower(), parts[2][-4:].lower()


@dataclass
class KeyboardState:
    effect: str = "static"
    brightness: int = 70
    speed: int = 5
    direction: str = "right"
    zones: list[str] = field(
        default_factory=lambda: ["00aaff", "00aaff", "00aaff", "00aaff"]
    )

    def to_dict(self) -> dict:
        return {
            "effect": self.effect,
            "brightness": self.brightness,
            "speed": self.speed,
            "direction": self.direction,
            "zones": list(self.zones),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeyboardState":
        return cls(
            effect=data.get("effect", "static"),
            brightness=int(data.get("brightness", 70)),
            speed=int(data.get("speed", 5)),
            direction=data.get("direction", "right"),
            zones=list(data.get("zones", ["00aaff"] * 4)),
        )


@dataclass
class LidState:
    effect: str = "static"
    brightness: int = 70
    speed: int = 4
    color: str = "00aaff"

    def to_dict(self) -> dict:
        return {
            "effect": self.effect,
            "brightness": self.brightness,
            "speed": self.speed,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LidState":
        return cls(
            effect=data.get("effect", "static"),
            brightness=int(data.get("brightness", 70)),
            speed=int(data.get("speed", 4)),
            color=data.get("color", "00aaff"),
        )


@dataclass
class AppProfile:
    name: str
    keyboard: KeyboardState = field(default_factory=KeyboardState)
    lid: LidState = field(default_factory=LidState)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": "linux-predator-sense-app-profile",
            "keyboard": self.keyboard.to_dict(),
            "lid": self.lid.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppProfile":
        return cls(
            name=data.get("name", "profile"),
            keyboard=KeyboardState.from_dict(data.get("keyboard", {})),
            lid=LidState.from_dict(data.get("lid", {})),
        )
