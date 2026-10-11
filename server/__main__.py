"""Entry: ``python server`` (or ``python -m server``) from the App root."""
from __future__ import annotations

import sys
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent
_ROOT = _SERVER_DIR.parent
# This directory first so ``import app`` is the Flask server.
if sys.path[:1] != [str(_SERVER_DIR)]:
    sys.path.insert(0, str(_SERVER_DIR))
for _p in (_ROOT, _ROOT / "sdk"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.append(_s)

def _load_env() -> None:
    """Load repo-root ``.env`` without overriding real process env.

    Prefers python-dotenv when installed; otherwise parses KEY=VALUE lines so
    LICENSE is always available at bootstrap even in minimal venvs.
    """
    env_path = _ROOT / ".env"
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None  # type: ignore[assignment]
    if load_dotenv is not None:
        load_dotenv(env_path, override=False)
        return
    if not env_path.is_file():
        return
    import os
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        os.environ[key] = val



_load_env()

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
