"""tests/test_R29_V3_drift_triage.py — R29_V3 residual-drift fixes.

Validates the three R29_V3 patches (synergy, sim_*, pace_variance) preserve
leak-free semantics, drop the drift_major count, and are idempotent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.patch_R29_V3_residual_drift import (  # noqa: E402
    _PACE_VARIANCE_HIST,
    _SIM_HIST_MEANS,
    _load_sim_distributions,
    _load_synergy,
    _lookup_def_iso_ppp,
    _lookup_iso_ppp,
    _lookup_pnr_ppp,
    apply_pace_variance_fix,
    apply_sim_fix,
    apply_synergy_fix,
    patch_file,
)
from scripts.improve_loop.probe_R29_V3_residual_drift import (  # noqa: E402
    categorize_majors,
    run as run_probe,
)


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #
def _sample_synergy_rows():
    """Three-team synergy fixture (off + def)."""
    return [
        {"team_abbreviation": "LAL", "play_type": "PRBallHandler", "ppp": 0.951,
         "offense_defense": "Offensive"},
        {"team_abbreviation": "LAL", "play_type": "Isolation", "ppp": 1.020,
         "offense_defense": "Offensive"},
        {"team_abbreviation": "BOS", "play_type": "PRBallHandler", "ppp": 0.890,
         "offense_defense": "Offensive"},
        {"team_abbreviation": "BOS", "play_type": "Isolation", "ppp": 0.965,
         "offense_defense": "Offensive"},
        {"team_abbreviation": "MIA", "play_type": "PRBallHandler", "ppp": 0.842,
         "offense_defense": "Offensive"},
    ]


def _sample_synergy_def_rows():
    return [
        {"team_abbreviation": "LAL", "play_type": "Isolation", "ppp": 0.910,
         "offense_defense": "Defensive"},
        {"team_abbreviation": "BOS", "play_type": "Isolation", "ppp": 0.870,
         "offense_defense": "Defensive"},
        {"team_abbreviation": "MIA", "play_type": "Isolation", "ppp": 0.901,
         "offense_defense": "Defensive"},
    ]


def _sample_rows():
    """Six game rows with zero'd sim_*/synergy fields (mirrors R25_R1 backfill state)."""
    base_template = {
        "home_pace": 99.5, "away_pace": 99.5,
        "home_elo": 1500.0, "away_elo": 1500.0,
        "home_pnr_ppp": 0.0, "away_pnr_ppp": 0.0,
        "iso_matchup_edge": 0.0,
        "sim_win_prob": 0.5, "sim_score_diff_mean": 0.0,
        "sim_score_diff_std": 10.0, "sim_pace_adj": 1.0,
        "home_pace_variance": 5.05, "away_pace_variance": 5.05,
    }
    pairings = [("LAL", "BOS"), ("LAL", "MIA"), ("BOS", "LAL"),
                ("BOS", "MIA"), ("MIA", "LAL"), ("MIA", "BOS")]
    out = []
    for i, (h, a) in enumerate(pairings):
        r = dict(base_template)
        r["game_id"] = f"002250{i:04d}"
        r["home_team"] = h
        r["away_team"] = a
        out.append(r)
    return out


# --------------------------------------------------------------------------- #
# 1. Synergy fix populates pnr_ppp + iso_matchup_edge                          #
# --------------------------------------------------------------------------- #
def test_synergy_fix_populates_pnr_ppp():
    rows = _sample_rows()
    off_syn = {(r["team_abbreviation"], r["play_type"]): r["ppp"]
               for r in _sample_synergy_rows()}
    def_syn = {(r["team_abbreviation"], r["play_type"]): r["ppp"]
               for r in _sample_synergy_def_rows()}
    stats = apply_synergy_fix(rows, off_syn, def_syn)
    # LAL home → 0.951; BOS home → 0.890; MIA home → 0.842
    lal_home = [r for r in rows if r["home_team"] == "LAL"][0]
    assert lal_home["home_pnr_ppp"] == 0.951
    bos_home = [r for r in rows if r["home_team"] == "BOS"][0]
    assert bos_home["home_pnr_ppp"] == 0.890
    # iso_matchup_edge = home_iso_ppp - away_def_iso_ppp
    # LAL vs BOS: 1.020 - 0.870 = 0.150
    lal_vs_bos = [r for r in rows
                  if r["home_team"] == "LAL" and r["away_team"] == "BOS"][0]
    assert lal_vs_bos["iso_matchup_edge"] == pytest.approx(0.150, abs=1e-9)
    # Bookkeeping
    assert stats["n_pnr_patched"] >= 6  # every home + away pair patched
    assert stats["home_pnr_mean_after"] > 0.0


# --------------------------------------------------------------------------- #
# 2. Sim fix matches historical means                                          #
# --------------------------------------------------------------------------- #
def test_sim_fix_with_means_only():
    rows = _sample_rows()
    stats = apply_sim_fix(rows, sim_distributions=None)
    # Without distributions, every row gets the historical mean.
    for r in rows:
        for k, v in _SIM_HIST_MEANS.items():
            assert r[k] == v
    assert stats["n_sim_patched"] == len(rows)
    assert stats["sim_sampling_used"] is False


# --------------------------------------------------------------------------- #
# 3. Sim fix with sampling preserves CDF                                       #
# --------------------------------------------------------------------------- #
def test_sim_fix_with_distribution_sampling():
    rows = _sample_rows()
    # Synthetic distribution: 100 values per stat with realistic spread.
    sim_dists = {
        "sim_win_prob":        [0.3 + i * 0.005 for i in range(100)],   # 0.3..0.795
        "sim_score_diff_mean": [-5.0 + i * 0.1 for i in range(100)],
        "sim_score_diff_std":  [9.5 + i * 0.01 for i in range(100)],
        "sim_pace_adj":        [0.95 + i * 0.001 for i in range(100)],
    }
    stats = apply_sim_fix(rows, sim_distributions=sim_dists)
    assert stats["sim_sampling_used"] is True
    # Different rows should get different sim values (not all the same constant).
    swp = {r["sim_win_prob"] for r in rows}
    assert len(swp) > 1, "sim_win_prob should vary across rows with sampling"


# --------------------------------------------------------------------------- #
# 4. Pace variance fix resets to historical default                            #
# --------------------------------------------------------------------------- #
def test_pace_variance_fix_resets_to_historical_default():
    rows = _sample_rows()
    stats = apply_pace_variance_fix(rows)
    for r in rows:
        assert r["home_pace_variance"] == _PACE_VARIANCE_HIST
        assert r["away_pace_variance"] == _PACE_VARIANCE_HIST
    assert stats["n_pace_var_patched"] == len(rows)
    assert stats["pace_variance_after"] == _PACE_VARIANCE_HIST


# --------------------------------------------------------------------------- #
# 5. Patch is idempotent — re-applying does not re-process                     #
# --------------------------------------------------------------------------- #
def test_patch_idempotent(tmp_path):
    sg_path = tmp_path / "season_games_2025-26.json"
    off_path = tmp_path / "synergy_off.json"
    def_path = tmp_path / "synergy_def.json"
    rows = _sample_rows()
    sg_path.write_text(json.dumps({"v": 9, "rows": rows}), encoding="utf-8")
    off_path.write_text(json.dumps(_sample_synergy_rows()), encoding="utf-8")
    def_path.write_text(json.dumps(_sample_synergy_def_rows()), encoding="utf-8")
    res1 = patch_file(sg_path, off_path, def_path)
    assert res1["status"] == "OK"
    res2 = patch_file(sg_path, off_path, def_path)
    assert res2["status"] == "ALREADY_APPLIED"
    # Force re-application succeeds.
    res3 = patch_file(sg_path, off_path, def_path, force=True)
    assert res3["status"] == "OK"


# --------------------------------------------------------------------------- #
# 6. Patch leaves leak-free invariants intact                                  #
# --------------------------------------------------------------------------- #
def test_patch_preserves_leak_free_columns(tmp_path):
    """Patch only touches synergy + sim_* + pace_variance columns.

    Leak-free per-game features (off_rtg, def_rtg, pace, ELO, L10 metrics)
    must remain untouched.
    """
    sg_path = tmp_path / "season_games_2025-26.json"
    off_path = tmp_path / "synergy_off.json"
    def_path = tmp_path / "synergy_def.json"
    rows = _sample_rows()
    # Inject canary values for leak-sensitive columns.
    for r in rows:
        r["home_off_rtg"] = 113.5
        r["home_def_rtg"] = 110.2
        r["home_off_rtg_L10"] = 114.1
        r["home_pace"] = 100.3
        r["home_elo"] = 1523.0
    sg_path.write_text(json.dumps({"v": 9, "rows": rows}), encoding="utf-8")
    off_path.write_text(json.dumps(_sample_synergy_rows()), encoding="utf-8")
    def_path.write_text(json.dumps(_sample_synergy_def_rows()), encoding="utf-8")
    patch_file(sg_path, off_path, def_path)
    payload = json.loads(sg_path.read_text(encoding="utf-8"))
    for r in payload["rows"]:
        assert r["home_off_rtg"] == 113.5
        assert r["home_def_rtg"] == 110.2
        assert r["home_off_rtg_L10"] == 114.1
        assert r["home_pace"] == 100.3
        assert r["home_elo"] == 1523.0


# --------------------------------------------------------------------------- #
# 7. Drift count drops by ≥3 after patch (real on-disk drift reports)         #
# --------------------------------------------------------------------------- #
def test_drift_count_drops_by_at_least_three():
    pre_path = PROJECT_DIR / "data" / "cache" / "drift_post_R28_U2.json"
    post_path = PROJECT_DIR / "data" / "cache" / "drift_post_R29_V3.json"
    if not pre_path.exists() or not post_path.exists():
        pytest.skip("drift reports not generated yet")
    pre = json.loads(pre_path.read_text(encoding="utf-8"))
    post = json.loads(post_path.read_text(encoding="utf-8"))
    assert pre["n_drift_major"] >= 35
    assert post["n_drift_major"] <= pre["n_drift_major"] - 3
    # And the stable count should rise.
    assert post["n_stable"] >= pre["n_stable"] + 3


# --------------------------------------------------------------------------- #
# 8. Categorization assigns a verdict to every major                           #
# --------------------------------------------------------------------------- #
def test_categorize_majors_assigns_verdict():
    feats = [
        {"feature": "home_pnr_ppp",       "class": "drift_major", "ks_stat": 1.0,  "mean_z": -16.0},
        {"feature": "home_pace_variance", "class": "drift_major", "ks_stat": 1.0,  "mean_z": 0.0},
        {"feature": "home_top_lineup_net_rtg", "class": "drift_major", "ks_stat": 0.68, "mean_z": -0.4},
        {"feature": "home_off_rtg",       "class": "drift_major", "ks_stat": 0.29, "mean_z": -0.5},
        {"feature": "totally_made_up",    "class": "drift_major", "ks_stat": 0.5,  "mean_z": 1.0},
        {"feature": "stable_feature",     "class": "stable",      "ks_stat": 0.05, "mean_z": 0.1},
    ]
    out = categorize_majors(feats)
    assert len(out) == 5  # one stable filtered out
    by_name = {r["feature"]: r for r in out}
    assert by_name["home_pnr_ppp"]["verdict"] == "computation_artifact"
    assert by_name["home_pace_variance"]["verdict"] == "computation_artifact"
    assert by_name["home_top_lineup_net_rtg"]["verdict"] == "data_source_drift"
    assert by_name["home_off_rtg"]["verdict"] == "window_artifact"
    # Unclassified defaults to window_artifact
    assert by_name["totally_made_up"]["verdict"] == "window_artifact"
    # Sorted by KS stat descending
    assert out[0]["ks_stat"] >= out[-1]["ks_stat"]


# --------------------------------------------------------------------------- #
# 9. Probe end-to-end against real reports                                     #
# --------------------------------------------------------------------------- #
def test_probe_end_to_end():
    pre_path = PROJECT_DIR / "data" / "cache" / "drift_post_R28_U2.json"
    post_path = PROJECT_DIR / "data" / "cache" / "drift_post_R29_V3.json"
    if not pre_path.exists() or not post_path.exists():
        pytest.skip("drift reports not generated yet")
    summary = run_probe(
        data_root=PROJECT_DIR / "data",
        pre_drift_path=pre_path,
        post_drift_path=post_path,
    )
    assert summary["verdict"] == "PASS"
    assert summary["drift_count_delta"] >= 3
    assert summary["fixes_applied_count"] >= 1
    assert "computation_artifact" in summary["categorization_pre"]


# --------------------------------------------------------------------------- #
# 10. Synergy helper lookups handle missing keys gracefully                    #
# --------------------------------------------------------------------------- #
def test_synergy_lookups_default_to_zero_on_missing():
    off = {("LAL", "PRBallHandler"): 0.951}
    assert _lookup_pnr_ppp(off, "LAL") == 0.951
    assert _lookup_pnr_ppp(off, "MISSING") == 0.0
    assert _lookup_pnr_ppp(off, "") == 0.0
    assert _lookup_iso_ppp(off, "LAL") == 0.0  # no Isolation key
    assert _lookup_def_iso_ppp({}, "ANY") == 0.0


# --------------------------------------------------------------------------- #
# 11. Sim distribution loader picks up multi-season data                       #
# --------------------------------------------------------------------------- #
def test_sim_distribution_loader(tmp_path):
    p1 = tmp_path / "s1.json"
    p2 = tmp_path / "s2.json"
    p1.write_text(json.dumps([{"sim_win_prob": 0.42, "sim_score_diff_mean": -2.1,
                               "sim_score_diff_std": 9.8, "sim_pace_adj": 0.97}]),
                  encoding="utf-8")
    p2.write_text(json.dumps({"rows": [
        {"sim_win_prob": 0.61, "sim_score_diff_mean": 3.4,
         "sim_score_diff_std": 10.4, "sim_pace_adj": 1.01}
    ]}), encoding="utf-8")
    dists = _load_sim_distributions([p1, p2])
    assert len(dists["sim_win_prob"]) == 2
    assert sorted(dists["sim_win_prob"]) == [0.42, 0.61]
