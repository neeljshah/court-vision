"""Per-file tests for enrichment_gate_validation_v2 (LANE 3 item 4: v2
artifact assembly, v1 preserved).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_enrichment_gate_validation_v2.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import enrichment_gate_validation_v2 as V2


def _v1_better():
    return {"verdict": "BETTER_THAN_BASELINE", "half0": {"verdict": "BETTER_THAN_BASELINE"},
           "half1": {"verdict": "BETTER_THAN_BASELINE"}}


def _crossfit_better():
    return {"overall_verdict": "BETTER_THAN_BASELINE"}


def _crossfit_match():
    return {"overall_verdict": "MATCH"}


def _market_no_add():
    return {"verdict": "NO_ADD_BEYOND_MARKET"}


def test_build_v2_overall_better_when_v1_and_crossfit_both_better():
    doc = V2.build_v2(v1_doc=_v1_better(), census_fn=lambda: {"n_finished_matches_total": 88},
                      crossfit_fn=_crossfit_better, market_fn=_market_no_add)
    assert doc["overall_verdict"] == "BETTER_THAN_BASELINE"


def test_build_v2_overall_mixed_when_crossfit_not_better():
    doc = V2.build_v2(v1_doc=_v1_better(), census_fn=lambda: {}, crossfit_fn=_crossfit_match,
                      market_fn=_market_no_add)
    assert doc["overall_verdict"] == "MIXED_OR_INSUFFICIENT"


def test_build_v2_overall_mixed_when_v1_missing():
    """v1_doc={} (genuinely empty, not None-meaning-'use the real on-disk
    default') must yield MIXED_OR_INSUFFICIENT -- an absent/unresolvable v1
    verdict must never default to a passing overall."""
    doc = V2.build_v2(v1_doc={}, census_fn=lambda: {}, crossfit_fn=_crossfit_better,
                      market_fn=_market_no_add)
    assert doc["overall_verdict"] == "MIXED_OR_INSUFFICIENT"


def test_build_v2_preserves_v1_verbatim():
    v1 = _v1_better()
    v1["n_games"] = 29
    v1["brier_delta_marker"] = "UNIQUE_SENTINEL_VALUE"
    doc = V2.build_v2(v1_doc=v1, census_fn=lambda: {}, crossfit_fn=_crossfit_better,
                      market_fn=_market_no_add)
    assert doc["v1_fixed_form"]["brier_delta_marker"] == "UNIQUE_SENTINEL_VALUE"
    assert doc["v1_fixed_form"]["n_games"] == 29


def test_build_v2_all_sections_present():
    doc = V2.build_v2(v1_doc=_v1_better(), census_fn=lambda: {"a": 1},
                      crossfit_fn=_crossfit_better, market_fn=_market_no_add)
    for key in ("v1_fixed_form", "corpus_extension_census", "crossfit_conditioning",
               "market_awareness_check"):
        assert key in doc


def test_build_v2_honesty_fields_present():
    doc = V2.build_v2(v1_doc=_v1_better(), census_fn=lambda: {}, crossfit_fn=_crossfit_better,
                      market_fn=_market_no_add)
    assert doc["edge_claimed"] is False
    assert doc["schema_version"] == 2
    assert "preserved verbatim" in doc["honest_note"]


def test_build_v2_never_raises_on_producer_exception():
    def boom():
        raise RuntimeError("producer broke")

    doc = V2.build_v2(v1_doc=_v1_better(), census_fn=boom, crossfit_fn=boom, market_fn=boom)
    assert "error" in doc["corpus_extension_census"]
    assert "error" in doc["crossfit_conditioning"]
    assert "error" in doc["market_awareness_check"]
    assert doc["overall_verdict"] == "MIXED_OR_INSUFFICIENT"


def test_build_v2_gate_and_component_names_match_v1_convention():
    doc = V2.build_v2(v1_doc=_v1_better(), census_fn=lambda: {}, crossfit_fn=_crossfit_better,
                      market_fn=_market_no_add)
    assert doc["gate"] == "A_soccer_xg_VALIDATION"
    assert doc["component"] == "fotmob_backfill_validation"
    assert doc["provenance"] == "backfill_validation"


def test_main_never_raises_with_real_default_wiring(tmp_path, monkeypatch):
    """Exercises the real default read-or-run wiring, redirecting BOTH the
    v1 read path and the v2 write path to tmp_path so this test never
    touches real on-disk artifacts."""
    monkeypatch.setattr(V2, "V1_PATH", tmp_path / "v1_absent.json")
    monkeypatch.setattr(V2, "V2_PATH", tmp_path / "v2_out.json")
    rc = V2.main()
    assert rc == 0
    assert (tmp_path / "v2_out.json").is_file()
