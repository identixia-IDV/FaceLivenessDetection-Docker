#!/usr/bin/env python3
"""Open the Gradio demo. Start run_server.py first."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UTF8 = False


def main() -> int:
    os.chdir(ROOT)
    if UTF8:
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    print("Open the Gradio demo (API_BASE / DEMO_PORT from .env; start python run_server.py first).")
    os.execv(sys.executable, [sys.executable, str(ROOT / "demo")])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
