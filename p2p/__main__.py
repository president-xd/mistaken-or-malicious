"""CLI entry point:  python -m p2p <config.yaml>"""

from __future__ import annotations

import asyncio
import sys

from .config import load_config
from .network import run_network

# Models emit unicode (e.g. the × sign); keep Windows terminals from mangling it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m p2p <config.yaml>")

    cfg = load_config(sys.argv[1])
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
