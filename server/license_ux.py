#!/usr/bin/env python3
"""
Identixia customer license UX (Linux / Docker API servers).


Canonical copy: Identixia org kit → templates/linux-api/license_ux.py
Scaffold copies this into each new *-Linux repository. Keep behavior identical.


Activation methods (all supported):
  1. LICENSE=… in repo-root .env (or process env)
  2. POST /api/activate (writes LICENSE into .env)
  3. Interactive terminal paste — up to LICENSE_ATTEMPTS tries when
     activation fails (or no license yet), only if stdin is a TTY


Docker note: `docker compose up -d` has no TTY → interactive prompt is skipped.
Use `docker compose run --rm -it sdk …`, local `python run_server.py` / `python3 run_server.py`, or POST /api/activate.
"""


from __future__ import annotations


import os
import sys
import time
from pathlib import Path
from typing import Callable


# Max interactive paste attempts after a failed / missing license.
LICENSE_ATTEMPTS = 3
# Retries when activate fails due to a lingering engine license lock.
ACTIVATE_LOCK_RETRIES = 8
ACTIVATE_LOCK_BASE_MS = 400

# Native return codes from FaceSDK_activate (see facesdk/codes.h).
ACTIVATION_OK = 0
ACTIVATION_INVALID = 1
ACTIVATION_EXPIRED = 2
ACTIVATION_ENGINE_FAILED = 3




def looks_real(text: str) -> bool:
    """Ignore empty / placeholder license values (not file paths)."""
    lines = [
        ln.strip()
        for ln in text.strip().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return False
    t = lines[0]
    if t.startswith("/") or t.startswith("./") or t.startswith("../"):
        return False
    if "PASTE_YOUR" in t or "YOUR_KEY" in t or "YOUR_LICENSE" in t:
        return False
    if t.startswith("IXL1"):
        return True
    return len(t) > 20


def _is_text_license(path: Path) -> bool:
    sample = path.read_bytes()[:8]
    return not sample.startswith(b"IXL1") and all(c < 128 for c in sample)




def _normalize_text_key(text: str) -> str:
    text = text.strip()
    import re

    m = re.match(r"[A-Za-z0-9+/]+={0,2}", text)
    return m.group(0) if m else text


def _binary_license_path(root: Path) -> Path:
    """Binary IXL1 blob beside .env (gitignored). Text keys stay in LICENSE= only."""
    return root / ".license.dat"


def upsert_env_license(root: Path, value: str) -> None:
    """Persist LICENSE=… into repo-root .env and process env."""
    env_path = root / ".env"
    value = value.strip()
    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    seen = False
    for ln in lines:
        if ln.startswith("LICENSE=") or ln.startswith("LICENSE ="):
            out.append("LICENSE=" + value)
            seen = True
        else:
            out.append(ln)
    if not seen:
        if out and out[-1].strip():
            out.append("")
        out.append("LICENSE=" + value)
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.environ["LICENSE"] = value


def find_license(root: Path) -> str | None:
    """Resolve activate() argument from LICENSE in env / .env only.

    Text keys are returned as strings (no on-disk copy). Binary license files are
    returned as absolute paths.
    """
    env = os.environ.get("LICENSE", "").strip()
    if not env:
        return None
    if (env.startswith('"') and env.endswith('"')) or (
        env.startswith("'") and env.endswith("'")
    ):
        env = env[1:-1].strip()
    if not env:
        return None

    p = Path(env).expanduser()
    if not p.is_absolute():
        cand = (root / p).resolve()
        if cand.is_file():
            p = cand
        elif p.is_file():
            pass
        else:
            p = Path(env)
    if p.is_file() and p.stat().st_size > 0:
        if p.suffix.lower() == ".dat" or not _is_text_license(p):
            return str(p)
        text = p.read_text(encoding="utf-8", errors="replace")
        if looks_real(text):
            return _normalize_text_key(text)
        return None

    if looks_real(env):
        return _normalize_text_key(env)
    return None


def save_license(root: Path, raw: bytes) -> str:
    """Save license to .env (LICENSE=). Returns the argument for activate()."""
    if raw.startswith(b"IXL1"):
        path = _binary_license_path(root)
        path.write_bytes(raw)
        upsert_env_license(root, "./.license.dat")
        return str(path)
    if all(c < 128 for c in raw[: min(64, len(raw))]):
        key = _normalize_text_key(raw.decode("utf-8", errors="replace"))
        upsert_env_license(root, key)
        return key
    path = _binary_license_path(root)
    path.write_bytes(raw)
    upsert_env_license(root, "./.license.dat")
    return str(path)


def decode_activate_body(body: bytes) -> bytes | None:
    if not body:
        return None
    if body.startswith(b"IXL1"):
        return body
    text = body.decode("utf-8", errors="replace").strip()
    if text.startswith("{"):
        try:
            import json


            obj = json.loads(text)
            if isinstance(obj, dict) and obj.get("license") is not None:
                lic = obj["license"]
                return lic.encode("utf-8") if isinstance(lic, str) else bytes(lic)
        except Exception:  # noqa: BLE001
            pass
    return text.encode("utf-8")




def can_prompt() -> bool:
    if os.environ.get("IX_NO_LICENSE_PROMPT", "").strip() in ("1", "true", "yes"):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:  # noqa: BLE001
        return False




def _say(msg: str) -> None:
    """Print a status line and flush so the customer sees it immediately."""
    print(msg, flush=True)




def print_machine_code(machine_code: str) -> None:
    """Print the machine code once, on its own lines (… is long)."""
    _say("Machine code (send this to Identixia for your license):")
    _say(machine_code)




def prompt_license_key(attempt: int, max_attempts: int) -> str | None:
    """Read one  key from the terminal. Empty / Ctrl-C → skip."""
    _say("")
    _say(
        "Paste your license key, then press Enter "
        "(attempt {0}/{1}). Press Enter alone to skip.".format(attempt, max_attempts)
    )
    try:
        line = input().strip()
    except (EOFError, KeyboardInterrupt):
        print(flush=True)
        return None
    if not line:
        return None
    return line




def activate_with_retry(
    activate: Callable[[str], int],
    license_arg: str,
    *,
    retries: int = ACTIVATE_LOCK_RETRIES,
) -> int:
    """Activate, retrying briefly if the previous process still holds the engine lock."""
    last = -1
    for attempt in range(1, retries + 1):
        last = int(activate(license_arg))
        if last == 0:
            return 0
        if attempt < retries:
            time.sleep((ACTIVATE_LOCK_BASE_MS * attempt) / 1000.0)
    return last


def interactive_activate(
    root: Path,
    activate: Callable[[str], int],
    *,
    attempts: int = LICENSE_ATTEMPTS,
) -> bool:
    """Up to `attempts` terminal pastes. Saves successful key to .env LICENSE."""
    if not can_prompt():
        return False
    _say("Enter license key")
    for i in range(1, attempts + 1):
        key = prompt_license_key(i, attempts)
        if key is None:
            _say("License entry skipped.")
            return False
        if not looks_real(key):
            _say("That does not look like an Identixia license key. Try again.")
            continue
        _say("Saving license ({0} characters) and activating…".format(len(key)))
        license_arg = save_license(root, key.encode("utf-8"))
        res = activate_with_retry(activate, license_arg)
        if res == 0:
            _say("License activated. Saved to .env (LICENSE).")
            return True
        if res == ACTIVATION_ENGINE_FAILED:
            _say(
                "License key is valid, but the native engine failed to start (code {0}). "
                "Use the official lib/cpu runtime (Docker Hub or the runtime zip from https://github.com/identixia-IDV/FaceLivenessDetection-Docker/releases/latest) — no extra apt packages needed.".format(
                    res
                )
            )
            return False
        _say("Activation failed (code {0}). Check the key and try again.".format(res))
    _say(
        "Could not activate after {0} tries. "
        "Set LICENSE in .env or POST /api/activate.".format(attempts)
    )
    return False



# Signature of the last license material we passed to activate(). Used so updating
# LICENSE in .env (or POST /api/activate) picks up the new key without a restart.
_loaded_sig: tuple | None = None
# True after init_sdk() extracted/mounted runtime packs.
_sdk_ready: bool = False




def _license_sig(license_arg: str) -> tuple:
    """Signature for reload detection. license_arg is a text key or a file path."""
    p = Path(license_arg)
    try:
        if p.is_file():
            st = p.stat()
            return ("file", str(p.resolve()), st.st_mtime_ns, st.st_size)
    except OSError:
        pass
    return ("text", license_arg)




def remember_loaded(root: Path) -> None:
    global _loaded_sig
    arg = find_license(root)
    _loaded_sig = _license_sig(arg) if arg is not None else None




def mark_sdk_ready(ready: bool = True) -> None:
    global _sdk_ready
    _sdk_ready = ready




def is_sdk_ready() -> bool:
    return _sdk_ready




def ensure_ready(
    root: Path,
    activate: Callable[[str], int],
    init_sdk: Callable[[], int],
) -> int:
    """
    Activate when LICENSE / LICENSE changes, then run init_sdk once.

    Docker compose often starts without a key, then the customer sets LICENSE
    in .env or POSTs /api/activate. Without this, activate alone never mounts
    packs and process calls return empty / failed results.
    """
    global _loaded_sig, _sdk_ready
    license_arg = find_license(root)
    if license_arg is None:
        return -1
    sig = _license_sig(license_arg)
    if sig != _loaded_sig:
        res = activate_with_retry(activate, license_arg)
        if res != 0:
            return int(res)
        _loaded_sig = sig
        _sdk_ready = False
    if _sdk_ready:
        return 0
    _say("Starting SDK (first run can take up to a minute)…")
    if init_sdk() != 0:
        _say("Engine failed to start (model extract). Check shm_size / recognition*.xdb.")
        return -2
    _say("Ready.")
    _sdk_ready = True
    return 0




def reload_if_changed(
    root: Path,
    activate: Callable[[str], int],
    init_sdk: Callable[[], int] | None = None,
) -> None:
    """Re-activate (and init SDK) when LICENSE in .env changes."""
    if init_sdk is not None:
        ensure_ready(root, activate, init_sdk)
        return
    global _loaded_sig, _sdk_ready
    license_arg = find_license(root)
    if license_arg is None:
        return
    sig = _license_sig(license_arg)
    if sig == _loaded_sig:
        return
    activate_with_retry(activate, license_arg)
    _loaded_sig = sig
    _sdk_ready = False




def bootstrap(
    root: Path,
    *,
    get_machine_code: Callable[[], str],
    activate: Callable[[str], int],
    init_sdk: Callable[[], int],
    attempts: int = LICENSE_ATTEMPTS,
) -> None:
    """
    Startup license flow for Identixia Linux API servers.


    On missing or failed license: offer up to `attempts` interactive pastes when TTY.
    Always leaves the process running so /api/machinecode and /api/activate work.
    """
    global _sdk_ready
    _sdk_ready = False
    mc = get_machine_code()
    print_machine_code(mc)


    license_arg = find_license(root)
    ok = False
    if license_arg:
        _say("Activating license from .env …")
        res = activate_with_retry(activate, license_arg)
        if res == 0:
            _say("License activated.")
            ok = True
        elif res == ACTIVATION_ENGINE_FAILED:
            _say(
                "License is valid, but the native engine failed to start (code {0}). "
                "Prefer Docker Hub, or re-run the runtime zip from https://github.com/identixia-IDV/FaceLivenessDetection-Docker/releases/latest "
                "(runtime deps are bundled — do not apt-install extra libraries).".format(
                    res
                )
            )
            ok = False
        else:
            _say("Activation failed (code {0}).".format(res))
            ok = interactive_activate(root, activate, attempts=attempts)
    else:
        _say("No LICENSE in .env yet.")
        ok = interactive_activate(root, activate, attempts=attempts)


    if not ok:
        _say(
            "Starting without a license. Use GET /api/machinecode and "
            "POST /api/activate, or set LICENSE in .env and restart."
        )
        return


    remember_loaded(root)
    _say("Starting SDK (first run can take up to a minute)…")
    if init_sdk() != 0:
        _say("Engine failed to start.")
        sys.exit(1)
    _say("Ready.")
    _sdk_ready = True
