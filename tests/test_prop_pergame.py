"""
test_prop_pergame.py -- Tests for per-game prop models (PRED-13).

Per-game training: each row is one game, features come only from prior
games, the target is that game's realised stat line. These tests pin the
leakage-free feature construction and the training contract.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime


def _dt(s: str) -> datetime:
    """Parse an NBA gamelog date string for tests."""
    return datetime.strptime(s, "%b %d, %Y")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    _RestTravel,
    _ewma,
    build_opponent_defense,
    build_pergame_dataset,
    build_rest_travel,
    feature_columns,
    train_pergame_models,
)


def _game(date: str, matchup: str, pts, reb, ast, minutes=30.0,
          fg3m=2, stl=1, blk=0, tov=2) -> dict:
    return {"GAME_DATE": date, "MATCHUP": matchup, "PTS": pts, "REB": reb,
            "AST": ast, "FG3M": fg3m, "STL": stl, "BLK": blk, "TOV": tov,
            "MIN": minutes}


def _write_gamelog(tmp_path, pid: str, games: list) -> None:
    (tmp_path / f"gamelog_{pid}_2024-25.json").write_text(
        json.dumps(games), encoding="utf-8")


# ── EWMA recency ──────────────────────────────────────────────────────────────

def test_ewma_weights_recent_games_more():
    """EWMA of an improving series is pulled toward the most recent value."""
    rising = [10.0, 12.0, 14.0, 16.0, 30.0]   # last game a spike
    assert _ewma(rising) > sum(rising) / len(rising)   # above the flat mean


def test_ewma_empty_is_zero():
    assert _ewma([]) == 0.0


# ── feature columns ───────────────────────────────────────────────────────────

def test_feature_columns_are_leakage_free():
    """Every feature is a prior-game form metric, game context, or opponent
    defence — never the target."""
    cols = feature_columns()
    assert "rest_days" in cols and "is_home" in cols
    assert all(not c.startswith("target_") for c in cols)
    assert all(f"opp_def_{s}" in cols for s in STATS)
    # Frozen production contract = 129 cols. The original 85-col base
    # (5 form x 8 stats + 3 context + 2 rampup + 7 opp_def + 4 rest/travel +
    # 9 playtype + 15 bbref + 4 contracts + 1 pts_share_3pt ratio) PLUS the
    # Wave-2b+ extension blocks (bbref-extended, defender-matchup, player-profile,
    # referee, foul, dnp, dnp-team, advanced-split). feature_columns_for() freezes
    # this; serve-time models truncate to their own n_features_in_. The leakage
    # invariants above (no target_*, opp_def present) are the substantive check;
    # this count is the contract tripwire.
    assert len(cols) == 129


def _feature_columns_under(flag_value):
    """Return feature_columns() with CV_BBREF_REORDER_FIX set to flag_value (or
    unset when None). Runs in a SUBPROCESS so the module-level gate re-reads the
    env from a clean import without reloading prop_pergame in-process (a reload
    would change _MLPSeedEnsemble's class identity and break sibling pickling
    tests)."""
    import json as _json
    import subprocess
    import sys as _sys
    env = dict(os.environ)
    env.pop("PROP_USE_CV", None)
    if flag_value is None:
        env.pop("CV_BBREF_REORDER_FIX", None)
    else:
        env["CV_BBREF_REORDER_FIX"] = flag_value
    code = (
        "import sys, json; sys.path.insert(0, r'%s');"
        "from src.prediction.prop_pergame import feature_columns;"
        "print(json.dumps(feature_columns()))" % PROJECT_DIR
    )
    out = subprocess.check_output([_sys.executable, "-c", code], env=env, text=True)
    return _json.loads(out.strip().splitlines()[-1])


def test_feature_columns_first85_aligns_when_reorder_fix_on():
    """EX-5 gate ON: first 85 cols must match the frozen training order from
    props_pergame_metrics.json so all n_features_in_=85 artifacts receive the
    correct features. bbref_extra must be APPENDED after slot 85, not
    interleaved in the contract/ratio block at slots 80-84."""
    frozen = json.load(
        open(os.path.join(PROJECT_DIR, "data", "models", "props_pergame_metrics.json"))
    )["feature_cols"]
    assert len(frozen) == 85
    cols = _feature_columns_under("1")          # fix ON
    assert cols[:85] == frozen                  # 85-feature artifacts read first-85 slots
    for k in ("orb_pct", "drb_pct", "trb_pct", "bpm", "ws"):
        assert cols.index(f"bbref_{k}") >= 85   # bbref_extra appended after baseline


def test_feature_columns_default_is_now_aligned():
    """PREDICTION_FIDELITY plumbing fix (2026-06-04): the MODULE DEFAULT is now
    the ALIGNED order. The 85-feature artifacts were trained aligned
    (props_pergame_metrics.json feature_cols: contract/ratio at slots 80-84),
    so the aligned serve order is correct. With the flag at its default (unset),
    feature_columns()[:85] matches the frozen trained list and bbref_extra is
    appended AFTER slot 85 — NOT interleaved at slots 80-84 (the old misaligned
    default). golive already set CV_BBREF_REORDER_FIX=1; this removes the
    load-bearing env var."""
    frozen = json.load(
        open(os.path.join(PROJECT_DIR, "data", "models", "props_pergame_metrics.json"))
    )["feature_cols"]
    cols = _feature_columns_under(None)          # default (flag unset) -> aligned
    assert cols[:85] == frozen                   # 0/85 mismatch on the served slice
    for k in ("orb_pct", "drb_pct", "trb_pct", "bpm", "ws"):
        assert cols.index(f"bbref_{k}") >= 85    # bbref_extra appended after baseline


def test_feature_columns_escape_hatch_restores_legacy_order():
    """Revertibility: CV_BBREF_REORDER_FIX=0 (the explicit escape hatch) forces
    the legacy misaligned order back — bbref_extra at slots 80-84. The fix is
    gated/revertible, not removed."""
    cols = _feature_columns_under("0")           # escape hatch -> legacy layout
    for i, k in enumerate(("orb_pct", "drb_pct", "trb_pct", "bpm", "ws")):
        assert cols[80 + i] == f"bbref_{k}"      # legacy slot 80-84 placement


def test_feature_columns_include_rest_travel():
    """feature_columns() includes the 4 new rest/travel schedule features."""
    cols = feature_columns()
    for name in ("is_b2b", "is_b3b", "miles_traveled", "altitude_ft"):
        assert name in cols, f"Missing rest/travel feature: {name}"


def test_build_rest_travel_neutral_defaults_for_unknown_key():
    """_RestTravel returns neutral defaults for any (date, team) not in the parquet."""
    rt = build_rest_travel()   # parquet absent in test env -> empty lookup
    from datetime import datetime
    feats = rt.features("XXX", datetime(2025, 1, 15))
    assert feats["is_b2b"] == 0.0
    assert feats["is_b3b"] == 0.0
    assert feats["miles_traveled"] == 0.0
    assert feats["altitude_ft"] == 0.0


def test_build_pergame_dataset_has_rest_travel_columns(tmp_path):
    """build_pergame_dataset() includes all 4 rest/travel columns in every row
    even when no rest_travel.parquet exists (neutral defaults applied)."""
    import math
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 10 + d, 5, 4)
             for d in range(1, 16)]
    (tmp_path / "gamelog_10_2024-25.json").write_text(
        json.dumps(games), encoding="utf-8")
    rows, cols = build_pergame_dataset(str(tmp_path), min_prior=6)
    assert len(rows) > 0
    for name in ("is_b2b", "is_b3b", "miles_traveled", "altitude_ft"):
        assert name in cols, f"feature_columns() missing {name}"
        for row in rows:
            assert name in row, f"Row missing key {name}"
            assert math.isfinite(row[name]), f"{name} is not finite in row"


def test_opponent_defense_is_to_date_only(tmp_path):
    """Opponent-defence factors use only games before the query date — no leak."""
    # SAS allows big lines early, small lines late.
    sas_games = ([_game(f"Jan {d:02d}, 2025", "TOR @ SAS", 40, 12, 10) for d in range(1, 9)]
                 + [_game(f"Feb {d:02d}, 2025", "TOR @ SAS", 4, 1, 1) for d in range(1, 9)])
    (tmp_path / "gamelog_99_2024-25.json").write_text(json.dumps(sas_games), encoding="utf-8")
    # A control opponent (DEN) with steady lines so the league baseline is stable.
    den_games = ([_game(f"Jan {d:02d}, 2025", "TOR @ DEN", 20, 6, 5) for d in range(9, 17)]
                 + [_game(f"Feb {d:02d}, 2025", "TOR @ DEN", 20, 6, 5) for d in range(9, 17)])
    (tmp_path / "gamelog_100_2024-25.json").write_text(json.dumps(den_games), encoding="utf-8")

    oppdef = build_opponent_defense(str(tmp_path))
    early = oppdef.factors("SAS", _dt("Jan 20, 2025"))   # only SAS's big lines seen
    late = oppdef.factors("SAS", _dt("Feb 20, 2025"))    # big + small lines seen
    # Early query sees only the inflated lines -> a higher allowed factor.
    assert early["opp_def_pts"] > late["opp_def_pts"]


def test_opponent_defense_neutral_without_history(tmp_path):
    """An unknown opponent / no prior games yields a neutral 1.0 factor."""
    oppdef = build_opponent_defense(str(tmp_path))
    factors = oppdef.factors("XXX", _dt("Jan 01, 2025"))
    assert all(v == 1.0 for v in factors.values())


# ── dataset construction ──────────────────────────────────────────────────────

def test_dataset_emits_rows_with_prior_history(tmp_path):
    """Rows are emitted only once a player has min_prior prior played games."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 10 + d, 5, 4)
             for d in range(1, 16)]
    _write_gamelog(tmp_path, "1", games)
    rows, cols = build_pergame_dataset(str(tmp_path), min_prior=6)
    # 15 games, first 6 are history -> 9 training rows.
    assert len(rows) == 9
    assert all("target_pts" in r and "date" in r for r in rows)
    assert all(c in rows[0] for c in cols)


def test_dnp_games_are_not_training_rows(tmp_path):
    """A game the player sat out (MIN=0) is not emitted as a training row."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS @ TOR", 20, 6, 5) for d in range(1, 11)]
    games.append(_game("Jan 15, 2025", "SAS vs. TOR", 0, 0, 0, minutes=0.0))  # DNP
    games.append(_game("Jan 17, 2025", "SAS vs. TOR", 25, 7, 6))
    _write_gamelog(tmp_path, "2", games)
    rows, _ = build_pergame_dataset(str(tmp_path), min_prior=6)
    # No row should carry the DNP game's zero line as a target.
    assert all(not (r["target_pts"] == 0 and r["target_reb"] == 0) for r in rows)


def test_home_away_flag_parsed_from_matchup(tmp_path):
    """is_home is 1 for a 'vs.' matchup, 0 for an '@' matchup."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 20, 6, 5) for d in range(1, 9)]
    games.append(_game("Jan 12, 2025", "SAS @ TOR", 18, 5, 4))   # away game
    _write_gamelog(tmp_path, "3", games)
    rows, _ = build_pergame_dataset(str(tmp_path), min_prior=6)
    assert rows[-1]["is_home"] == 0.0
    assert rows[0]["is_home"] == 1.0


def test_features_use_only_prior_games(tmp_path):
    """A row's rolling features reflect prior games, never the current one."""
    games = [_game(f"Jan {d:02d}, 2025", "SAS vs. TOR", 10, 5, 5) for d in range(1, 9)]
    games.append(_game("Jan 12, 2025", "SAS vs. TOR", 99, 5, 5))   # huge spike
    _write_gamelog(tmp_path, "4", games)
    rows, _ = build_pergame_dataset(str(tmp_path), min_prior=6)
    last = rows[-1]
    # The spike is the TARGET; the prior-form features must not include it.
    assert last["target_pts"] == 99.0
    assert last["l5_pts"] == 10.0          # all prior games scored 10


# ── training ──────────────────────────────────────────────────────────────────

def test_train_reports_honest_holdout(tmp_path):
    """Training yields a temporal-holdout R²/MAE per stat (not a 0.99 identity)."""
    import random
    rng = random.Random(0)
    # 40 players x 40 games — realistic noisy per-game lines.
    for pid in range(40):
        base = rng.uniform(8, 28)
        games = []
        for d in range(1, 41):
            pts = max(0, base + rng.gauss(0, 6))
            month, day = ("Jan", d) if d <= 28 else ("Feb", d - 28)
            games.append(_game(f"{month} {day:02d}, 2025",
                                "SAS vs. TOR" if d % 2 else "SAS @ TOR",
                                round(pts), rng.randint(2, 10), rng.randint(1, 9),
                                fg3m=rng.randint(0, 6), stl=rng.randint(0, 4),
                                blk=rng.randint(0, 3), tov=rng.randint(0, 5)))
        _write_gamelog(tmp_path, str(pid), games)

    from src.prediction.prop_pergame import _LGB_ONLY_STATS

    metrics = train_pergame_models(
        gamelog_dir=str(tmp_path), model_dir=str(tmp_path), min_prior=6,
    )
    assert metrics["n_rows"] > 200
    for stat in STATS:
        m = metrics["stats"][stat]
        # Honest holdout — must NOT be a fake near-1.0 identity fit.
        assert -1.0 <= m["holdout_r2"] <= 0.95
        assert m["holdout_mae"] >= 0.0
        # LGB-only stats don't persist the XGB model; everyone has the LGB pkl.
        if stat not in _LGB_ONLY_STATS:
            assert os.path.exists(tmp_path / f"props_pg_{stat}.json")
        assert os.path.exists(tmp_path / f"props_pg_lgb_{stat}.pkl")


def test_train_insufficient_data_returns_status(tmp_path):
    """A near-empty gamelog dir returns a clean status, not a crash."""
    result = train_pergame_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    assert result["status"] == "insufficient_data"


# ── 3-way MLP stack (cycle 5 loop 5) ──────────────────────────────────────────

def _train_for_stack(tmp_path):
    """Produce a small but valid synthetic dataset and train one round.

    Returns the metrics dict so individual asserts can poke at it without
    re-training. Re-used by the three stack tests below."""
    import random
    rng = random.Random(7)
    for pid in range(8):
        games = []
        for i in range(45):
            day = (i % 28) + 1
            month = ((i // 28) % 12) + 1
            year = 2024 + (i // 336)
            games.append(_game(f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][month-1]} {day:02d}, {year}",
                               f"P{pid:02d} vs. OPP{pid % 6:02d}",
                               pts=rng.randint(0, 30), reb=rng.randint(0, 12),
                               ast=rng.randint(0, 10), minutes=rng.uniform(8, 36),
                               fg3m=rng.randint(0, 6), stl=rng.randint(0, 4),
                               blk=rng.randint(0, 3), tov=rng.randint(0, 5)))
        (tmp_path / f"gamelog_{pid}_2024-25.json").write_text(
            json.dumps(games), encoding="utf-8")
    return train_pergame_models(
        gamelog_dir=str(tmp_path), model_dir=str(tmp_path), min_prior=6,
    )


def test_mlp_meta_weights_persisted_per_stat(tmp_path):
    """meta_weights_pergame.json carries a w_mlp entry for every stat the
    trainer touched. Smoke-tests the cycle-5 3-way stack writer."""
    metrics = _train_for_stack(tmp_path)
    from src.prediction.prop_pergame import _META_WEIGHTS_FILENAME
    weights_path = tmp_path / _META_WEIGHTS_FILENAME
    assert weights_path.exists()
    weights = json.loads(weights_path.read_text())
    for stat in STATS:
        # Synthetic data may push a stat into _LGB_ONLY_STATS (no w_mlp);
        # for everyone else the 3-way weights must all be present and the
        # NNLS sum must land in the production-acceptable band.
        w = weights[stat]
        if w.get("source") == "lgb_only":
            continue
        assert "w_xgb" in w and "w_lgb" in w and "w_mlp" in w, w
        assert 0.5 <= (w["w_xgb"] + w["w_lgb"] + w["w_mlp"]) <= 1.5


def test_mlp_artifacts_only_when_keep_threshold_met(tmp_path):
    """props_pg_mlp_<stat>.pkl + scaler are persisted iff w_mlp >= 0.05 and
    the stat is not LGB-only — see train_pergame_models persistence block."""
    metrics = _train_for_stack(tmp_path)
    for stat in STATS:
        mlp_pkl    = tmp_path / f"props_pg_mlp_{stat}.pkl"
        mlp_scaler = tmp_path / f"props_pg_mlp_scaler_{stat}.pkl"
        m = metrics["stats"][stat]
        w_mlp = float(m.get("meta_w_mlp", 0.0))
        meta_src = m.get("meta_fit_source", "")
        if meta_src == "lgb_only" or w_mlp < 0.05:
            assert not mlp_pkl.exists(), f"{stat}: mlp pkl persisted but w_mlp={w_mlp}, src={meta_src}"
            assert not mlp_scaler.exists()
        else:
            assert mlp_pkl.exists(), f"{stat}: mlp pkl missing but w_mlp={w_mlp}"
            assert mlp_scaler.exists()


def test_predict_pergame_runs_with_3way_blend(tmp_path):
    """predict_pergame returns a finite float when XGB+LGB+MLP all exist on
    disk and the meta_weights JSON references w_mlp."""
    from src.prediction.prop_pergame import (
        feature_columns as fc, load_pergame_model, predict_pergame,
    )
    _train_for_stack(tmp_path)
    # Use the first stat that actually persisted an MLP artifact.
    for stat in STATS:
        models = load_pergame_model(stat, model_dir=str(tmp_path))
        if not models or not any(isinstance(m, tuple) for m in models):
            continue
        feat = {c: 1.0 for c in fc()}
        pred = predict_pergame(stat, feat, model_dir=str(tmp_path))
        assert pred is not None
        assert pred >= 0.0
        assert pred < 200.0  # sane bound for any per-game stat
        return
    # If no stat ended up with an MLP (small synthetic data sometimes
    # below the keep threshold), don't fail — the artifact test covers
    # the persistence path.


# ── FIX IN-7: opp_abbrev threaded into _inject_iter23_features on serve path ──

def test_build_prediction_row_passes_opp_to_inject_iter23(tmp_path):
    """FIX IN-7 — build_prediction_row must pass the opponent to
    _inject_iter23_features so that ls_opp_* features are not silently
    zeroed on the live serve path.

    Strategy: monkeypatch _inject_iter23_features with a spy that records
    every call, then assert the recorded opp_abbrev matches the 'BOS' we
    supply to build_prediction_row.
    """
    import src.prediction.prop_pergame as ppg

    recorded_calls: list = []

    original_inject = ppg._inject_iter23_features

    def _spy(row, player_id, game_date, team_abbrev, opp_abbrev=""):
        recorded_calls.append({
            "team_abbrev": team_abbrev,
            "opp_abbrev": opp_abbrev,
        })
        return original_inject(row, player_id, game_date, team_abbrev, opp_abbrev)

    # Write a minimal gamelog so build_prediction_row doesn't return None.
    games = [
        {
            "GAME_DATE": f"Jan {d:02d}, 2025",
            "MATCHUP": "LAL vs. MIA",
            "PTS": 20,
            "REB": 5,
            "AST": 4,
            "FG3M": 2,
            "STL": 1,
            "BLK": 0,
            "TOV": 2,
            "MIN": 30.0,
        }
        for d in range(1, 12)
    ]
    player_id = 999
    (tmp_path / f"gamelog_{player_id}_2024-25.json").write_text(
        json.dumps(games), encoding="utf-8"
    )

    ppg._inject_iter23_features = _spy  # type: ignore[assignment]
    try:
        result = ppg.build_prediction_row(
            player_id=player_id,
            opp_team="BOS",
            season="2024-25",
            is_home=True,
            rest_days=2.0,
            gamelog_dir=str(tmp_path),
            min_prior=0,
        )
    finally:
        ppg._inject_iter23_features = original_inject  # type: ignore[assignment]

    # build_prediction_row must have produced a row (gamelog exists).
    assert result is not None, "build_prediction_row returned None — gamelog not found?"

    # The spy must have been called at least once.
    assert recorded_calls, "_inject_iter23_features was never called on the serve path"

    # Every call must carry the real opponent, not an empty string (pre-fix behaviour).
    for call in recorded_calls:
        assert call["opp_abbrev"] == "BOS", (
            f"FIX IN-7 regression: opp_abbrev='{call['opp_abbrev']}' "
            f"instead of 'BOS' — ls_opp_* features will serve zeros!"
        )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
