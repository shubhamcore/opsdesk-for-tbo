"""Re-export the root fixtures so `pytest backend/tests` works on its own."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.conftest import *  # noqa: F401,F403,E402
