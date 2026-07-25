"""Vercel ASGI entrypoint for the Augur dashboard."""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
RUNTIME_HOME = Path("/tmp/augur")

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if os.environ.get("VERCEL"):
    RUNTIME_HOME.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(RUNTIME_HOME)
    os.environ.setdefault("XDG_CACHE_HOME", str(RUNTIME_HOME / ".cache"))
    os.environ.setdefault("MPLCONFIGDIR", str(RUNTIME_HOME / ".matplotlib"))

from dashboard.app import app  # noqa: E402
