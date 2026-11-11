"""JOURNEY E — Product intelligence and 50,000-row export.

Runs against a live server:  python -m simulation.journey_e [base_url]
"""
from __future__ import annotations

import sys

from simulation.engine import pretty
from simulation.journeys import journey_e


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    result = journey_e(base_url)
    print(pretty(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
