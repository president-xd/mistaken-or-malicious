"""Start the program:  python -m p2p config.yaml [--share both] [--result json]"""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import roles
from .config import SHARE_MODES, load_config
from .network import Network, run_network
from .results import Results, already_done

# Models write characters like the multiply sign. Make sure Windows can show them.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m p2p",
        description="Run a peer-to-peer network of agents from a YAML config.")
    parser.add_argument("config", help="path to the YAML config file")
    parser.add_argument(
        "--share", choices=SHARE_MODES, default=None,
        help="what each agent sends its neighbours: 'answer' = its conclusion "
             "only; 'both' = conclusion and reasoning. Overrides the config file.")
    parser.add_argument(
        "--result", choices=["json"], default=None,
        help="save the whole run, including the performance numbers, to a JSON "
             "file in the results folder.")
    args = parser.parse_args()

    cfg = load_config(args.config, share=args.share)

    # If this run has already finished, do not do it again. Needs `run_name`.
    if cfg.skip_done:
        done = already_done(cfg.run_name)
        if done:
            print(f"[SKIP] This run is already finished: {done}\n"
                  f"       Set skip_done: false, or change run_name, to run it again.")
            return

    recorder = None
    if args.result == "json":
        # Work out the agent names and who lies, so the file header is right.
        from .agent import agent_names
        names = agent_names(cfg.agents)
        liars = roles.choose_seats(names, cfg.attackers, cfg.attacker_places,
                                   cfg.topology, cfg.seed)
        recorder = Results(cfg, names, liars)

    try:
        asyncio.run(run_network(cfg, recorder))
    except Exception as exc:  # noqa: BLE001 - give a clear hint for the usual cause
        text = str(exc).lower()
        if any(k in text for k in ("connect", "refused", "11434", "connection")):
            raise SystemExit(
                "\nCannot reach Ollama at http://localhost:11434.\n"
                "Start it with `ollama serve`, and make sure the model is pulled "
                "(`ollama pull <model>`). See README.md.\n"
                f"\noriginal error: {exc}")
        raise

    if recorder:
        path = recorder.save(run_name=cfg.run_name)
        print(f"\nResults saved to: {path}")


if __name__ == "__main__":
    main()
