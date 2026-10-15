"""Offline trust sanity check for responsive consistency."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p2p.trust import responsive_consist


def main() -> int:
    corrected_honest = responsive_consist("B", "A", ["A", "A", "A"], 2)
    liar = responsive_consist("B", "B", ["A", "A", "B"], 2)
    assert liar < corrected_honest
    print(f"liar={liar:.3f} corrected_honest={corrected_honest:.3f}")
    print("Known limit: a stubborn honest-wrong agent has the same behaviour "
          "signals as a stubborn liar and is not distinguishable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
