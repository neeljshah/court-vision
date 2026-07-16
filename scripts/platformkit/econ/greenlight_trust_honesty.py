"""E-SPEC/F-SPEC real computation replacing the two NOT_BUILT constants in greenlight_criteria.py
(criterion_e channel_trust_status, criterion_f cv_honesty_status). See docs/research/depth-program/
GREENLIGHT_UNCAP_SPEC_2026-07-05.md (sha-pinned, rulings R-a..R-e). Fail-closed: missing/stale/
unreadable => RED, never a hardcoded pass. Suppression-only: RED withholds, GREEN stops withholding.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/econ/test_greenlight_trust_honesty.py -q
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from typing import Any, Dict, Optional, Sequence

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from governance import policy as _pol
from governance import honesty_linter as _linter
from scripts.platformkit.autonomy import freshness_sla as _sla
from scripts.platformkit.l4.prereg_sha_stamp import compute_sha as _compute_sha

_INGAME_CHANNELS = ("paper_ingame", "paper_ingame_prop")
_Z_SIG = 2.5
_RED, _AMBER, _GREEN = "RED", "AMBER", "GREEN"

def _ops(root: str) -> str:
    return os.path.join(root, "data", "frontend", "ops")
def _read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

_R_D_KEYS = (  # R-d's 10 keys + clv_scoreboard (F-check-1); _sla_table() remaps onto tmp_path
    "execution_quality", "ingame_segment_trust", "ingame_segment_trust_multi",
    "ingame_clv_verdict", "l4_gate_prereg", "reject_ledger", "clv_reconcile_moneyline",
    "clv_reconcile_paper_pm", "clv_reconcile_paper_ingame", "clv_reconcile_paper_ingame_prop", "clv_scoreboard")

def _sla_table(root: str) -> Dict[str, "_sla.SlaEntry"]:  # real TABLE SLAs, paths under *root*
    def _path(key):
        return (os.path.join(root, "data", "frontend", "reject_ledger.jsonl")
                if key == "reject_ledger" else os.path.join(_ops(root), "%s.json" % key))
    return {key: _sla.SlaEntry(_path(key), _sla.TABLE[key].max_staleness_sec) for key in _R_D_KEYS}

def _fresh(key: str, table: Optional[Dict[str, "_sla.SlaEntry"]] = None) -> Optional[str]:
    row = _sla.check_one(key, table=table)  # None if fresh; else a reason string
    return None if row["status"] == _sla.GREEN else (row.get("reason") or row["status"].lower())

def _e_settled_n_coverage(sport: str, channel: str, root: str, table: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
    stale = _fresh("execution_quality", table)
    if stale:
        return "red", "execution_quality:%s" % stale
    eq = _read_json(os.path.join(_ops(root), "execution_quality.json")) or {}
    cell = (eq.get("channel_cells") or {}).get("%s|%s" % (sport, channel))
    if cell is None:
        return "red", "execution_quality_cell_missing"
    n, cov = cell.get("n_measurable"), cell.get("true_close_coverage_pct")
    inputs["n_measurable"], inputs["true_close_coverage_pct"] = n, cov
    inputs["execution_quality_cell"] = cell
    if not isinstance(n, (int, float)) or not isinstance(cov, (int, float)) or n < 60 or cov < 60.0:
        return "red", "settled_n_or_coverage_below_60"
    if n < _pol.MIN_SETTLED_N or cov < _pol.MIN_TRUE_CLOSE_FRAC * 100.0:
        return "amber", "settled_n_or_coverage_below_floor"
    return "green", None

def _e_clv_ci(cell: Optional[Dict[str, Any]], inputs: Dict[str, Any]) -> Any:
    if cell is None:
        return "red", "execution_quality_cell_missing"
    sv = ((cell.get("same_venue") or {}).get("same_venue") or {})
    lo, hi = ((sv.get("clv_ci95") or [None, None]) + [None, None])[:2]
    inputs["same_venue_clv_ci95"] = [lo, hi]
    if lo is not None and lo >= 0.0:
        return "green", None
    if hi is not None and hi < 0.0:
        return "red", "same_venue_clv_ci_adverse"
    return "amber", "same_venue_clv_ci_straddles_zero"

def _e_reconciler(channel: str, root: str, table: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
    key = "clv_reconcile_%s" % channel
    stale = _fresh(key, table)
    if stale:
        return "red", "%s:%s" % (key, stale)
    recon = _read_json(os.path.join(_ops(root), "%s.json" % key))
    if recon is None:
        return "red", "reconcile_file_missing:%s" % channel
    verdict = str(recon.get("verdict") or "")
    zmax = max([abs(z) for z in (recon.get("z_wins"), recon.get("z_units")) if isinstance(z, (int, float))], default=None)
    inputs["reconcile_verdict"] = verdict.split(" -- ")[0]
    if verdict.startswith("SUSPECT_CLOSE") or (zmax is not None and zmax > _Z_SIG):
        return "red", "reconcile_suspect_or_high_z"
    if verdict.startswith(("INSUFFICIENT_DATA", "NOT_APPLICABLE")):
        return "amber", "reconcile_not_applicable:%s" % channel
    if verdict.startswith("GENUINE_VARIANCE"):
        return "green", None
    if verdict.startswith("DIVERGENT"):  # zmax<=_Z_SIG here -- real, not-decisive 4th outcome, not "unknown"
        return "amber", "reconcile_divergent_not_decisive:%s" % channel
    return "red", "reconcile_unknown_verdict"

def _e_segment_trust(sport: str, root: str, table: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
    key = "ingame_segment_trust" if sport == "mlb" else "ingame_segment_trust_multi"
    stale = _fresh(key, table)
    if stale:
        return "red", "%s:%s" % (key, stale)
    seg = _read_json(os.path.join(_ops(root), "%s.json" % key))
    doc = seg if sport == "mlb" else ((seg or {}).get("per_sport") or {}).get(sport)
    if doc is None:
        return "red", "segment_trust_sport_missing:%s" % sport
    adverse = doc.get("adverse") or []
    inputs["adverse_segments"] = adverse
    return ("red", "segment_adverse") if adverse else ("green", None)

def _e_ingame_verdict(sport: str, root: str, table: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
    stale = _fresh("ingame_clv_verdict", table)
    if stale:
        return "red", "ingame_clv_verdict:%s" % stale
    doc = _read_json(os.path.join(_ops(root), "ingame_clv_verdict.json")) or {}
    match = next((s for s in (doc.get("sports") or []) if s.get("sport") == sport), None)
    if match is None:
        return "red", "ingame_clv_verdict_sport_absent"
    verd, nm = match.get("verdict"), match.get("n_markets")
    inputs["ingame_clv_verdict"] = verd
    if verd == "MATCH" and isinstance(nm, (int, float)) and nm >= 30:
        return "green", None
    if verd == "BEHIND":
        return "red", "ingame_clv_verdict_behind"
    return "red", "ingame_clv_verdict_not_match_or_thin"

def channel_trust_status(channel: str, rows: Sequence[Dict[str, Any]],
                          *, root: Optional[str] = None) -> Dict[str, Any]:
    """GREEN only if every sub-check is GREEN; RED if any; N-A/soft-floor => AMBER."""
    root = root or _REPO
    inputs: Dict[str, Any] = {}
    try:
        sports = [str(r.get("sport")) for r in rows if r.get("sport")]
        sport = Counter(sports).most_common(1)[0][0] if sports else None
        if not sport:
            return {"status": _RED, "reasons": ["no_sport"], "inputs": inputs}
        table = _sla_table(root)
        checks = [
            _e_settled_n_coverage(sport, channel, root, table, inputs),
            _e_clv_ci(inputs.get("execution_quality_cell"), inputs),
            _e_reconciler(channel, root, table, inputs),
            _e_segment_trust(sport, root, table, inputs),
        ]
        if channel in _INGAME_CHANNELS:
            checks.append(_e_ingame_verdict(sport, root, table, inputs))
        reasons = [r for _, r in checks if r]
        if any(v == "red" for v, _ in checks):
            status = _RED
        elif any(v == "amber" for v, _ in checks):
            status = _AMBER
        else:
            status = _GREEN
        return {"status": status, "reasons": reasons, "inputs": inputs}
    except Exception as exc:  # noqa: BLE001 -- fail-closed, never a bare pass
        return {"status": _RED, "reasons": ["error:%s" % type(exc).__name__], "inputs": inputs}

_WATERMARK_REL = os.path.join("data", "cache", "greenlight", "reject_ledger_watermark.jsonl")
_SNAPSHOT_REL = os.path.join("data", "cache", "greenlight", "prereg_snapshot")
_PREREG_PINNED_FIELDS = ("pre_registered_at", "floors", "planted_null", "fail_action")
_CITED_OPS_ARTIFACTS = ("execution_quality.json", "clv_scoreboard.json", "ingame_clv_verdict.json",
    "ingame_segment_trust.json", "ingame_segment_trust_multi.json")  # F-check-1 spec L163
def _check_retracted_numbers(report: Dict[str, Any], root: str) -> Dict[str, Any]:
    fails = list(_linter.lint_obj(report)["violations"])  # any kind: number/token/key, incl. cited artifacts
    for fn in _CITED_OPS_ARTIFACTS:
        d = _read_json(os.path.join(_ops(root), fn))
        fails.extend(_linter.lint_obj(d)["violations"] if d is not None else [])
    return {"name": "retracted_numbers_scan", "pass": len(fails) == 0, "na": False, "detail": fails[:5]}

def _check_edge_claimed_false(root: str) -> Dict[str, Any]:
    bad = []
    for fn in ("ingame_segment_trust.json", "ingame_segment_trust_multi.json", "ingame_clv_verdict.json"):
        d = _read_json(os.path.join(_ops(root), fn))
        if d is None:
            bad.append("%s:missing" % fn)
        elif d.get("edge_claimed") is not False:
            bad.append(fn)
    return {"name": "edge_claimed_false", "pass": len(bad) == 0, "na": False, "detail": bad}

def _check_proposal_only(root: str) -> Dict[str, Any]:
    d = _read_json(os.path.join(_ops(root), "ingame_segment_trust_multi.json"))
    prereg = _read_json(os.path.join(_ops(root), "l4_gate_prereg.json"))
    bad = []
    if d is not None and d.get("measurement_only") is False:
        bad.append("segment_trust_multi.measurement_only=False")
    if prereg is not None and prereg.get("edge_claimed") is True:
        bad.append("l4_gate_prereg.edge_claimed=True")
    for label, doc in (("segment_trust_multi", d), ("l4_gate_prereg", prereg)):
        if doc is not None and (doc.get("flag_flipped") or doc.get("wired")):
            bad.append("%s.flag_flipped_or_wired" % label)
    return {"name": "proposal_only_integrity", "pass": len(bad) == 0, "na": False, "detail": bad}

def _sha256_prefix(path: str, n_lines: int) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for i, line in enumerate(fh):
                if i >= n_lines:
                    break
                h.update(line)
        return h.hexdigest()
    except OSError:
        return None

def _append_watermark(path: str, tag: str, n_lines: int, prefix_sha: Optional[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts_utc": tag, "n_lines": n_lines, "prefix_sha256": prefix_sha}) + "\n")

def _check_reject_ledger_monotonic(root: str) -> Dict[str, Any]:
    ledger_path = os.path.join(root, "data", "frontend", "reject_ledger.jsonl")
    watermark_path = os.path.join(root, _WATERMARK_REL)
    name = "reject_ledger_monotonic"
    if not os.path.exists(ledger_path):
        return {"name": name, "pass": False, "na": False, "detail": "reject_ledger_missing"}
    try:
        with open(ledger_path, "r", encoding="utf-8") as fh:
            n_lines = sum(1 for _ in fh)
    except OSError:
        return {"name": name, "pass": False, "na": False, "detail": "reject_ledger_unreadable"}
    prefix_sha = _sha256_prefix(ledger_path, n_lines)
    if not os.path.exists(watermark_path):
        _append_watermark(watermark_path, "bootstrap", n_lines, prefix_sha)
        return {"name": name, "pass": True, "na": False, "detail": "bootstrap_first_run n_lines=%d" % n_lines}
    try:
        with open(watermark_path, "r", encoding="utf-8") as fh:
            last = json.loads([ln for ln in fh if ln.strip()][-1])
    except (OSError, json.JSONDecodeError, IndexError):
        return {"name": name, "pass": False, "na": False, "detail": "watermark_unreadable"}
    w_n, w_sha = last.get("n_lines", 0), last.get("prefix_sha256")
    shrunk = n_lines < w_n
    rewritten = (not shrunk) and _sha256_prefix(ledger_path, w_n) != w_sha
    if shrunk or rewritten:
        return {"name": name, "pass": False, "na": False, "detail": "shrink" if shrunk else "prefix_sha_mismatch"}
    if n_lines > w_n:
        _append_watermark(watermark_path, "refresh", n_lines, prefix_sha)
    return {"name": name, "pass": True, "na": False, "detail": "ok"}

def _check_prereg_integrity(root: str) -> Dict[str, Any]:
    name = "prereg_integrity"
    prereg_path = os.path.join(_ops(root), "l4_gate_prereg.json")
    prereg = _read_json(prereg_path)
    if prereg is None:
        return {"name": name, "pass": False, "na": False, "detail": "l4_gate_prereg_missing"}
    snap_dir = os.path.join(root, _SNAPSHOT_REL)
    snap_path = os.path.join(snap_dir, "l4_gate_prereg.json")
    if not os.path.exists(snap_path):
        os.makedirs(snap_dir, exist_ok=True)
        with open(snap_path, "w", encoding="utf-8") as fh:
            json.dump(prereg, fh, indent=1)
        snapshot = prereg
    else:
        snapshot = _read_json(snap_path)
        if snapshot is None:
            return {"name": name, "pass": False, "na": False, "detail": "snapshot_unreadable"}
    mismatched = [f for f in _PREREG_PINNED_FIELDS if prereg.get(f) != snapshot.get(f)]
    if mismatched:
        return {"name": name, "pass": False, "na": False, "detail": "snapshot_mismatch:%s" % ",".join(mismatched)}
    if "sha256" not in prereg:
        return {"name": name, "pass": True, "na": True, "detail": "sha_pending"}
    if _compute_sha(prereg) != prereg.get("sha256"):
        return {"name": name, "pass": False, "na": False, "detail": "sha_mismatch"}
    return {"name": name, "pass": True, "na": False, "detail": "ok"}

_F_FRESHNESS_KEYS = ("ingame_segment_trust", "ingame_segment_trust_multi", "reject_ledger",  # STALE fails, R-d
                     "execution_quality", "clv_scoreboard", "ingame_clv_verdict")
# l4_gate_prereg deliberately excluded: it is a write-once pre-registration
# stamp (2026-07-04) -- staying untouched for 172800s+ is the CORRECT state,
# not staleness. mtime-freshness would have permanently RED'd this gate 48h
# after pre-registration. Its real integrity check is content-based
# (_check_prereg_integrity's sha256 pin below), which runs regardless of age.
# Found + fixed in the 2026-07-16 freshness_sla audit.

def cv_honesty_status(report: Dict[str, Any], *, root: Optional[str] = None) -> Dict[str, Any]:
    """NOT_REFUTED only if all 5 checks pass with zero NOT_APPLICABLE."""
    root = root or _REPO
    try:
        table = _sla_table(root)
        stale = [("freshness:%s:%s" % (k, r)) for k in _F_FRESHNESS_KEYS
                 for r in [_fresh(k, table)] if r]
        if stale:
            return {"status": _RED, "checks": [], "failures": stale}
        checks = [
            _check_retracted_numbers(report, root),
            _check_edge_claimed_false(root),
            _check_proposal_only(root),
            _check_reject_ledger_monotonic(root),
            _check_prereg_integrity(root),
        ]
        failures = ["%s:%s" % (c["name"], c["detail"]) for c in checks if not c["pass"]]
        if failures:
            status = _RED
        elif any(c.get("na") for c in checks):
            status = _AMBER
        else:
            status = "NOT_REFUTED"
        return {"status": status, "checks": checks, "failures": failures}
    except Exception as exc:  # noqa: BLE001 -- fail-closed, never a bare pass
        return {"status": _RED, "checks": [], "failures": ["error:%s" % type(exc).__name__]}

__all__ = ["channel_trust_status", "cv_honesty_status"]
