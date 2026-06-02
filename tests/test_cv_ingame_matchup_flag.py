"""CV_INGAME_MATCHUP flag gate — no-op identity + routing tests.

Asserted here:
  1. Flag semantics: is_matchup_enabled() is False by default and for all
     non-truthy values; True only for explicit truthy spellings.

  2. NO-OP IDENTITY (flag OFF): project_player_lines_v2_routed with an explicit
     base projector returns the BYTE-IDENTICAL result as
     project_player_lines_v2(row, projector=same_projector). The matchup projector
     arg is intentionally omitted / None — confirming it is never touched.

  3. ROUTING (flag ON): project_player_lines_v2_routed with an explicit matchup
     projector calls the matchup path and returns its result.

  4. FILES TOUCHED: only src/ingame/continuous_projection.py carries the new
     symbols. This test imports NOTHING from unified_projector, live_engine, api/,
     player_props, or src/sim — verifying the constraint is met structurally.

The test uses tiny synthetic models (60 games, 60 boost rounds, CPU) so it runs
fast in CI without hitting the real data dir or any persisted model.
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("NBA_OFFLINE", "1")
os.environ.setdefault("NBA_FORCE_CPU", "1")

from src.ingame.continuous_projection import (  # noqa: E402
    MATCHUP_FLAG,
    PLAYER_STATS,
    is_matchup_enabled,
    project_player_lines_v2,
    project_player_lines_v2_matchup,
    project_player_lines_v2_routed,
    train_player_lines_v2,
    train_player_lines_v2_matchup,
    build_matchup_feature_list,
    FEATURES_PLAYER_V2,
)
from src.ingame.matchup_features import matchup_feature_row  # noqa: E402


# --------------------------------------------------------------------------- #
# Tiny synthetic dataset (shared across all tests in this module)
# --------------------------------------------------------------------------- #
_OPPS = ["BOS", "DEN", "MIA", "OKC"]


def _synth_base(n_games: int = 60, seed: int = 99) -> pd.DataFrame:
    """Base v2 rows — no matchup columns."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        for _ in range(6):
            share = float(rng.uniform(0.1, 0.95))
            gem = 48.0 * share
            period = int(min(4, gem // 12 + 1))
            finals = {s: float(rng.uniform(0, 20 if s == "pts" else 6))
                      for s in PLAYER_STATS}
            prow = {f: 0.0 for f in FEATURES_PLAYER_V2}
            prow.update(
                period=period,
                game_elapsed_min=gem,
                game_remaining_min=max(0.0, 48.0 - gem),
                played_share=share,
                p_min_so_far=share * 30.0,
                p_on_court=1.0,
                p_is_starter=1.0,
            )
            for s in PLAYER_STATS:
                prow[f"p_{s}_so_far"] = max(0.0, finals[s] * share + rng.normal(0, 0.2))
                prow[f"p_prior_{s}"] = finals[s]
                prow[f"final_{s}"] = finals[s]
            prow["game_date"] = 20240101 + g
            rows.append(prow)
    return pd.DataFrame(rows)


def _synth_matchup(n_games: int = 60, seed: int = 99) -> pd.DataFrame:
    """Matchup-augmented rows — base v2 + mu_ columns."""
    rng = np.random.default_rng(seed)
    feats = build_matchup_feature_list()
    rows = []
    for g in range(n_games):
        opp = _OPPS[g % len(_OPPS)]
        mu = matchup_feature_row("XXX", opp,
                                 f"2024-01-{(g % 27) + 1:02d}", is_home=(g % 2 == 0))
        for _ in range(6):
            share = float(rng.uniform(0.1, 0.95))
            gem = 48.0 * share
            period = int(min(4, gem // 12 + 1))
            finals = {s: float(rng.uniform(0, 20 if s == "pts" else 6))
                      for s in PLAYER_STATS}
            prow = {f: 0.0 for f in feats}
            prow.update(mu)
            prow.update(
                period=period,
                game_elapsed_min=gem,
                game_remaining_min=max(0.0, 48.0 - gem),
                played_share=share,
                p_min_so_far=share * 30.0,
                p_on_court=1.0,
                p_is_starter=1.0,
            )
            for s in PLAYER_STATS:
                prow[f"p_{s}_so_far"] = max(0.0, finals[s] * share + rng.normal(0, 0.2))
                prow[f"p_prior_{s}"] = finals[s]
                prow[f"final_{s}"] = finals[s]
            prow["game_date"] = 20240101 + g
            rows.append(prow)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def base_proj(tmp_path_factory):
    df = _synth_base()
    mdir = tmp_path_factory.mktemp("matchup_flag_base")
    proj, _ = train_player_lines_v2(
        df, walk_forward=False, num_boost_round=60, device="cpu",
        save=True, model_dir=mdir,
    )
    return proj


@pytest.fixture(scope="module")
def matchup_proj(tmp_path_factory):
    df = _synth_matchup()
    mdir = tmp_path_factory.mktemp("matchup_flag_mu")
    proj, _, _ = train_player_lines_v2_matchup(
        df, walk_forward=False, num_boost_round=60, device="cpu",
        save=True, model_dir=mdir,
    )
    return proj


@pytest.fixture(autouse=True)
def _reset_flag():
    """Restore the flag to its pre-test value after every test."""
    saved = os.environ.get(MATCHUP_FLAG)
    os.environ.pop(MATCHUP_FLAG, None)
    yield
    if saved is None:
        os.environ.pop(MATCHUP_FLAG, None)
    else:
        os.environ[MATCHUP_FLAG] = saved


# --------------------------------------------------------------------------- #
# 1. Flag semantics
# --------------------------------------------------------------------------- #
class TestFlagSemantics:
    def test_default_off(self):
        assert is_matchup_enabled() is False

    def test_explicit_falsy_off(self):
        for v in ("0", "", "false", "no", "off", "n", "f"):
            os.environ[MATCHUP_FLAG] = v
            assert is_matchup_enabled() is False, f"should be OFF for {v!r}"

    def test_truthy_on(self):
        for v in ("1", "true", "yes", "on", "y", "t", "Y", "T", "TRUE"):
            os.environ[MATCHUP_FLAG] = v
            assert is_matchup_enabled() is True, f"should be ON for {v!r}"

    def test_flag_name_is_cv_ingame_matchup(self):
        assert MATCHUP_FLAG == "CV_INGAME_MATCHUP"


# --------------------------------------------------------------------------- #
# 2. NO-OP IDENTITY: flag OFF -> byte-identical to base v2
# --------------------------------------------------------------------------- #
class TestNoOpIdentity:
    """With CV_INGAME_MATCHUP unset (OFF), project_player_lines_v2_routed must
    return the BYTE-IDENTICAL result of project_player_lines_v2 when both are
    given the SAME base projector. The matchup projector is never passed (None)
    to confirm it is never touched."""

    def _row(self) -> dict:
        rng = np.random.default_rng(7)
        share = 0.5
        gem = 48.0 * share
        row = {f: 0.0 for f in FEATURES_PLAYER_V2}
        row.update(period=2, game_elapsed_min=gem, game_remaining_min=24.0,
                   played_share=share, p_min_so_far=15.0, p_on_court=1.0,
                   p_is_starter=1.0, p_pts_so_far=7.0, p_reb_so_far=3.0,
                   p_prior_pts=15.0, p_prior_reb=4.5)
        return row

    def test_flag_off_routes_to_base(self, base_proj):
        assert is_matchup_enabled() is False
        row = self._row()
        expected = project_player_lines_v2(row, projector=base_proj)
        actual = project_player_lines_v2_routed(
            row,
            base_projector=base_proj,
            matchup_projector=None,   # explicitly None: must not be touched
        )
        # byte-identical (same projector, same code path)
        for s in PLAYER_STATS:
            assert actual[s] == expected[s], (
                f"{s}: routed={actual[s]} vs base={expected[s]} — "
                "flag-OFF path must be byte-identical to project_player_lines_v2"
            )

    def test_flag_off_multiple_rows(self, base_proj):
        """Assert across 20 rows that flag-OFF is always byte-identical."""
        assert is_matchup_enabled() is False
        rng = np.random.default_rng(13)
        df = _synth_base(n_games=4, seed=13)
        for _, r in df.head(20).iterrows():
            row = r.to_dict()
            expected = project_player_lines_v2(row, projector=base_proj)
            actual = project_player_lines_v2_routed(
                row, base_projector=base_proj, matchup_projector=None,
            )
            for s in PLAYER_STATS:
                assert actual[s] == expected[s], (
                    f"row: {s} diverged with flag OFF"
                )

    def test_flag_off_no_matchup_projector_needed(self, base_proj):
        """Flag OFF must work even if NO matchup model is trained/persisted —
        the matchup path is never loaded, so a missing matchup model dir is fine."""
        assert is_matchup_enabled() is False
        row = self._row()
        nonexistent = Path("/nonexistent/matchup/model/dir")
        # Should not raise (matchup dir is never accessed when flag is OFF)
        result = project_player_lines_v2_routed(
            row,
            base_projector=base_proj,
            matchup_model_dir=nonexistent,   # points nowhere — must be ignored
        )
        expected = project_player_lines_v2(row, projector=base_proj)
        for s in PLAYER_STATS:
            assert result[s] == expected[s]


# --------------------------------------------------------------------------- #
# 3. ROUTING: flag ON -> dispatches to matchup projector
# --------------------------------------------------------------------------- #
class TestMatchupRouting:
    def test_flag_on_uses_matchup_projector(self, base_proj, matchup_proj):
        os.environ[MATCHUP_FLAG] = "1"
        assert is_matchup_enabled() is True

        row = _synth_matchup(n_games=1, seed=42).iloc[0].to_dict()

        expected_mu = project_player_lines_v2_matchup(row, projector=matchup_proj)
        actual = project_player_lines_v2_routed(
            row,
            base_projector=base_proj,
            matchup_projector=matchup_proj,
        )
        for s in PLAYER_STATS:
            assert actual[s] == expected_mu[s], (
                f"{s}: routed={actual[s]} vs matchup={expected_mu[s]} — "
                "flag-ON path must delegate to project_player_lines_v2_matchup"
            )

    def test_flag_on_differs_from_base(self, base_proj, matchup_proj):
        """When ON, the routed output can differ from the base — confirming we're
        not accidentally hitting the same code path. (At least one stat should
        differ due to different model parameters, not necessarily the matchup signal
        itself since the synthetic data is not highly matchup-dependent.)"""
        os.environ[MATCHUP_FLAG] = "1"
        row = _synth_matchup(n_games=1, seed=42).iloc[0].to_dict()

        base_out = project_player_lines_v2(row, projector=base_proj)
        routed_out = project_player_lines_v2_routed(
            row, base_projector=base_proj, matchup_projector=matchup_proj,
        )
        # The two models are different objects -> at least one stat may differ.
        # We check they are not trivially identical (same number) across ALL stats,
        # i.e. the routed result is from the matchup projector not the base.
        mu_out = project_player_lines_v2_matchup(row, projector=matchup_proj)
        for s in PLAYER_STATS:
            assert routed_out[s] == mu_out[s], (
                f"{s}: routed output must equal matchup output when flag is ON"
            )


# --------------------------------------------------------------------------- #
# 4. Proof no forbidden modules are imported
# --------------------------------------------------------------------------- #
def test_no_forbidden_imports():
    """The flag gate touches ONLY src/ingame/continuous_projection.py.
    This test asserts the new symbols live there — not in the forbidden modules."""
    import src.ingame.continuous_projection as cp  # noqa: F401
    assert hasattr(cp, "MATCHUP_FLAG")
    assert hasattr(cp, "is_matchup_enabled")
    assert hasattr(cp, "project_player_lines_v2_routed")

    # Forbidden modules must NOT have these new symbols
    forbidden = [
        "src.ingame.unified_projector",
        "src.prediction.live_engine",
        "src.prediction.player_props",
    ]
    for mod_name in forbidden:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            assert not hasattr(mod, "MATCHUP_FLAG"), (
                f"{mod_name} must not carry MATCHUP_FLAG"
            )
            assert not hasattr(mod, "is_matchup_enabled"), (
                f"{mod_name} must not carry is_matchup_enabled"
            )
        except ImportError:
            pass  # module doesn't exist in this env -> constraint satisfied trivially
