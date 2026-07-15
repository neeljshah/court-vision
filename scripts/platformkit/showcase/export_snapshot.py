"""Proof Room snapshot exporter: builds the scrubbed static bundle.

Usage: python scripts/platformkit/showcase/export_snapshot.py [--out DIR]
Each room builder is fail-open (a broken room ships status:unavailable);
the lint gate at the end is fail-closed (violations -> exit 1, bundle kept
for inspection but reported dirty).
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.platformkit.showcase.common import BUNDLE_DIR, scrub_notes  # noqa: E402
from scripts.platformkit.showcase.lint_bundle import lint_bundle  # noqa: E402

ROOMS = ["bridge", "slate", "calibration", "claims", "graveyard",
         "machine", "ledger", "replay"]


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def export(out: Path) -> int:
    now = datetime.now(timezone.utc).isoformat()
    manifest: dict = {"generated_at_utc": now, "bundle_version": "1.1",
                      "files": {}, "counts": {}}
    for name in ROOMS:
        try:
            mod = importlib.import_module(
                f"scripts.platformkit.showcase.rooms.{name}")
            result = mod.build()
        except Exception as exc:  # fail-open per room, never fabricate
            result = {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
        result = scrub_notes(result)
        if name == "replay" and isinstance(result, dict) and "games" in result:
            for gid, game in result["games"].items():
                _write(out / "replays" / f"{gid}.json", game)
                manifest["files"][f"replays/{gid}.json"] = "replay"
            result = result.get("index", {"game_ids": list(result["games"])})
        _write(out / f"{name}.json", result)
        manifest["files"][f"{name}.json"] = (
            "unavailable" if result.get("status") == "unavailable" else "ok")
    _write(out / "manifest.json", manifest)

    violations = lint_bundle(out)
    if violations:
        print(f"LINT FAILED ({len(violations)}):")
        for v in violations[:50]:
            print(f"  - {v}")
        return 1
    ok = sum(1 for v in manifest["files"].values() if v != "unavailable")
    print(f"bundle OK at {out} ({ok}/{len(manifest['files'])} files ok, lint clean)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=BUNDLE_DIR)
    return export(ap.parse_args().out)


if __name__ == "__main__":
    raise SystemExit(main())
