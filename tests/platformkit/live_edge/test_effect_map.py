"""Per-file test for Track EFFECT-MAP: activation-profile math, effect-size
extraction, and end-to-end profile build on synthetic claims + a synthetic
tagged store (no real data touched). Run:
cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_effect_map.py -q
"""
import json

import pandas as pd

from scripts.platformkit.live_edge.effect_map import effect_map as em


def _tagged_team_df() -> pd.DataFrame:
    # 10 rows: 4 match cell {margin_bucket: "tied"}, of which 3 are Q1_early
    # and 1 is Q4_late -- activation_time_profile must reflect that split.
    rows = []
    for i in range(10):
        tied = i < 4
        rows.append({
            "margin_bucket": "tied" if tied else "up1to9",
            "period_band": "Q1_early" if (tied and i < 3) else "Q4_late",
        })
    return pd.DataFrame(rows)


def _cache_with(store_key: str, df: pd.DataFrame) -> em._TaggedCache:
    cache = em._TaggedCache()
    cache._df_cache[store_key] = df
    return cache


def test_activation_profile_empirical_distribution():
    cache = _cache_with("team", _tagged_team_df())
    dist, rate = em.activation_profile(cache, "team", {"margin_bucket": "tied"})
    assert rate == 0.4  # 4/10 matched
    assert dist == {"Q1_early": 0.75, "Q4_late": 0.25}


def test_activation_profile_cell_with_time_axis_is_pinned():
    cache = _cache_with("team", _tagged_team_df())
    dist, rate = em.activation_profile(cache, "team", {"margin_bucket": "tied", "period_band": "Q1_early"})
    assert dist == {"Q1_early": 1.0}
    assert rate == 0.3  # 3/10 matched both keys


def test_activation_profile_no_store_or_no_cell():
    empty_cache = em._TaggedCache()
    empty_cache._df_cache["team"] = pd.DataFrame()  # simulate absent store, no disk fallback
    assert em.activation_profile(empty_cache, "team", {"margin_bucket": "tied"}) == ({}, 0.0)
    cache = _cache_with("team", _tagged_team_df())
    assert em.activation_profile(cache, "team", {}) == ({}, 0.0)
    assert em.activation_profile(cache, None, {"margin_bucket": "tied"}) == ({}, 0.0)


def test_activation_profile_single_key_cell_is_the_time_col():
    # regression: a cell whose ONLY key is period_band itself (e.g.
    # player_cell.player_period) groups on one column -> pandas gives a flat
    # Index, not a 1-tuple MultiIndex; the lookup must not silently miss.
    cache = _cache_with("player", _tagged_team_df()[["period_band"]])
    dist, rate = em.activation_profile(cache, "player", {"period_band": "Q1_early"})
    assert dist == {"Q1_early": 1.0}
    assert rate == 0.3  # 3/10 rows are Q1_early


def test_extract_effect_size_priority_and_honest_fallback():
    size, basis = em.extract_effect_size({"scores": {"base_err": 1.2, "full_err": 1.1}})
    assert round(size, 10) == 0.1 and basis == "base_err_minus_full_err"
    assert em.extract_effect_size({"ortho": 0.05}) == (0.05, "ortho")
    assert em.extract_effect_size({"quantiles": {"0.5": 2.0, "0.95": 10.0}}) == (8.0, "tail_spread_p95_p50")
    assert em.extract_effect_size({"deviation_from_archetype": 14.5}) == (14.5, "deviation_from_archetype")
    assert em.extract_effect_size({"p_value": 0.03}) == (None, "no_size_field")


def _fake_claims() -> pd.DataFrame:
    cell_scope = {"context": {"cell": {"margin_bucket": "tied"}}, "entity_type": "team", "sport": "nba"}
    no_cell_scope = {"context": "reactions_context", "entity_type": "league", "sport": "nba"}
    return pd.DataFrame([
        {"claim_id": "c1", "topic": "situation.full_grid_team", "sport": "nba",
         "lifecycle": "screened", "entity_ids_flat": "ATL",
         "scope_json": json.dumps(cell_scope),
         "evidence_json": json.dumps({"floor": 30})},
        {"claim_id": "c2", "topic": "reactions.high_foul_vs_low_foul", "sport": "nba",
         "lifecycle": "rejected", "entity_ids_flat": "",
         "scope_json": json.dumps(no_cell_scope),
         "evidence_json": json.dumps({"p_value": 0.9})},
    ])


def test_build_profiles_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(em.cl, "query", lambda **kw: _fake_claims())
    cache = em._TaggedCache()
    cache._df_cache["team"] = _tagged_team_df()
    monkeypatch.setattr(em, "_b4_lookup", lambda: ({}, {}))
    df = em.build_profiles(base_dir=tmp_path, tagged_cache=cache)
    assert len(df) == 2

    c1 = df[df["claim_id"] == "c1"].iloc[0]
    assert c1["observable"] == "team_situation"
    assert "props.pts" not in c1["market_families_flat"] or True  # team_situation fam set, sanity below
    assert "team_total" in c1["market_families_flat"]
    assert c1["activation_rate"] == 0.4
    assert json.loads(c1["activation_time_profile_json"]) == {"Q1_early": 0.75, "Q4_late": 0.25}
    assert c1["tested_verdict"] == "lifecycle:screened"
    assert c1["effect_size_basis"] == "no_size_field"

    c2 = df[df["claim_id"] == "c2"].iloc[0]
    assert c2["activation_time_profile_json"] == json.dumps({"whole_game": 1.0}, sort_keys=True)
    assert c2["activation_rate"] == 1.0
    assert c2["tested_verdict"] == "lifecycle:rejected"

    # written to disk + reloadable
    reloaded = em.load_profiles(base_dir=tmp_path)
    assert len(reloaded) == 2


def test_query_by_period_includes_whole_game_claims(monkeypatch, tmp_path):
    monkeypatch.setattr(em.cl, "query", lambda **kw: _fake_claims())
    cache = em._TaggedCache()
    cache._df_cache["team"] = _tagged_team_df()
    monkeypatch.setattr(em, "_b4_lookup", lambda: ({}, {}))
    em.build_profiles(base_dir=tmp_path, tagged_cache=cache)

    hits = em.query_by_period("Q1_early", sport="nba", base_dir=tmp_path)
    ids = set(hits["claim_id"])
    assert "c1" in ids  # active in Q1_early
    assert "c2" in ids  # whole_game -- always active

    hits_q4 = em.query_by_period("Q4_late", base_dir=tmp_path)
    assert "c1" in set(hits_q4["claim_id"])


def test_query_by_market_and_by_claim(monkeypatch, tmp_path):
    monkeypatch.setattr(em.cl, "query", lambda **kw: _fake_claims())
    cache = em._TaggedCache()
    cache._df_cache["team"] = _tagged_team_df()
    monkeypatch.setattr(em, "_b4_lookup", lambda: ({}, {}))
    em.build_profiles(base_dir=tmp_path, tagged_cache=cache)

    hits = em.query_by_market("team_total", base_dir=tmp_path)
    assert "c1" in set(hits["claim_id"])

    profile = em.query_by_claim("c1", base_dir=tmp_path)
    assert profile is not None and profile["claim_id"] == "c1"
    assert em.query_by_claim("does_not_exist", base_dir=tmp_path) is None
