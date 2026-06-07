"""tests/test_playoff_pregame_guard.py — CV_PLAYOFF_PREGAME_GUARD gated guard.

Four invariants verified:

1. Flag OFF (default): byte-identical behavior — REB/PTS still pass on
   playoff game_ids exactly as they do today.
2. Flag ON: ALL pregame props blocked on playoff game_ids (prefix 004).
3. Regular-season games unaffected by the flag in either state.
4. The existing AST guard still fires independently (guard 2 still works
   when the broader guard is OFF).

Evidence: docs/_audits/PLAYOFF_PREGAME_EDGE.md — all four stats are
negative-ROI at real 2026 playoff odds; model MAE > line MAE on all four.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.prediction import bet_policy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PLAYOFF_GID = "0042500317"      # 2026 Finals game — prefix 004
_REGSEASON_GID = "0022400123"    # regular-season game — prefix 002
_STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


@pytest.fixture(autouse=True)
def _clean_playoff_guard_env():
    """Remove CV_PLAYOFF_PREGAME_GUARD and CV_ALLOW_PLAYOFF_PREGAME between tests."""
    saved_guard = os.environ.pop("CV_PLAYOFF_PREGAME_GUARD", None)
    saved_allow = os.environ.pop("CV_ALLOW_PLAYOFF_PREGAME", None)
    saved_ast   = os.environ.pop("CV_ALLOW_PLAYOFF_AST", None)
    try:
        yield
    finally:
        for k, v in [
            ("CV_PLAYOFF_PREGAME_GUARD", saved_guard),
            ("CV_ALLOW_PLAYOFF_PREGAME", saved_allow),
            ("CV_ALLOW_PLAYOFF_AST",     saved_ast),
        ]:
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


# ---------------------------------------------------------------------------
# 1. Flag OFF (default) — byte-identical: REB/PTS still pass in playoffs
# ---------------------------------------------------------------------------

class TestGuardOff:
    """When CV_PLAYOFF_PREGAME_GUARD is unset, non-AST playoff bets are allowed
    (current behavior is preserved exactly)."""

    def test_pts_playoff_allowed_when_guard_off(self):
        assert "CV_PLAYOFF_PREGAME_GUARD" not in os.environ
        assert bet_policy.policy_allows_context("pts", _PLAYOFF_GID) is True

    def test_reb_playoff_allowed_when_guard_off(self):
        assert bet_policy.policy_allows_context("reb", _PLAYOFF_GID) is True

    def test_fg3m_playoff_allowed_when_guard_off(self):
        assert bet_policy.policy_allows_context("fg3m", _PLAYOFF_GID) is True

    def test_stl_playoff_allowed_when_guard_off(self):
        assert bet_policy.policy_allows_context("stl", _PLAYOFF_GID) is True

    def test_blk_playoff_allowed_when_guard_off(self):
        assert bet_policy.policy_allows_context("blk", _PLAYOFF_GID) is True

    def test_tov_playoff_allowed_when_guard_off(self):
        assert bet_policy.policy_allows_context("tov", _PLAYOFF_GID) is True

    def test_guard_disabled_function_returns_false(self):
        assert bet_policy.playoff_pregame_guard_enabled() is False

    def test_explicit_zero_is_off(self):
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "0"
        assert bet_policy.playoff_pregame_guard_enabled() is False
        assert bet_policy.policy_allows_context("pts", _PLAYOFF_GID) is True

    def test_explicit_false_is_off(self):
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "false"
        assert bet_policy.playoff_pregame_guard_enabled() is False
        assert bet_policy.policy_allows_context("reb", _PLAYOFF_GID) is True


# ---------------------------------------------------------------------------
# 2. Flag ON — ALL pregame props blocked on prefix-004 games
# ---------------------------------------------------------------------------

class TestGuardOn:
    """When CV_PLAYOFF_PREGAME_GUARD=1, every stat is blocked on playoff game_ids."""

    @pytest.fixture(autouse=True)
    def _set_guard(self):
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        yield

    def test_guard_enabled_function_returns_true(self):
        assert bet_policy.playoff_pregame_guard_enabled() is True

    @pytest.mark.parametrize("stat", _STATS)
    def test_all_stats_blocked_on_playoff_game(self, stat):
        assert bet_policy.policy_allows_context(stat, _PLAYOFF_GID) is False, (
            f"{stat} should be blocked on playoff game when guard is ON"
        )

    def test_case_insensitive_stat(self):
        for stat in ("PTS", "Reb", "AST", "FG3M"):
            assert bet_policy.policy_allows_context(stat, _PLAYOFF_GID) is False

    def test_various_playoff_game_ids_blocked(self):
        playoff_ids = ["0042500401", "0042500402", "0042300123", "0042100999"]
        for gid in playoff_ids:
            assert bet_policy.policy_allows_context("pts", gid) is False, (
                f"pts should be blocked for playoff game_id {gid}"
            )

    # --- Escape hatch ---

    def test_escape_hatch_overrides_guard(self):
        """CV_ALLOW_PLAYOFF_PREGAME=1 lets a future validated edge through."""
        os.environ["CV_ALLOW_PLAYOFF_PREGAME"] = "1"
        for stat in _STATS:
            assert bet_policy.policy_allows_context(stat, _PLAYOFF_GID) is True, (
                f"{stat} should pass through with escape hatch enabled"
            )

    def test_escape_hatch_off_still_blocks(self):
        os.environ["CV_ALLOW_PLAYOFF_PREGAME"] = "0"
        assert bet_policy.policy_allows_context("pts", _PLAYOFF_GID) is False


# ---------------------------------------------------------------------------
# 3. Regular-season games unaffected by the guard in either state
# ---------------------------------------------------------------------------

class TestRegularSeasonUnaffected:
    """Guard never fires on non-playoff game_ids, regardless of flag state."""

    @pytest.mark.parametrize("stat", _STATS)
    def test_guard_off_regseason_allowed(self, stat):
        assert bet_policy.policy_allows_context(stat, _REGSEASON_GID) is True

    @pytest.mark.parametrize("stat", _STATS)
    def test_guard_on_regseason_still_allowed(self, stat):
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        assert bet_policy.policy_allows_context(stat, _REGSEASON_GID) is True, (
            f"{stat} on regular-season game must not be blocked"
        )

    def test_preseason_prefix_not_blocked(self):
        """Only prefix 004 = playoffs; preseason (001) and regular (002) are safe."""
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        for gid in ("0012400001", "0022400999", "0052400001"):
            assert bet_policy.policy_allows_context("pts", gid) is True, (
                f"game_id {gid} should not be blocked (not a playoff prefix)"
            )

    def test_none_game_id_is_allowed(self):
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        assert bet_policy.policy_allows_context("pts", None) is True

    def test_none_stat_is_allowed(self):
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        assert bet_policy.policy_allows_context(None, _PLAYOFF_GID) is True


# ---------------------------------------------------------------------------
# 4. AST guard still fires independently when broad guard is OFF
# ---------------------------------------------------------------------------

class TestAstGuardStillFires:
    """Guard 2 (AST-specific playoff guard) fires regardless of guard 1 state."""

    def test_ast_playoff_blocked_guard_off(self):
        """Even without the broad guard, AST playoff bets are blocked (back-compat)."""
        assert "CV_PLAYOFF_PREGAME_GUARD" not in os.environ
        assert bet_policy.policy_allows_context("ast", _PLAYOFF_GID) is False

    def test_ast_playoff_blocked_case_insensitive(self):
        assert bet_policy.policy_allows_context("AST", _PLAYOFF_GID) is False

    def test_ast_playoff_escape_hatch(self):
        """CV_ALLOW_PLAYOFF_AST=1 enables the old escape hatch on guard 2."""
        os.environ["CV_ALLOW_PLAYOFF_AST"] = "1"
        assert bet_policy.policy_allows_context("ast", _PLAYOFF_GID) is True

    def test_ast_regseason_allowed(self):
        assert bet_policy.policy_allows_context("ast", _REGSEASON_GID) is True

    def test_non_ast_still_allowed_guard_off(self):
        """Only AST is blocked by guard 2; other stats pass through."""
        for stat in ["pts", "reb", "fg3m", "stl", "blk", "tov"]:
            assert bet_policy.policy_allows_context(stat, _PLAYOFF_GID) is True, (
                f"{stat} should not be blocked by AST-specific guard 2"
            )

    def test_broad_guard_on_subsumes_ast_guard(self):
        """When guard 1 is ON, AST is blocked by guard 1 before guard 2 is reached."""
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        # AST is blocked (guard 1 fires first; escape hatch for guard 2 is irrelevant)
        assert bet_policy.policy_allows_context("ast", _PLAYOFF_GID) is False

    def test_allow_playoff_ast_does_not_bypass_broad_guard(self):
        """CV_ALLOW_PLAYOFF_AST=1 only bypasses guard 2; guard 1 still blocks."""
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        os.environ["CV_ALLOW_PLAYOFF_AST"] = "1"
        # Guard 1 fires (CV_ALLOW_PLAYOFF_PREGAME not set) -> still blocked
        assert bet_policy.policy_allows_context("ast", _PLAYOFF_GID) is False

    def test_allow_playoff_pregame_bypasses_all_guards_including_ast(self):
        """CV_ALLOW_PLAYOFF_PREGAME=1 bypasses guard 1 entirely (early return True).

        When guard 1 returns True via its escape hatch, the function returns
        immediately -- guard 2 (AST-specific) is not reached.  The caller
        explicitly opted into playoff pregame bets for ALL stats.
        """
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        os.environ["CV_ALLOW_PLAYOFF_PREGAME"] = "1"
        # Guard 1 escape hatch causes an immediate True return; AST passes through.
        assert bet_policy.policy_allows_context("ast", _PLAYOFF_GID) is True

    def test_both_escape_hatches_unblock_ast(self):
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        os.environ["CV_ALLOW_PLAYOFF_PREGAME"] = "1"
        os.environ["CV_ALLOW_PLAYOFF_AST"] = "1"
        assert bet_policy.policy_allows_context("ast", _PLAYOFF_GID) is True


# ---------------------------------------------------------------------------
# 5. bet_selector integration — guard ON skips all stats on playoff game
# ---------------------------------------------------------------------------

class TestSelectorIntegrationPlayoffGuard:
    """Confirm bet_selector skips all stats on a playoff game when guard ON."""

    _SAMPLE_EDGES = [
        {"player": "LeBron James", "stat": "pts", "projection": 29.5,
         "book_line": 27.5, "edge": 2.0, "kelly": 0.02,
         "confidence": "high", "team": "NYK", "opp_team": "SAS",
         "game_id": _PLAYOFF_GID},
        {"player": "Karl-Anthony Towns", "stat": "reb", "projection": 11.5,
         "book_line": 9.5, "edge": 2.0, "kelly": 0.02,
         "confidence": "high", "team": "NYK", "opp_team": "SAS",
         "game_id": _PLAYOFF_GID},
        {"player": "Jalen Brunson", "stat": "ast", "projection": 6.5,
         "book_line": 5.5, "edge": 1.0, "kelly": 0.02,
         "confidence": "high", "team": "NYK", "opp_team": "SAS",
         "game_id": _PLAYOFF_GID},
        {"player": "OG Anunoby", "stat": "fg3m", "projection": 3.5,
         "book_line": 2.5, "edge": 1.0, "kelly": 0.02,
         "confidence": "high", "team": "NYK", "opp_team": "SAS",
         "game_id": _PLAYOFF_GID},
    ]

    _REGSEASON_EDGES = [
        {"player": "LeBron James", "stat": "pts", "projection": 29.5,
         "book_line": 27.5, "edge": 2.0, "kelly": 0.02,
         "confidence": "high", "team": "LAL", "opp_team": "BOS",
         "game_id": _REGSEASON_GID},
    ]

    def _make_cfg(self, tmp_path):
        cfg = tmp_path / "betting.yaml"
        cfg.write_text(
            "bankroll: 1000.0\nkelly_fraction: 0.25\nmax_bet_pct: 0.04\n"
            "edge_min: 0.04\nmax_bets_per_game: 10\nmax_combined_pct: 0.30\n"
            "default_odds: -110\ndry_run: false\n"
        )
        return str(cfg)

    def _run(self, rows, tmp_path):
        out_dir = str(tmp_path / "output")
        os.makedirs(out_dir, exist_ok=True)
        with patch("src.prediction.bet_selector._CONFIG_PATH", self._make_cfg(tmp_path)), \
             patch("src.prediction.bet_selector._OUTPUT_DIR", out_dir), \
             patch("src.prediction.bet_selector._BET_LOG_PATH",
                   str(tmp_path / "bet_log.json")):
            from src.prediction.bet_selector import select
            return select(rows, "2026-06-04", dry_run=False)

    def test_guard_off_reb_pts_fg3m_pass_in_playoffs(self, tmp_path):
        """Default (guard off): REB/PTS/FG3M still selectable in playoffs (byte-identical)."""
        bets = self._run(self._SAMPLE_EDGES, tmp_path)
        stats = {b["stat"] for b in bets}
        assert "pts"  in stats, "guard OFF: PTS must still be selectable in playoffs"
        assert "reb"  in stats, "guard OFF: REB must still be selectable in playoffs"
        assert "fg3m" in stats, "guard OFF: FG3M must still be selectable in playoffs"

    def test_guard_off_ast_still_blocked_in_playoffs(self, tmp_path):
        """AST guard (guard 2) still fires even when broad guard is off."""
        bets = self._run(self._SAMPLE_EDGES, tmp_path)
        stats = {b["stat"] for b in bets}
        assert "ast" not in stats, "guard OFF: AST must still be blocked in playoffs (guard 2)"

    def test_guard_on_blocks_all_stats_on_playoff_game(self, tmp_path):
        """Guard ON: no pregame prop bets placed on any playoff game_id."""
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        bets = self._run(self._SAMPLE_EDGES, tmp_path)
        assert len(bets) == 0, (
            f"guard ON: no bets should be placed on playoff game; got {bets}"
        )

    def test_guard_on_does_not_affect_regular_season(self, tmp_path):
        """Guard ON: regular-season bets are unaffected."""
        os.environ["CV_PLAYOFF_PREGAME_GUARD"] = "1"
        bets = self._run(self._REGSEASON_EDGES, tmp_path)
        stats = {b["stat"] for b in bets}
        assert "pts" in stats, (
            "guard ON: regular-season PTS bets must still be placed"
        )


class TestStrippedGameIdRobustness:
    """WAVE 17d: the legacy slate builder does int(gid), stripping the leading
    '00' so a served playoff bet carries '42500401' not '0042500401'. The guard
    (and the always-on AST guard) must still classify it as playoff. Regression
    for the bug where _is_playoff_game_id('42500401') was False -> guard inert."""

    def test_stripped_playoff_id_is_playoff(self):
        from src.prediction.bet_policy import _is_playoff_game_id
        assert _is_playoff_game_id("0042500401") is True
        assert _is_playoff_game_id("42500401") is True, "stripped playoff id must classify as playoff"

    def test_stripped_regular_id_not_playoff(self):
        from src.prediction.bet_policy import _is_playoff_game_id
        assert _is_playoff_game_id("0022500401") is False
        assert _is_playoff_game_id("22500401") is False, "stripped regular id stays non-playoff"

    def test_book_and_nonnumeric_ids_not_playoff(self):
        from src.prediction.bet_policy import _is_playoff_game_id
        assert _is_playoff_game_id("35669206") is False, "synth book id must not false-positive"
        assert _is_playoff_game_id("KAMBI_x") is False
        assert _is_playoff_game_id(None) is False

    def test_guard_blocks_stripped_playoff_id(self, monkeypatch):
        from src.prediction.bet_policy import policy_allows_context
        monkeypatch.setenv("CV_PLAYOFF_PREGAME_GUARD", "1")
        monkeypatch.delenv("CV_ALLOW_PLAYOFF_PREGAME", raising=False)
        assert policy_allows_context("pts", "42500401") is False, "stripped playoff PTS must be blocked"
        assert policy_allows_context("pts", "22500401") is True, "stripped regular PTS allowed"

    def test_alwayson_ast_guard_blocks_stripped_playoff(self, monkeypatch):
        from src.prediction.bet_policy import policy_allows_context
        monkeypatch.delenv("CV_PLAYOFF_PREGAME_GUARD", raising=False)
        monkeypatch.delenv("CV_ALLOW_PLAYOFF_AST", raising=False)
        assert policy_allows_context("ast", "42500401") is False, "stripped playoff AST blocked by always-on guard"
        assert policy_allows_context("ast", "22500401") is True, "reg-season AST allowed"


# ---------------------------------------------------------------------------
# 6. CV_PLAYOFF_GUARD_FAILCLOSED — the synth-path hole (SYNTH_PATH_PLAYOFF_GUARD.md)
# ---------------------------------------------------------------------------

_BOOK_ID = "35669206"        # raw book event id -> zfill 0035669206 -> '003' (unclassifiable)
_BOOK_ID2 = "1027847552"     # another book id on the 06-05 Finals slate


class TestFailClosedOffByteIdentical:
    """Flag OFF (default): a book id / None in a playoff window is SERVED exactly
    as it is today — the new playoff_window kwarg + flag are a strict no-op."""

    @pytest.fixture(autouse=True)
    def _clean(self, monkeypatch):
        monkeypatch.delenv("CV_PLAYOFF_GUARD_FAILCLOSED", raising=False)
        monkeypatch.delenv("CV_PLAYOFF_PREGAME_GUARD", raising=False)
        monkeypatch.delenv("CV_ALLOW_PLAYOFF_PREGAME", raising=False)

    def test_failclosed_disabled_function_returns_false(self):
        assert bet_policy.playoff_guard_failclosed_enabled() is False

    def test_book_id_playoff_window_served_when_off(self):
        # No playoff_window arg -> default False -> byte-identical
        assert bet_policy.policy_allows_context("pts", _BOOK_ID) is True
        # Even WITH playoff_window=True, flag OFF must still serve (no-op)
        assert bet_policy.policy_allows_context("pts", _BOOK_ID, playoff_window=True) is True

    def test_ast_book_id_playoff_window_served_when_off(self):
        # The always-on AST guard keys on the 004 prefix; a book id evades it
        # today — flag OFF preserves that exact (evading) behavior.
        assert bet_policy.policy_allows_context("ast", _BOOK_ID, playoff_window=True) is True

    def test_none_game_id_served_when_off(self):
        assert bet_policy.policy_allows_context("pts", None, playoff_window=True) is True

    def test_kwarg_is_keyword_only_and_optional(self):
        # Old positional callers (stat, game_id) keep working unchanged.
        assert bet_policy.policy_allows_context("pts", _BOOK_ID) is True


class TestFailClosedOnPlayoffWindow:
    """Flag ON + a detected playoff window: an UNCLASSIFIABLE id (book id, KAMBI
    hash, None) is treated as playoff and BLOCKED — every stat, independent of
    CV_PLAYOFF_PREGAME_GUARD."""

    @pytest.fixture(autouse=True)
    def _set(self, monkeypatch):
        monkeypatch.setenv("CV_PLAYOFF_GUARD_FAILCLOSED", "1")
        monkeypatch.delenv("CV_PLAYOFF_PREGAME_GUARD", raising=False)
        monkeypatch.delenv("CV_ALLOW_PLAYOFF_PREGAME", raising=False)

    def test_failclosed_enabled_function_returns_true(self):
        assert bet_policy.playoff_guard_failclosed_enabled() is True

    @pytest.mark.parametrize("stat", _STATS)
    def test_book_id_blocked_in_playoff_window(self, stat):
        assert bet_policy.policy_allows_context(
            stat, _BOOK_ID, playoff_window=True) is False, (
            f"{stat} on an unclassifiable book id must fail closed in a playoff window")

    @pytest.mark.parametrize("gid", [_BOOK_ID, _BOOK_ID2, "KAMBI_x", None, "", "0035669206"])
    def test_various_unclassifiable_ids_blocked(self, gid):
        assert bet_policy.policy_allows_context("pts", gid, playoff_window=True) is False

    def test_blocks_without_broad_guard_flag(self):
        # CV_PLAYOFF_PREGAME_GUARD is NOT set here; fail-closed blocks anyway.
        assert "CV_PLAYOFF_PREGAME_GUARD" not in os.environ
        assert bet_policy.policy_allows_context("pts", _BOOK_ID, playoff_window=True) is False

    def test_escape_hatch_unblocks_failclosed(self):
        os.environ["CV_ALLOW_PLAYOFF_PREGAME"] = "1"
        try:
            for stat in _STATS:
                assert bet_policy.policy_allows_context(
                    stat, _BOOK_ID, playoff_window=True) is True
        finally:
            os.environ.pop("CV_ALLOW_PLAYOFF_PREGAME", None)


class TestFailClosedRegSeasonSafety:
    """Flag ON but NOT a playoff window: unclassifiable ids must still be SERVED
    (a regular-season slate's book ids must NOT be blocked)."""

    @pytest.fixture(autouse=True)
    def _set(self, monkeypatch):
        monkeypatch.setenv("CV_PLAYOFF_GUARD_FAILCLOSED", "1")
        monkeypatch.delenv("CV_PLAYOFF_PREGAME_GUARD", raising=False)

    @pytest.mark.parametrize("gid", [_BOOK_ID, _BOOK_ID2, "KAMBI_x", None])
    def test_unclassifiable_served_when_not_playoff_window(self, gid):
        assert bet_policy.policy_allows_context("pts", gid, playoff_window=False) is True
        # default (no kwarg) is also reg-season-safe
        assert bet_policy.policy_allows_context("pts", gid) is True

    def test_known_regseason_id_never_blocked_even_in_playoff_window(self):
        # A real 002 NBA id (and its int-stripped form) is recognized and served
        # even with the flag on and a playoff window — fail-closed only catches
        # UNCLASSIFIABLE ids, never a known reg-season game.
        assert bet_policy._is_regular_season_game_id("0022500401") is True
        assert bet_policy._is_regular_season_game_id("22500401") is True
        assert bet_policy._is_regular_season_game_id(_BOOK_ID) is False
        assert bet_policy.policy_allows_context("pts", "0022500401", playoff_window=True) is True
        assert bet_policy.policy_allows_context("pts", "22500401", playoff_window=True) is True


class TestFailClosedDoesNotChangeNbaIdPaths:
    """A normal NBA playoff id is still handled by the EXISTING guards; a normal
    NBA reg-season id is still served — fail-closed never alters these paths."""

    def test_nba_playoff_id_still_blocked_by_existing_guard(self, monkeypatch):
        monkeypatch.setenv("CV_PLAYOFF_GUARD_FAILCLOSED", "1")
        monkeypatch.setenv("CV_PLAYOFF_PREGAME_GUARD", "1")
        monkeypatch.delenv("CV_ALLOW_PLAYOFF_PREGAME", raising=False)
        assert bet_policy.policy_allows_context("pts", _PLAYOFF_GID, playoff_window=True) is False
        assert bet_policy.policy_allows_context("pts", "42500401", playoff_window=True) is False

    def test_nba_regseason_id_still_served(self, monkeypatch):
        monkeypatch.setenv("CV_PLAYOFF_GUARD_FAILCLOSED", "1")
        monkeypatch.setenv("CV_PLAYOFF_PREGAME_GUARD", "1")
        # known 002 reg-season id, even with playoff_window True (mismatched
        # context) is recognized as reg-season and served.
        assert bet_policy.policy_allows_context("pts", _REGSEASON_GID, playoff_window=True) is True
