"""Compose the ``harness_health`` MCP artifact from existing validation outputs.

The MCP tool ``harness_health`` (scripts/platformkit/mcp_server/artifact_tools.py)
reads data/frontend/analytics/harness_health.json and returned no_data because no
producer ever wrote it. This module is that producer.

Read-only composition: every value is copied from an artifact another producer
already wrote, except the golden section, which the frozen offline gate recomputes
on the committed SYNTHETIC fixture (a reproducibility anchor, not a calibration
claim). An absent input yields {"status": "no_data", "path": ...} for that section
-- never an exception, never an invented number. The FWER ledger is read, never
written. Calibration language only: verdicts are BEATS / MATCHES / BEHIND.

    python -m scripts.platformkit.eval_gate.harness_health_report
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[3]

# the FIRST path the harness_health handler tries
OUT_REL = "data/frontend/analytics/harness_health.json"
GOLDEN_REL = "tests/fixtures/golden/game_states.json"
NULL_SHIP_REL = "scripts/platformkit/eval_gate/post_hardening_revalidation_report.txt"
RETRO_REL = "scripts/platformkit/eval_gate/retro_correction_report.txt"
FWER_REL = "data/cache/eval_gate/backtest_fwer.jsonl"
MANIFEST_REL = "data/cache/eval_gate/gate_manifest.json"

_KV = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)")
_GOLDEN_KEEP = ("corpus", "n", "brier_model", "brier_close", "bss", "ece",
                "sharpness", "verdict", "regressed", "ship_eligible", "status")


_RESERVED = ("status", "path", "as_of", "note")


def _no_data(rel: str, note: str = "artifact absent or unreadable") -> Dict[str, Any]:
    return {"status": "no_data", "path": rel, "note": note}


def _merge(section: Dict[str, Any], scalars: Dict[str, Any]) -> Dict[str, Any]:
    """Fold a report's own key=value scalars in without clobbering the section keys.

    The null-ship report carries its own `status=FINAL`, which must not overwrite the
    section's ok/no_data status; it is preserved verbatim as `report_status`.
    """
    for key in _RESERVED:
        if key in scalars:
            scalars["report_" + key] = scalars.pop(key)
    section.update(scalars)
    return section


def _num(text: str) -> Any:
    """Copy a scalar verbatim, typed when it is plainly numeric."""
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def _stamp(path: Path, payload: Any = None) -> str:
    """The artifact's OWN timestamp: a declared field when it carries one, else mtime."""
    if isinstance(payload, dict):
        for key in ("as_of", "generated_at", "updated_at", "created_at"):
            if payload.get(key):
                return str(payload[key])
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _golden(root: Path) -> Dict[str, Any]:
    """Score the frozen golden fixture through the unmodified offline gate (~8 s)."""
    path = root / GOLDEN_REL
    if not path.is_file():
        return _no_data(GOLDEN_REL, "golden fixture absent")
    try:
        from scripts.platformkit.eval_gate.offline_predict import offline_predict_fn
        from scripts.platformkit.eval_gate.run_gate import (gate_exit_code,
                                                            run_gate_in_process)
        rows = run_gate_in_process(offline_predict_fn, golden_path=str(path))
    except Exception as exc:  # never raise out of a composer
        return _no_data(GOLDEN_REL, "gate run failed: {0}".format(exc))
    return {"status": "ok", "path": GOLDEN_REL, "as_of": _stamp(path, _read_json(path)),
            "note": "recomputed by run_gate_in_process on the SYNTHETIC fixture; "
                    "regression/leak anchor, not a calibration claim",
            "exit_code": gate_exit_code(rows),
            "corpora": [{k: r[k] for k in _GOLDEN_KEEP if k in r} for r in rows]}


def _null_ship(root: Path) -> Dict[str, Any]:
    """null_ship_calibration.py's persisted report (its first block)."""
    path = root / NULL_SHIP_REL
    if not path.is_file():
        return _no_data(NULL_SHIP_REL)
    block = path.read_text(encoding="ascii", errors="replace").split("\n\n")[0]
    scalars: Dict[str, Any] = {}
    exploits = []
    for line in block.splitlines():
        pairs = {k: _num(v) for k, v in _KV.findall(line)}
        if not pairs:
            continue
        (exploits.append(pairs) if line.startswith("exploit=") else scalars.update(pairs))
    out = _merge({"status": "ok", "path": NULL_SHIP_REL, "as_of": _stamp(path)}, scalars)
    out["exploits"] = exploits
    return out


def _retro(root: Path) -> Dict[str, Any]:
    """retro_correction.py's persisted report; only its footer carries key=value."""
    path = root / RETRO_REL
    if not path.is_file():
        return _no_data(RETRO_REL)
    text = path.read_text(encoding="ascii", errors="replace")
    return _merge({"status": "ok", "path": RETRO_REL, "as_of": _stamp(path)},
                  {k: _num(v) for k, v in _KV.findall(text)})


def _fwer(root: Path) -> Dict[str, Any]:
    """READ-ONLY summary of the multiplicity ledger. This module never appends."""
    path = root / FWER_REL
    if not path.is_file():
        return _no_data(FWER_REL)
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    ks = [r.get("k_cumulative") for r in rows
          if isinstance(r, dict) and isinstance(r.get("k_cumulative"), int)]
    ats = sorted(str(r["at"]) for r in rows if isinstance(r, dict) and r.get("at"))
    return {"status": "ok", "path": FWER_REL, "as_of": ats[-1] if ats else _stamp(path),
            "rows": len(rows), "k_cumulative_max": max(ks) if ks else None,
            "last_at": ats[-1] if ats else None}


def _manifest(root: Path) -> Dict[str, Any]:
    path = root / MANIFEST_REL
    payload = _read_json(path)
    if payload is None:
        return _no_data(MANIFEST_REL)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    rows = rows if isinstance(rows, list) else []
    ok = sum(1 for r in rows if isinstance(r, dict) and r.get("status") == "OK")
    return {"status": "ok", "path": MANIFEST_REL, "as_of": _stamp(path, payload),
            "rows_ok": ok, "rows_unreadable": len(rows) - ok,
            "note": "rows_unreadable counts every row whose status is not OK"}


def build(out_path: Optional[str] = None, root: Path = ROOT) -> Dict[str, Any]:
    """Compose the five sections, write the artifact, return the payload."""
    sections = {"golden": _golden(root), "null_ship": _null_ship(root),
                "retro_correction": _retro(root), "fwer_ledger": _fwer(root),
                "gate_manifest": _manifest(root)}
    stamps = {name: sec["as_of"] for name, sec in sections.items() if sec.get("as_of")}
    newest = max(stamps, key=lambda k: stamps[k]) if stamps else None
    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": stamps[newest] if newest else None,
        "as_of_source": newest,
        "as_of_note": "max of the composed artifacts' own timestamps, not the wall clock",
        "source_artifact": [sec["path"] for sec in sections.values()],
        "status": "ok",
    }
    payload.update(sections)
    # aliases the harness_health handler reads by name
    payload["retro_correction_survivors"] = sections["retro_correction"].get("survivors")
    payload["multiplicity_ledger_K"] = sections["fwer_ledger"].get("k_cumulative_max")
    out = Path(out_path) if out_path else root / OUT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                   encoding="ascii")
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="compose the harness_health MCP artifact")
    ap.add_argument("--out", default=None, help="output path (default: " + OUT_REL + ")")
    args = ap.parse_args(argv)
    payload = build(args.out)
    print("harness_health artifact -- composed sections")
    for name in ("golden", "null_ship", "retro_correction", "fwer_ledger", "gate_manifest"):
        sec = payload[name]
        print("  {0:<18} {1:<8} {2}".format(name, sec["status"], sec["path"]))
    print("  as_of {0} (from {1})".format(payload["as_of"], payload["as_of_source"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
