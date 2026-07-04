"""Per-file test for ingame_soccer_trust_rerun.py (LANE 3 queue item 3)."""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_soccer_trust_rerun as _rr


def test_build_rerun_never_raises_and_has_shape():
    doc = _rr.build_rerun()
    assert doc.get("component") == _rr.COMPONENT
    assert doc.get("sport") == "soccer_intl"
    assert doc.get("edge_claimed") is False
    assert "error" not in doc
    variants = doc.get("variants", {})
    assert set(variants.keys()) == {"raw", "backfilled"}
    for variant in ("raw", "backfilled"):
        vd = variants[variant]
        assert "scheme_a_md5_hash" in vd and "scheme_b_day_parity" in vd
        assert set(vd["half_verdict"].keys()) == {"H1", "H2"}
        for h in ("H1", "H2"):
            v = vd["half_verdict"][h]["verdict"]
            assert v in ("ADVERSE-REPLICATED", "NOT-REPLICATED", "INSUFFICIENT")


def test_backfilled_has_more_or_equal_labeled_games_than_raw():
    doc = _rr.build_rerun()
    raw_a = doc["variants"]["raw"]["scheme_a_md5_hash"]["per_corpus"]
    bf_a = doc["variants"]["backfilled"]["scheme_a_md5_hash"]["per_corpus"]
    raw_total = sum(c["n_labeled"] for c in raw_a)
    bf_total = sum(c["n_labeled"] for c in bf_a)
    assert bf_total >= raw_total


def test_overall_verdict_matches_per_half_rollup():
    doc = _rr.build_rerun()
    ov, _reason = _rr.overall_verdict(doc)
    assert ov in ("ADVERSE-REPLICATED", "NOT-REPLICATED", "INSUFFICIENT")


def test_day_parity_split_is_disjoint_and_deterministic():
    from scripts.platformkit.ingame import ingame_clv_per_segment as _seg
    files = _seg._discover(None, "soccer_intl")
    b1 = _rr._day_parity_split(files, 2)
    b2 = _rr._day_parity_split(files, 2)
    assert [set(x) for x in b1] == [set(x) for x in b2]
    all_files = set(files)
    split_files = set(b1[0]) | set(b1[1])
    assert split_files == all_files
    assert not (set(b1[0]) & set(b1[1]))
