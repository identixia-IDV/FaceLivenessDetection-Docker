"""Entry: ``python demo`` (or ``python -m demo``) from the App root."""
from __future__ import annotations

import sys
from pathlib import Path

_DEMO_DIR = Path(__file__).resolve().parent
_ROOT = _DEMO_DIR.parent
# This directory first so ``import app`` is the Gradio UI.
if sys.path[:1] != [str(_DEMO_DIR)]:
    sys.path.insert(0, str(_DEMO_DIR))
for _p in (_ROOT, _ROOT / "sdk"):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.append(_s)

def _load_env() -> None:
    """Load repo-root ``.env`` without overriding real process env."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_ROOT / ".env", override=False)


_load_env()

from app import main  # noqa: E402

if __name__ == "__main__":
    main()
