"""Per-file test for funnel_verdict_reconcile -- folds recorded funnel GATE verdicts into
the reject-ledger and exposes a PRECISE per-sport closed index so the improvement_finder
stops re-listing already-tested data layers as UNTESTED.

Honesty-critical: the closure must be PRECISE (sport-scoped, distinctive-slug substring) so
a genuinely-untested data point is NEVER falsely marked tested (that would fabricate
completeness). Under-closing is the safe error direction; over-closing is a bug.
"""
from __future__ import annotations

import json

from scripts.platformkit.meta import funnel_verdict_reconcile as F


def _write_verdict(funnel_dir, name, layer, verdict):
    funnel_dir.mkdir(parents=True, exist_ok=True)
    (funnel_dir / name).write_text(json.dumps(
        {"layer": layer, "verdict": verdict, "n_corpora": 2,
         "vs_close": "UNPROVEN -- CALIBRATION only"}), encoding="utf-8")


def test_fold_is_idempotent(tmp_path, monkeypatch):
    fd = tmp_path / "funnel"
    _write_verdict(fd, "nba_travel_gate.json", "nba_travel", "REJECT")
    _write_verdict(fd, "mlb_atbat_ingame_gate.json", "mlb_atbat", "REJECT")
    monkeypatch.setattr(F, "FUNNEL", fd)
    ledger = tmp_path / "reject_ledger.jsonl"
    assert F.fold_into_ledger(ledger_path=ledger) == 2     # both new
    assert F.fold_into_ledger(ledger_path=ledger) == 0     # idempotent re-run
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    sigs = {r["signal"] for r in rows}
    assert sigs == {"nba_travel", "mlb_atbat"}
    assert all(r["source"] == "funnel_gate" for r in rows)


def test_cadence_and_nongate_files_are_skipped(tmp_path, monkeypatch):
    fd = tmp_path / "funnel"
    _write_verdict(fd, "mlb_ci_survivor_123.json", "mlb_x", "SURVIVOR_HELD")  # cadence spam
    _write_verdict(fd, "soccer_intl_parity.json", "soccer_intl", "ok")        # not a verdict
    _write_verdict(fd, "nba_travel_gate.json", "nba_travel", "REJECT")        # real
    monkeypatch.setattr(F, "FUNNEL", fd)
    got = {layer for layer, _, _ in F.iter_funnel_verdicts()}
    assert got == {"nba_travel"}  # only the real gate verdict


def test_index_and_closure_are_precise_and_sport_scoped():
    idx = {"nba": {"travel", "possession"}, "mlb": {"atbat", "statcast"},
           "soccer": {"redcard", "reddiff", "espn28"}}
    # tested layers -> closed (matches the COVERAGE prose wording)
    assert F.is_data_point_closed("NBA", "travel_home/away", idx) is True
    assert F.is_data_point_closed("NBA", "PBP possession/pace/run_diff", idx) is True
    assert F.is_data_point_closed("MLB", "per-at-bat states (RE24, leverage)", idx) is True
    assert F.is_data_point_closed("soccer", "in-game card / man-advantage (red_diff)", idx) is True
    assert F.is_data_point_closed("soccer", "ESPN 28-field matchstats", idx) is True
    # genuinely untested -> stays OPEN (the honest error direction)
    assert F.is_data_point_closed("MLB", "ESPN box LOB/GIDP/errors", idx) is False
    # sport-scoped: an nba slug must NOT close a soccer row
    assert F.is_data_point_closed("soccer", "travel_home/away", idx) is False
    # generic words never over-close
    assert F.is_data_point_closed("NBA", "team form state", idx) is False


def test_basketball_nba_sport_alias_resolves():
    idx = {"nba": {"travel"}}
    assert F.is_data_point_closed("basketball_nba", "travel_home/away", idx) is True


def test_extra_source_finegrid_picked_up(tmp_path, monkeypatch):
    """A gate verdict outside funnel/ (data/frontend/ingame/finegrid_gate_nba.json) is
    folded via _EXTRA_SOURCES so the finer-grid REJECT is recognized as CLOSED."""
    frontend = tmp_path / "frontend"
    fd = frontend / "funnel"
    fd.mkdir(parents=True, exist_ok=True)
    ingame = frontend / "ingame"
    ingame.mkdir(parents=True, exist_ok=True)
    (ingame / "finegrid_gate_nba.json").write_text(json.dumps(
        {"verdict": "REJECT",
         "vs_close": "UNPROVEN -- calibration vs coarse grid, not a market edge"}),
        encoding="utf-8")
    monkeypatch.setattr(F, "FUNNEL", fd)  # FUNNEL.parent == frontend -> ingame/ resolvable
    slugs = {slug for slug, _v, _d in F.iter_funnel_verdicts()}
    assert "nba_finegrid_blend" in slugs
    # folds into the ledger as a recognized nba REJECT (source funnel_gate)
    ledger = tmp_path / "reject_ledger.jsonl"
    assert F.fold_into_ledger(ledger_path=ledger) == 1
    rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows[0]["signal"] == "nba_finegrid_blend"
    assert F._norm(rows[0]["sport"]) == "nba"
