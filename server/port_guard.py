"""Stop a leftover listener so a restart can bind the same port."""
from __future__ import annotations

import os
import socket
import subprocess
import time


def _busy(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("0.0.0.0", int(port)))
    except OSError:
        return True
    finally:
        sock.close()
    return False


def _pids(port: int) -> set[int]:
    found: set[int] = set()
    me = os.getpid()
    if os.name == "nt":
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
        for line in out.splitlines():
            if "LISTENING" not in line:
                continue
            parts = line.split()
            if len(parts) < 5 or not parts[-1].isdigit():
                continue
            if parts[1].rsplit(":", 1)[-1] == str(port) and int(parts[-1]) != me:
                found.add(int(parts[-1]))
        return found
    for cmd in (
        ["ss", "-lptn", f"sport = :{port}"],
        ["lsof", "-nP", "-iTCP:%d" % port, "-sTCP:LISTEN"],
    ):
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            continue
        text = out.replace("pid=", " ").replace(",", " ")
        for token in text.split():
            if token.isdigit() and int(token) != me:
                found.add(int(token))
    return found


def free_port(port: int) -> None:
    if not _busy(port):
        return
    print(f"Port {port} is in use. Stopping the previous listener so this start can bind.")
    for pid in _pids(port):
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid), "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(["kill", "-TERM", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if not _busy(port):
            return
        time.sleep(0.1)
