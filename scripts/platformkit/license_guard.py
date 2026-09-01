"""Read-only AST guard for dependencies unsuitable for shipping."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


DENYLIST = {
    "ultralytics": "AGPL-3.0", "boxmot": "AGPL-3.0", "strongsort": "GPL-3.0",
    "sn_gamestate": "GPL-3.0", "statsapi": "GPL-3.0", "mlb_statsapi": "GPL-3.0",
    "deep_eiou": "NO-LICENSE", "tenniscourtdetector": "NO-LICENSE",
    "gtr": "NO-LICENSE", "baseballcv": "NO-LICENSE",
}
SHIPPING_PATHS = (Path("domains"), Path("scripts") / "platformkit")


@dataclass(frozen=True)
class LicenseFinding:
    file: str
    line: int
    module: str
    license: str
    verdict: str = "DENY"

    def to_json(self) -> str:
        """Return the required JSON row."""
        return json.dumps(asdict(self), sort_keys=True)


def _normalise(module: str) -> str:
    return module.split(".", 1)[0].replace("-", "_").lower()


def _shipping_files(root: Path) -> Iterable[Path]:
    for relative in SHIPPING_PATHS:
        directory = root / relative
        if directory.is_dir():
            yield from (path for path in directory.rglob("*.py") if not path.name.startswith("test_"))


def tree_sha256(root: str | Path) -> dict[str, str]:
    """Hash the scanner's input set so callers can assert read-only behaviour."""
    root_path = Path(root).resolve()
    return {path.relative_to(root_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(_shipping_files(root_path))}


def scan(root: str | Path) -> list[LicenseFinding]:
    """Return denylisted imports reachable from platform shipping paths."""
    root_path = Path(root).resolve()
    findings: list[LicenseFinding] = []
    for path in sorted(_shipping_files(root_path)):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                key = _normalise(module)
                if key in DENYLIST:
                    findings.append(LicenseFinding(path.relative_to(root_path).as_posix(), node.lineno,
                                                   module, DENYLIST[key]))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    """Print JSON findings and return nonzero if a shipping import is denied."""
    parser = argparse.ArgumentParser(description="Scan shipping modules for denied imports.")
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    findings = scan(args.root)
    for finding in findings:
        print(finding.to_json())
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
