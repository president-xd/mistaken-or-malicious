"""CLI entry point:  python -m p2p <config.yaml> [--share answer|both]"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .config import SHARE_MODES, load_config
from .network import run_network

# Models emit unicode (e.g. the × sign); keep Windows terminals from mangling it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m p2p",
        description="Run a peer-to-peer network of agents over a YAML config.",
    )
    parser.add_argument("config", help="path to the YAML config file")
    parser.add_argument(
        "--share",
        choices=SHARE_MODES,
        default=None,
        help="what each peer sends to its neighbours: "
             "'answer' = its conclusion only (default); "
             "'both' = its conclusion AND its reasoning. "
             "Overrides the 'share' key in the config file.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config, share=args.share)
    try:
        asyncio.run(run_network(cfg))
    except Exception as exc:  # noqa: BLE001 - surface a friendly hint for the common case
        text = str(exc).lower()
        if any(k in text for k in ("connect", "refused", "11434", "connection")):
            raise SystemExit(
                "\nCannot reach Ollama at http://localhost:11434.\n"
                "Start the server with `ollama serve` and make sure the model is "
                "pulled (`ollama pull <model>`). See README.md.\n"
                f"\noriginal error: {exc}"
            )
        raise


if __name__ == "__main__":
    main()
