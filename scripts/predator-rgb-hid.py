#!/usr/bin/env python3

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from linux_predator_sense.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
