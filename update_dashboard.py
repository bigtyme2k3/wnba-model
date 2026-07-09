"""Legacy dashboard updater.

V4 owns docs/index.html now. This script is kept so older workflows do not fail.
It delegates to build_dashboard_v4.py when available and exits successfully.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if Path("build_dashboard_v4.py").exists():
        print("Legacy update_dashboard.py: delegating to Dashboard V4 builder")
        subprocess.check_call([sys.executable, "build_dashboard_v4.py"])
        return
    print("Legacy update_dashboard.py: no V4 builder found; nothing to update")


if __name__ == "__main__":
    main()
