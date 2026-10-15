"""Run the indicative five-question clean-vs-S2 gate after explicit approval."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm paid model calls")
    parser.add_argument("--config", default="configs/ring/base.yaml")
    parser.add_argument("--questions", default="data/questions_test_50.jsonl")
    parser.add_argument("--dump-prompts", metavar="PATH")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Refusing gate model calls. Re-run with --yes after confirming cost.")
    root = Path(__file__).resolve().parents[1]
    base = yaml.safe_load((root / args.config).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="ring_gate_", dir=root / "results") as folder:
        scores = {}
        for name, attackers in (("clean", 0), ("attack_defence_off", 2)):
            config = dict(base)
            config.update({
                "questions_file": str((root / args.questions).resolve()),
                "max_questions": 5,
                "attackers": attackers,
                "attacker_places": "0,1" if attackers else "",
                "trust_share": "off",
                "skip_done": False,
                "run_name": name,
                "results_dir": folder,
            })
            config_path = Path(folder) / f"{name}.yaml"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
            env = os.environ.copy()
            if args.dump_prompts:
                env["P2P_DUMP_AGENT"] = "Agent_C"
                env["P2P_DUMP_PROMPT"] = str(Path(args.dump_prompts).resolve())
            subprocess.run([
                str(root / "venv" / "Scripts" / "python.exe"), "-m", "p2p",
                str(config_path), "--result", "json",
            ], cwd=root, env=env, check=True)
            result = json.loads((Path(folder) / f"{name}.json").read_text(encoding="utf-8"))
            scores[name] = result.get("summary", {}).get("honest_accuracy")
        clean = scores["clean"]
        attacked = scores["attack_defence_off"]
        print(json.dumps({"clean_honest_accuracy": clean,
                          "attack_defence_off_honest_accuracy": attacked,
                          "difference": clean - attacked if clean is not None and attacked is not None else None},
                         indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())