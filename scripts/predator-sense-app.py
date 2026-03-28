#!/usr/bin/env python3

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

try:
    from linux_predator_sense.gui_app import main  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover - startup message
    missing = exc.name or "PySide6"
    print(
        f"error: missing dependency {missing}. Install the Debian package first, for example:\n"
        "  sudo apt install python3-pyside6.qtwidgets",
        file=sys.stderr,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    raise SystemExit(main())
