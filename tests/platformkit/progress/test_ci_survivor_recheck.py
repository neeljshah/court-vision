"""Per-file test for ci_survivor_recheck (W4 cadence step F2). NO full pytest."""
from __future__ import annotations

import json

from scripts.platformkit.progress import ci_survivor_recheck as sr
from scripts.platformkit.autonomy.work_queue import ALLOWED_KINDS


def test_survivor_re_enqueued_at_wider_k():
    survivors = [{"sport": "soccer", "signal": "diff_corners_asof",
                  "verdict": "CONFIRMED_SURVIVOR", "K": 20}]
    targets = sr.select_survivor_targets(survivors=survivors, k_step=2)
    assert len(targets) == 1
    t = targets[0]
    assert t.kind in ALLOWED_KINDS               # allowlist enforced
    assert t.prev_k == 20 and t.next_k == 40     # wider cumulative K
    assert t.kind == sr.RECHECK_KIND


def test_demotes_on_planted_fail(tmp_path):
    """A re-check that returns a non-CONFIRMED verdict DEMOTES the survivor."""
    task = sr.SurvivorTask(kind=sr.RECHECK_KIND, sport="soccer",
                           signal="diff_corners_asof", prev_k=20, next_k=40)

    class _Rep:
        verdict = "DOWNGRADE_TO_ARTIFACT"  # planted fail at wider K

    out = sr.recheck_survivor(task, gate_fn=lambda k: _Rep(),
                              funnel_dir=tmp_path, now=1_700_000_000.0)
    assert out.demoted is True
    assert out.status == sr.DEMOTED
    doc = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="ascii"))
    assert doc["demoted"] is True
    assert doc["verdict"] == "DOWNGRADE_TO_ARTIFACT"


def test_held_when_still_confirmed(tmp_path):
    task = sr.SurvivorTask(kind=sr.RECHECK_KIND, sport="soccer",
                           signal="x", prev_k=20, next_k=40)

    class _Rep:
        verdict = "CONFIRMED_SURVIVOR"

    out = sr.recheck_survivor(task, gate_fn=lambda k: _Rep(),
                              funnel_dir=tmp_path, now=2.0)
    assert out.demoted is False and out.status == sr.HELD


def test_harness_raise_fails_closed_to_demote(tmp_path):
    task = sr.SurvivorTask(kind=sr.RECHECK_KIND, sport="soccer",
                           signal="x", prev_k=4, next_k=8)

    def _boom(k):
        raise RuntimeError("gate exploded")

    out = sr.recheck_survivor(task, gate_fn=_boom, funnel_dir=tmp_path, now=3.0)
    assert out.demoted is True  # fail-closed: never keep a survivor we can't re-confirm


def test_no_feature_promotion_no_dollar(tmp_path):
    task = sr.SurvivorTask(kind=sr.RECHECK_KIND, sport="soccer",
                           signal="x", prev_k=20, next_k=40)
    out = sr.recheck_survivor(task, gate_fn=lambda k: type("R", (), {"verdict": "PASS"}),
                              funnel_dir=tmp_path, now=4.0)
    doc = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="ascii"))
    # No $ as a DATA KEY (the honest 'no $' disclaimer note/deciding text excluded).
    assert not any("$" in str(k) for k in doc)
    doc.pop("note", None)
    blob = (json.dumps(doc)).lower()
    for tok in ("ship_feature", "flag_on", "promote_feature", "roi", "pnl",
                "bankroll", "profit", "usd"):
        assert tok not in blob


if __name__ == "__main__":
    import sys
    import tempfile
    import pathlib
    test_survivor_re_enqueued_at_wider_k()
    print("ok: test_survivor_re_enqueued_at_wider_k")
    for fn in (test_demotes_on_planted_fail, test_held_when_still_confirmed,
               test_harness_raise_fails_closed_to_demote,
               test_no_feature_promotion_no_dollar):
        with tempfile.TemporaryDirectory() as d:
            fn(pathlib.Path(d))
        print("ok:", fn.__name__)
    sys.exit(0)
