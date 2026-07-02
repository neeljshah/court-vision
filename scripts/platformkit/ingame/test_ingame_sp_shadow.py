"""Per-file test for the SHADOW-ONLY SP-adjusted in-game probability logger.

OFFLINE + deterministic: fake gamelogs/probables frames + fake params are injected via
SpShadow's constructor -- no real parquet reads, no network. Covers the binding safety
contract: never raises, honest None on any miss, mlb-only, 6h staleness rebuild.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ingame/test_ingame_sp_shadow.py -q
"""
from __future__ import annotations

import math

import pandas as pd

from scripts.platformkit.ingame import ingame_sp_shadow as S


# --------------------------------------------------------------------------------------- #
# fixtures                                                                                  #
# --------------------------------------------------------------------------------------- #
_PARAMS = (0.08, -0.04, 1.78)  # (w, sp_mean, sp_std) -- shape of the real historical fit


def _probables_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"game_pk": 900001, "home_team": "Philadelphia Phillies", "away_team": "Pittsburgh Pirates",
         "home_sp_id": 1, "away_sp_id": 2},
        {"game_pk": 900002, "home_team": "Boston Red Sox", "away_team": "New York Yankees",
         "home_sp_id": 3, "away_sp_id": 4},
    ])


def _gamelogs_df() -> pd.DataFrame:
    # 3 prior starts per pitcher (MIN_PRIOR_STARTS) so sp_diff_ew is non-NaN for game 900001.
    # Pitcher 1 (home, Phillies) allows fewer earned runs (better) than pitcher 2 (away).
    rows = []
    for i in range(3):
        d = pd.Timestamp("2026-04-0%d" % (i + 1))
        rows.append({"game_pk": 800000 + i, "date": d, "player_id": 1, "is_pitcher": True,
                     "earnedRuns": 1.0, "inningsPitched": 6.0})
        rows.append({"game_pk": 800000 + i, "date": d, "player_id": 2, "is_pitcher": True,
                     "earnedRuns": 4.0, "inningsPitched": 6.0})
    # game 900001 itself needs a gamelog row too (the actual start being snapshotted) so
    # build_current_sp_form's walk-forward has a non-NaN pregame snapshot to emit for it.
    d_game = pd.Timestamp("2026-04-10")
    rows.append({"game_pk": 900001, "date": d_game, "player_id": 1, "is_pitcher": True,
                "earnedRuns": 1.0, "inningsPitched": 6.0})
    rows.append({"game_pk": 900001, "date": d_game, "player_id": 2, "is_pitcher": True,
                "earnedRuns": 4.0, "inningsPitched": 6.0})
    prob_hist = pd.DataFrame([
        {"game_pk": 800000 + i, "home_sp_id": 1, "away_sp_id": 2} for i in range(3)
    ])
    # game 900001 itself needs to be in probables (already is, in _probables_df).
    gl = pd.DataFrame(rows)
    return gl, prob_hist


def _shadow(**kw) -> S.SpShadow:
    gl, prob_hist = _gamelogs_df()
    full_probables = pd.concat([prob_hist, _probables_df()[["game_pk", "home_sp_id", "away_sp_id"]]],
                               ignore_index=True)
    probables = _probables_df()
    kw.setdefault("gamelogs_df", gl.copy())
    kw.setdefault("probables_df", pd.concat(
        [full_probables, probables[["game_pk"]].assign(
            home_team=probables["home_team"], away_team=probables["away_team"])],
        axis=0, ignore_index=True, sort=False).drop_duplicates("game_pk", keep="last"))
    kw.setdefault("params", _PARAMS)
    return S.SpShadow(**kw)


def _merged_probables() -> pd.DataFrame:
    """probables frame carrying BOTH the SP-id columns (for _identify_starts) and the
    team-name columns (for the team index) across the historical + slate rows."""
    gl, prob_hist = _gamelogs_df()
    slate = _probables_df()
    hist = prob_hist.copy()
    hist["home_team"] = "Philadelphia Phillies"
    hist["away_team"] = "Pittsburgh Pirates"
    return pd.concat([hist, slate], ignore_index=True, sort=False)


def _real_shadow(**kw) -> S.SpShadow:
    gl, _ = _gamelogs_df()
    kw.setdefault("gamelogs_df", gl)
    kw.setdefault("probables_df", _merged_probables())
    kw.setdefault("params", _PARAMS)
    return S.SpShadow(**kw)


# --------------------------------------------------------------------------------------- #
# tests                                                                                     #
# --------------------------------------------------------------------------------------- #
def test_known_matchup_returns_adjusted_prob():
    shadow = _real_shadow()
    out = shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55)
    assert out is not None
    assert isinstance(out, float)
    assert 0.0 <= out <= 1.0
    # home SP historically stingier with runs -> sp_diff_ew > 0 -> adjustment should not
    # push the home prob down relative to the raw model prob.
    assert out >= 0.55 - 1e-9


def test_game_pk_lookup_matches_team_lookup():
    shadow = _real_shadow()
    by_teams = shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55)
    by_pk = shadow.shadow_prob("mlb", "Unknown A", "Unknown B", 0.55, game_pk=900001)
    assert by_teams is not None and by_pk is not None
    assert math.isclose(by_teams, by_pk, rel_tol=1e-9)


def test_unknown_matchup_is_none():
    shadow = _real_shadow()
    assert shadow.shadow_prob("mlb", "Made Up Team", "Also Made Up", 0.55) is None


def test_non_mlb_sport_is_none():
    shadow = _real_shadow()
    assert shadow.shadow_prob("soccer_intl", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55) is None


def test_bad_p_model_is_none_never_raises():
    shadow = _real_shadow()
    assert shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", float("nan")) is None
    assert shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", "not-a-float") is None
    assert shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 1.7) is None


def test_poisoned_build_returns_none_and_never_raises():
    shadow = S.SpShadow(probables_path="does/not/exist.parquet",
                        gamelogs_path="does/not/exist.parquet", params=None)
    out = shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55)
    assert out is None
    # a second call still must not raise, and stays permanently broken (no retry storm).
    assert shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.60) is None


def test_missing_params_in_verdict_json_is_honest_none(tmp_path):
    import json
    bad_verdict = tmp_path / "verdict.json"
    bad_verdict.write_text(json.dumps({"forward_eval_2026": {}}), encoding="utf-8")
    gl, _ = _gamelogs_df()
    shadow = S.SpShadow(verdict_path=bad_verdict, gamelogs_df=gl,
                        probables_df=_merged_probables(), params=None)
    assert shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55) is None


def test_staleness_triggers_rebuild_with_fake_clock():
    calls = {"n": 0}
    real_build = S.SpShadow._build

    def _counting_build(self):
        calls["n"] += 1
        real_build(self)

    now = {"t": 1000.0}
    shadow = _real_shadow(clock=lambda: now["t"])
    shadow._build = _counting_build.__get__(shadow, S.SpShadow)  # type: ignore[method-assign]

    shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55)
    assert calls["n"] == 1
    # well within 6h -> cached, no rebuild.
    now["t"] += 60.0
    shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55)
    assert calls["n"] == 1
    # past STALE_AFTER_SEC -> rebuild fires.
    now["t"] += S.STALE_AFTER_SEC + 1.0
    shadow.shadow_prob("mlb", "Philadelphia Phillies", "Pittsburgh Pirates", 0.55)
    assert calls["n"] == 2


def test_get_shadow_singleton_is_stable():
    a = S.get_shadow()
    b = S.get_shadow()
    assert a is b
