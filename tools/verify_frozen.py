"""Verify the checksums recorded for the frozen result set."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def read_manifest(manifest_path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise ValueError(f"invalid manifest line {line_number}: {line!r}")
        entries.append((parts[0].lower(), parts[1]))
    return entries


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root: Path) -> list[str]:
    manifest_path = root / "MANIFEST.sha256"
    failures: list[str] = []
    for expected, relative_name in read_manifest(manifest_path):
        path = root / relative_name
        if not path.is_file():
            failures.append(f"missing: {relative_name}")
            continue
        actual = sha256(path)
        if actual != expected:
            failures.append(f"mismatch: {relative_name}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "results_v1_frozen",
        help="frozen results directory (default: results_v1_frozen)",
    )
    args = parser.parse_args()

    failures = verify(args.root.resolve())
    if failures:
        print("Frozen results verification failed:")
        print("\n".join(failures))
        return 1
    print(f"Frozen results verified: {args.root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())