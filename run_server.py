#!/usr/bin/env python3
"""Start the API from this folder. Replaces run.bat / run.sh."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "lib" / "cpu"
REQUIRED = ('libFaceLivenessSDK.so', 'recognition-common.xdb', 'recognition-liveness.xdb', 'recognition-deepfake.xdb', 'libFaceLivenessEngine.so')
START = 'Starting Face Liveness API (PORT from .env or default) ...'
ERROR = (
    "ERROR: ./lib/cpu/ is incomplete.\n"
    "Need: libFaceLivenessSDK.so, recognition-common.xdb, recognition-liveness.xdb, recognition-deepfake.xdb, libFaceLivenessEngine.so.\n"
    "Download the runtime zip from https://github.com/identixia-IDV/FaceLivenessDetection-Docker/releases/latest and unzip it into ./lib/cpu/.\n"
    "A Docker Hub image already includes the runtime.\n"
)
PRELOAD = None
LIBRARY_PATH = True
FETCH = True
NEED_USB = True


def _missing() -> list[str]:
    return [name for name in REQUIRED if not (LIB / name).is_file()]


def main() -> int:
    os.chdir(ROOT)
    missing = _missing()
    if missing:
        print(ERROR, file=sys.stderr)
        return 1
    if NEED_USB and not (LIB / "libusb-0.1.so.4").exists():
        print("ERROR: ./lib/cpu/libusb-0.1.so.4 is missing from the shipped runtime.", file=sys.stderr)
        print("Download the runtime zip from Releases into ./lib/cpu/, or use Docker Hub. Do not apt-install these libraries.", file=sys.stderr)
        return 1
    if os.name == "nt":
        os.environ["PATH"] = str(LIB) + os.pathsep + os.environ.get("PATH", "")
    if LIBRARY_PATH:
        old = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = str(LIB) + ((":" + old) if old else "")
    if PRELOAD:
        old = os.environ.get("LD_PRELOAD", "")
        pre = str(LIB / PRELOAD)
        os.environ["LD_PRELOAD"] = pre + ((":" + old) if old else "")
    print(START)
    os.execv(sys.executable, [sys.executable, str(ROOT / "server")])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
