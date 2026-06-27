"""Per-file test for ci_regate (W4 cadence step F1). NO full pytest."""
from __future__ import annotations

import json

from scripts.platformkit.progress import ci_regate
from scripts.platformkit.autonomy.work_queue import ALLOWED_KINDS


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="ascii")


def test_growth_selected_no_growth_skipped(tmp_path):
    lp = tmp_path / "improve_ledger.jsonl"
    _write_jsonl(lp, [{"sport": "soccer", "verdict": "REJECT", "n_settled": 100},
                      {"sport": "nba", "verdict": "REJECT", "n_settled": 50}])
    # soccer grew (100 -> 140), nba flat (50 -> 50).
    res = ci_regate.select_regate_targets(
        ledger_path=lp, corpora_dir=tmp_path,
        current_counts={"soccer": 140, "nba": 50, "mlb": 0, "tennis": 0})
    assert res.status == ci_regate.SELECTED
    sports = {t.sport for t in res.targets}
    assert "soccer" in sports
    assert "nba" not in sports  # no churn on a flat corpus
    for t in res.targets:
        assert t.kind in ALLOWED_KINDS  # allowlist enforced


def test_no_op_when_nothing_grew(tmp_path):
    lp = tmp_path / "l.jsonl"
    _write_jsonl(lp, [{"sport": "soccer", "verdict": "REJECT", "n_settled": 100}])
    res = ci_regate.select_regate_targets(
        ledger_path=lp, corpora_dir=tmp_path,
        current_counts={"soccer": 100, "nba": 0, "mlb": 0, "tennis": 0})
    assert res.status == ci_regate.NO_OP
    assert res.targets == []


def test_record_regate_pass_is_proposal_not_ship(tmp_path):
    out = ci_regate.record_regate(
        "soccer", "SHIP", {"brier_delta": 0.001},
        funnel_dir=tmp_path, now=1_700_000_000.0)
    doc = json.loads(out.read_text(encoding="ascii"))
    assert doc["verdict"] == "SHIP-PROPOSAL"   # a PASS records a PROPOSAL, never a ship
    assert doc["proposal_only"] is True
    assert doc["edge_claimed"] is False


def test_no_dollar_field_anywhere(tmp_path):
    lp = tmp_path / "l.jsonl"
    _write_jsonl(lp, [{"sport": "soccer", "verdict": "REJECT", "n_settled": 1}])
    res = ci_regate.select_regate_targets(
        ledger_path=lp, corpora_dir=tmp_path, current_counts={"soccer": 9})
    out = ci_regate.record_regate("soccer", "REJECT",
                                  {"roi": 1.23, "pnl": 5.0, "brier": 0.1},
                                  funnel_dir=tmp_path, now=1.0)
    doc = json.loads(out.read_text(encoding="ascii"))
    # forbidden money keys are stripped from the readout
    assert "roi" not in doc["readout"] and "pnl" not in doc["readout"]
    assert "brier" in doc["readout"]
    # No $ field as a DATA KEY (the honest 'no $ field' disclaimer note is excluded).
    doc.pop("note", None)
    assert not any("$" in str(k) for k in doc)
    blob = json.dumps(doc).lower()
    for tok in ("bankroll", "profit", "usd"):
        assert tok not in blob


def test_record_regate_filename_collision_safe(tmp_path):
    """Two records within the SAME wall-clock second must NOT overwrite each other.

    The stem now carries microsecond precision (derived from the injected ts only), so
    distinct sub-second ticks land in distinct files instead of aliasing to one.
    """
    out_a = ci_regate.record_regate("nba", "REJECT", {"brier": 0.1},
                                    funnel_dir=tmp_path, now=1_700_000_000.123456)
    out_b = ci_regate.record_regate("nba", "REJECT", {"brier": 0.2},
                                    funnel_dir=tmp_path, now=1_700_000_000.654321)
    assert out_a != out_b, "same-second siblings collided onto one filename"
    assert out_a.exists() and out_b.exists()
    # both readouts survived (no silent overwrite)
    assert json.loads(out_a.read_text(encoding="ascii"))["readout"]["brier"] == 0.1
    assert json.loads(out_b.read_text(encoding="ascii"))["readout"]["brier"] == 0.2
    # the integer-second "ts" readout field is unchanged (behavior-preserving)
    assert json.loads(out_a.read_text(encoding="ascii"))["ts"] == 1_700_000_000


if __name__ == "__main__":
    import sys
    import tempfile
    import pathlib
    for fn in (test_growth_selected_no_growth_skipped, test_no_op_when_nothing_grew,
               test_record_regate_pass_is_proposal_not_ship,
               test_no_dollar_field_anywhere,
               test_record_regate_filename_collision_safe):
        with tempfile.TemporaryDirectory() as d:
            fn(pathlib.Path(d))
        print("ok:", fn.__name__)
    sys.exit(0)
