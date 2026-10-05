"""Generate the ring study configs and their run manifests."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml


SCENARIOS = {
    "S1": [0],
    "S2": [0, 1],
    "S3": [0, 3],
    "S4": [0, 1, 2],
    "S5": [0, 2, 4],
}

CONDITIONS = (
    ("clean_defence_off", "00_clean", None, "off"),
    ("clean_defence_on", "00_clean", None, "broadcast"),
    ("attack_defence_off", "01_attack_defence_off", "scenario", "off"),
    ("attack_defence_on", "02_attack_defence_on", "scenario", "broadcast"),
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def package_versions() -> dict[str, str]:
    names = ("autogen-agentchat", "autogen-core", "autogen-ext", "PyYAML")
    return {
        name: importlib.metadata.version(name)
        for name in names
        if _installed(name)
    }


def _installed(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def write_manifest(folder: Path, config_path: Path, question_path: Path,
                   model: str, seed: int, repeats: int, commit: str) -> None:
    manifest = {
        "git_commit": commit,
        "config_sha256": digest(config_path),
        "model": model,
        "date": datetime.now(timezone.utc).isoformat(),
        "seeds": [seed + index for index in range(repeats)],
        "package_versions": package_versions(),
        "questions_sha256": digest(question_path),
    }
    (folder / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def generate(root: Path, output_root: Path) -> list[Path]:
    base_path = root / "configs" / "ring" / "base.yaml"
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    question_path = root / base["questions_file"]
    commit = git_commit(root)
    generated: list[Path] = []

    for condition_name, condition_dir, scenario_mode, trust_share in CONDITIONS:
        scenarios = ([("", [])] if scenario_mode is None
                     else list(SCENARIOS.items()))
        for scenario, seats in scenarios:
            settings = dict(base)
            settings.update({
                "attackers": len(seats),
                "attacker_places": ",".join(str(seat) for seat in seats),
                "trust_share": trust_share,
            })
            if scenario:
                folder = output_root / condition_dir / scenario
                run_name = f"ring_{condition_name}_{scenario}"
            else:
                folder = output_root / condition_dir / condition_name
                run_name = f"ring_{condition_name}"
            folder.mkdir(parents=True, exist_ok=True)
            settings["run_name"] = run_name
            settings["results_dir"] = str(folder.relative_to(root))
            config_path = folder / "config.yaml"
            config_path.write_text(
                yaml.safe_dump(settings, sort_keys=False), encoding="utf-8"
            )
            write_manifest(folder, config_path, question_path,
                           settings["model"], settings["seed"],
                           settings["repeats"], commit)
            generated.append(config_path)
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / "results" / "ring").resolve()
    generated = generate(root, output)
    print(f"Generated {len(generated)} configs under {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())