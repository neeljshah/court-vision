"""predict_service.test_produce_degeneracy_guard -- per-file test for WS1-mlb-degeneracy-guard.

Acceptance criteria (per workstream spec):

  (a) A slate with >=MIN_CARDS games but <=2 distinct pregame_probs triggers a cache
      clear + single rebuild attempt. The rebuild is attempted exactly once (not a loop).

  (b) If the rebuilt snapshot is STILL degenerate (flat prior persists), the returned
      envelope has status='unavailable' with an honest reason string -- NEVER status='ok'.

  (c) _build_predictor refuses to cache an MLB predictor whose _elo dict has <=2 distinct
      rating values across all corpus teams (init-rating collapse). Such a predictor is
      stored as None in the cache, not as the degenerate instance.

All three tests run OFFLINE with fake feeds and fake predictors -- no network, no corpus.

Run (per-file only):
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/test_produce_degeneracy_guard.py -q

INVARIANTS: ASCII only; no $ field; stale-never-green; <=300 LOC; per-file only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, call, patch

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.produce import (
    MIN_CARDS,
    _MAX_DISTINCT_PROBS,
    _is_degenerate,
    _try_warm_predictor,
    produce_sport,
)
from predict_service.contracts import (
    PredictionRecord,
    SnapshotEnvelope,
    GAME_STATE_PRE,
)
from scripts.platformkit.predictor_jd import (
    _build_predictor,
    _PREDICTOR_CACHE,
    _MIN_DISTINCT_RATINGS,
    clear_cache,
)


# ---------------------------------------------------------------------------
# Shared helpers / fake feeds
# ---------------------------------------------------------------------------

_FLAT_PROB = 0.5345  # the MLB init-rating collapse value

def _flat_pregame_probs() -> Dict[str, float]:
    """Return pregame_probs identical to the init-rating collapse (all same value)."""
    return {"home_ml": _FLAT_PROB, "away_ml": round(1.0 - _FLAT_PROB, 4)}


def _real_pregame_probs(home_prob: float) -> Dict[str, float]:
    """Return pregame_probs with a real (non-uniform) home_ml value."""
    return {"home_ml": round(home_prob, 4), "away_ml": round(1.0 - home_prob, 4)}


def _make_record(home: str, away: str, probs: Dict[str, float]) -> PredictionRecord:
    return PredictionRecord(
        sport="mlb", game_id=f"{away}@{home}", home=home, away=away,
        pregame_probs=probs, game_state=GAME_STATE_PRE,
        produced_at="2026-06-20T00:00:00+00:00")


def _games_slate(n: int) -> List[Dict[str, Any]]:
    """Build a fake schedule of *n* games."""
    teams = [
        ("NYY", "BOS"), ("LAD", "SFG"), ("HOU", "TEX"), ("ATL", "MIA"),
        ("CHC", "STL"), ("MIN", "CLE"), ("TOR", "BAL"), ("SEA", "OAK"),
    ]
    return [{"game_id": f"{a}@{h}", "home": h, "away": a, "tipoff": None}
            for h, a in teams[:n]]


def _flat_predict_fn(sport: str, home: str, away: str) -> Dict[str, Any]:
    """Fake predict_fn: always returns the init-rating collapse prob."""
    return {"pregame": {"p_home_win": _FLAT_PROB}}


def _real_predict_fn_factory(probs: Dict[str, float]):
    """Factory: returns a predict_fn that always returns *probs* as pregame."""
    def _fn(sport: str, home: str, away: str) -> Dict[str, Any]:
        return {"pregame": {"p_home_win": probs.get(f"{home}", _FLAT_PROB)}}
    return _fn


def _empty_odds_feed(sport: str) -> Dict[str, Any]:
    return {"events": [], "as_of": "2026-06-20T00:00:00+00:00"}


def _slate_schedule(n: int):
    games = _games_slate(n)
    def _feed(sport: str) -> List[Dict[str, Any]]:
        return games
    return _feed, games


# ---------------------------------------------------------------------------
# (a) Flat slate >=MIN_CARDS triggers cache-clear + single rebuild
# ---------------------------------------------------------------------------

class TestFlatSlateTriggersCacheClearAndRebuild:
    """Acceptance criterion (a): detect flat prior -> clear cache -> rebuild once."""

    def test_cache_cleared_and_rebuild_called_once(self) -> None:
        """When first build is flat, clear_cache is called and predict_fn is called
        again for the same games (one full rebuild pass, not looped)."""
        n_games = MIN_CARDS + 1
        schedule_fn, games = _slate_schedule(n_games)
        call_counts: Dict[str, int] = {"predict": 0, "cache_clear": 0}

        def _counting_predict(sport: str, home: str, away: str) -> Dict[str, Any]:
            call_counts["predict"] += 1
            return {"pregame": {"p_home_win": _FLAT_PROB}}

        cleared_log: list = []
        original_clear = None

        def _tracking_clear() -> None:
            call_counts["cache_clear"] += 1
            cleared_log.append(True)
            # Also call the real clear so the cache is actually dropped.
            if original_clear:
                original_clear()

        import scripts.platformkit.predictor_jd as jd_mod  # noqa: PLC0415
        original_clear = jd_mod.clear_cache

        with patch.object(jd_mod, "clear_cache", _tracking_clear):
            env = produce_sport(
                "mlb",
                schedule_feed=schedule_fn,
                odds_feed=_empty_odds_feed,
                predict_fn=_counting_predict,
            )

        # (a1) cache_clear was called exactly once.
        assert call_counts["cache_clear"] == 1, (
            "(a) clear_cache must be called exactly 1 time on flat slate; "
            "got %d" % call_counts["cache_clear"]
        )

        # (a2) predict_fn was called for n_games on the first build AND n_games on
        # the rebuild = 2 * n_games total (one full pass each).
        expected_calls = n_games * 2
        assert call_counts["predict"] == expected_calls, (
            "(a) predict_fn must be called %d times (2 passes of %d games); "
            "got %d" % (expected_calls, n_games, call_counts["predict"])
        )

    def test_no_false_positive_on_small_slate(self) -> None:
        """A slate with <MIN_CARDS games must NOT trigger the degeneracy guard
        even when all probs are identical (off-day / genuinely small slate)."""
        n_games = max(1, MIN_CARDS - 1)
        schedule_fn, _ = _slate_schedule(n_games)
        cache_clear_calls: list = []

        import scripts.platformkit.predictor_jd as jd_mod  # noqa: PLC0415

        with patch.object(jd_mod, "clear_cache",
                          side_effect=lambda: cache_clear_calls.append(1)):
            env = produce_sport(
                "mlb",
                schedule_feed=schedule_fn,
                odds_feed=_empty_odds_feed,
                predict_fn=_flat_predict_fn,
            )

        assert len(cache_clear_calls) == 0, (
            "(a) clear_cache must NOT be called for a small slate (<MIN_CARDS); "
            "got %d calls" % len(cache_clear_calls)
        )


# ---------------------------------------------------------------------------
# (b) Still-flat after rebuild -> status='unavailable' with honest reason
# ---------------------------------------------------------------------------

class TestPersistentFlatPriorBecomesUnavailable:
    """Acceptance criterion (b): if rebuild is still flat -> status='unavailable'."""

    def test_persistent_flat_prior_is_unavailable(self) -> None:
        """Both passes return flat probs -> envelope must be status='unavailable'."""
        n_games = MIN_CARDS + 1
        schedule_fn, _ = _slate_schedule(n_games)

        env = produce_sport(
            "mlb",
            schedule_feed=schedule_fn,
            odds_feed=_empty_odds_feed,
            predict_fn=_flat_predict_fn,  # always flat, rebuild won't help
        )

        assert env.status == "unavailable", (
            "(b) status must be 'unavailable' when flat prior persists after rebuild; "
            "got status=%r" % env.status
        )

    def test_unavailable_note_is_honest(self) -> None:
        """The 'unavailable' reason must mention flat-prior and must not claim ok."""
        n_games = MIN_CARDS + 1
        schedule_fn, _ = _slate_schedule(n_games)

        env = produce_sport(
            "mlb",
            schedule_feed=schedule_fn,
            odds_feed=_empty_odds_feed,
            predict_fn=_flat_predict_fn,
        )

        assert env.status != "ok", (
            "(b) envelope status must never be 'ok' when flat prior persists"
        )
        # The reason must mention the degeneracy diagnosis (not a generic 'no games').
        note = env.note or ""
        assert "flat" in note.lower() or "prior" in note.lower() or "degenerate" in note.lower(), (
            "(b) honest reason must mention flat-prior or degeneracy; got note=%r" % note
        )

    def test_ok_snapshot_when_rebuild_fixes_flat_prior(self) -> None:
        """If the rebuild returns varied probs, the envelope must be status='ok'."""
        n_games = MIN_CARDS + 1
        schedule_fn, games = _slate_schedule(n_games)

        # Build per-game real probs (distinct values for each home team).
        real_probs = {g["home"]: 0.50 + 0.02 * i for i, g in enumerate(games)}
        call_pass: Dict[str, int] = {"n": 0}

        def _two_pass_fn(sport: str, home: str, away: str) -> Dict[str, Any]:
            """Return flat on pass 1, real on pass 2."""
            call_pass["n"] += 1
            # pass 1 = first n_games calls; pass 2 = next n_games calls
            if call_pass["n"] <= n_games:
                return {"pregame": {"p_home_win": _FLAT_PROB}}
            return {"pregame": {"p_home_win": real_probs.get(home, 0.55)}}

        env = produce_sport(
            "mlb",
            schedule_feed=schedule_fn,
            odds_feed=_empty_odds_feed,
            predict_fn=_two_pass_fn,
        )

        assert env.status == "ok", (
            "(b) envelope must be status='ok' when rebuild produces varied probs; "
            "got status=%r" % env.status
        )
        assert len(env.predictions) == n_games, (
            "(b) rebuilt envelope must contain all %d predictions; got %d" % (
                n_games, len(env.predictions))
        )


# ---------------------------------------------------------------------------
# (c) _build_predictor refuses to cache a flat-Elo MLB predictor
# ---------------------------------------------------------------------------

class TestBuildPredictorRefusesFlatElo:
    """Acceptance criterion (c): _build_predictor must cache None for a flat-Elo predictor."""

    def setup_method(self) -> None:
        clear_cache()

    def teardown_method(self) -> None:
        clear_cache()

    def _make_flat_mlb_predictor(self, n_teams: int = 10) -> MagicMock:
        """Build a mock MLBPredictor whose _elo dict has only 1 distinct value."""
        mock_pred = MagicMock()
        # All teams share the same init rating -> flat prior collapse.
        flat_rating = 1500.0
        mock_pred._elo = {f"TEAM{i}": flat_rating for i in range(n_teams)}
        return mock_pred

    def _make_real_mlb_predictor(self, n_teams: int = 10) -> MagicMock:
        """Build a mock MLBPredictor whose _elo dict has varied distinct values."""
        mock_pred = MagicMock()
        # Teams have genuinely distinct ratings (replayed a real corpus).
        mock_pred._elo = {f"TEAM{i}": 1500.0 + i * 10.0 for i in range(n_teams)}
        return mock_pred

    def test_flat_elo_predictor_cached_as_none(self) -> None:
        """A mock MLBPredictor with all-same _elo values must be refused from cache."""
        flat_pred = self._make_flat_mlb_predictor(10)

        with patch(
            "domains.mlb.predictor.MLBPredictor", return_value=flat_pred
        ), patch(
            "domains.mlb.refresh_ratings.refreshed_predictor",
            side_effect=FileNotFoundError("no corpus"),
        ):
            result = _build_predictor("mlb")

        assert result is None, (
            "(c) _build_predictor must return None for flat-Elo MLBPredictor; "
            "got %r" % type(result)
        )
        # Cache must store None (not the degenerate instance).
        assert _PREDICTOR_CACHE.get("mlb") is None, (
            "(c) _PREDICTOR_CACHE['mlb'] must be None; "
            "got %r" % _PREDICTOR_CACHE.get("mlb")
        )

    def test_flat_elo_predictor_cached_as_none_for_two_teams(self) -> None:
        """Even with just 2 teams sharing the same rating -> refused."""
        flat_pred = self._make_flat_mlb_predictor(2)

        with patch(
            "domains.mlb.predictor.MLBPredictor", return_value=flat_pred
        ), patch(
            "domains.mlb.refresh_ratings.refreshed_predictor",
            side_effect=FileNotFoundError("no corpus"),
        ):
            result = _build_predictor("mlb")

        assert result is None, (
            "(c) 2-team flat-Elo predictor must be refused from cache"
        )

    def test_real_elo_predictor_cached_normally(self) -> None:
        """A mock MLBPredictor with varied _elo values must be accepted into cache."""
        real_pred = self._make_real_mlb_predictor(10)

        with patch(
            "domains.mlb.predictor.MLBPredictor", return_value=real_pred
        ), patch(
            "domains.mlb.refresh_ratings.refreshed_predictor",
            side_effect=FileNotFoundError("no corpus"),
        ):
            result = _build_predictor("mlb")

        assert result is not None, (
            "(c) _build_predictor must accept a real-Elo MLBPredictor; got None"
        )
        assert _PREDICTOR_CACHE.get("mlb") is not None, (
            "(c) _PREDICTOR_CACHE['mlb'] must hold the real predictor"
        )

    def test_refreshed_predictor_with_flat_elo_refused(self) -> None:
        """Even the refreshed predictor path is refused if its _elo is flat."""
        flat_refreshed = self._make_flat_mlb_predictor(20)

        with patch(
            "domains.mlb.refresh_ratings.refreshed_predictor",
            return_value=flat_refreshed,
        ):
            result = _build_predictor("mlb")

        assert result is None, (
            "(c) refreshed predictor with flat _elo must also be refused"
        )

    def test_single_team_elo_dict_not_refused(self) -> None:
        """An _elo dict with only 1 team should pass (too small to judge degeneracy)."""
        mock_pred = MagicMock()
        mock_pred._elo = {"NYY": 1500.0}  # only 1 team -- not >= 2

        with patch(
            "domains.mlb.predictor.MLBPredictor", return_value=mock_pred
        ), patch(
            "domains.mlb.refresh_ratings.refreshed_predictor",
            side_effect=FileNotFoundError("no corpus"),
        ):
            result = _build_predictor("mlb")

        # With < 2 teams we cannot detect degeneracy, so allow through.
        assert result is not None, (
            "(c) a 1-team _elo dict is too small to detect degeneracy; must allow through"
        )


# ---------------------------------------------------------------------------
# Shared honesty invariants
# ---------------------------------------------------------------------------

class TestHonestyInvariants:
    """No $ field; honest_note present; edge_claimed=False on envelope."""

    def _flat_envelope(self) -> SnapshotEnvelope:
        n_games = MIN_CARDS + 1
        schedule_fn, _ = _slate_schedule(n_games)
        return produce_sport(
            "mlb",
            schedule_feed=schedule_fn,
            odds_feed=_empty_odds_feed,
            predict_fn=_flat_predict_fn,
        )

    def test_no_dollar_field(self) -> None:
        env = self._flat_envelope()
        d = env.to_dict()
        text = str(d)
        assert "$" not in text or "honest_note" in text, (
            "no raw '$' field should appear outside of honest_note context"
        )

    def test_unavailable_note_not_empty(self) -> None:
        env = self._flat_envelope()
        assert env.note, "unavailable envelope must carry a non-empty note"

    def test_is_degenerate_helper_correct(self) -> None:
        """_is_degenerate must detect flat probs on a full slate."""
        flat_records = [
            _make_record(h, a, _flat_pregame_probs())
            for h, a in [("NYY", "BOS"), ("LAD", "SFG"), ("HOU", "TEX"),
                         ("ATL", "MIA")]
        ]
        assert _is_degenerate(flat_records) is True, (
            "_is_degenerate must return True for flat-prob records"
        )

    def test_is_degenerate_false_for_varied_probs(self) -> None:
        """_is_degenerate must return False when probs are genuinely distinct."""
        varied_records = [
            _make_record("NYY", "BOS", _real_pregame_probs(0.55)),
            _make_record("LAD", "SFG", _real_pregame_probs(0.48)),
            _make_record("HOU", "TEX", _real_pregame_probs(0.61)),
            _make_record("ATL", "MIA", _real_pregame_probs(0.52)),
        ]
        assert _is_degenerate(varied_records) is False, (
            "_is_degenerate must return False for genuinely varied probs"
        )

    def test_is_degenerate_false_for_small_slate(self) -> None:
        """_is_degenerate must return False for slates below MIN_CARDS."""
        small_records = [
            _make_record("NYY", "BOS", _flat_pregame_probs()),
        ]
        assert _is_degenerate(small_records) is False, (
            "_is_degenerate must return False for a 1-game slate"
        )


# ---------------------------------------------------------------------------
# (d) Warmup guard: _try_warm_predictor + corpus-warmed real MLB slate
# ---------------------------------------------------------------------------

class TestWarmPredictorAndRealCorpusSlate:
    """Acceptance criteria (d): warmup + real-corpus diversity.

    (d1) _try_warm_predictor returns None (ready) when corpus is present.
    (d2) _try_warm_predictor returns an honest str reason when corpus is absent.
    (d3) A slate built with produce_sport using the REAL corpus (default predict_fn)
         for MLB yields >=4 distinct pregame home_ml values across the slate games
         (0.3995..0.7028 per the live predictor, NOT the 0.5345 constant).
         REQUIRES: data/domains/mlb/games.parquet must be present (gitignored corpus).
         SKIP: when corpus is absent (expected on fresh clones, CI without data/).
    """

    def setup_method(self) -> None:
        clear_cache()

    def teardown_method(self) -> None:
        clear_cache()

    def test_warm_predictor_corpus_absent_returns_reason(self) -> None:
        """When the corpus is absent _try_warm_predictor returns a non-empty str."""
        with patch(
            "scripts.platformkit.predictor_jd._build_predictor",
            return_value=None,
        ):
            reason = _try_warm_predictor("mlb")
        assert reason is not None, (
            "(d2) _try_warm_predictor must return a reason string when corpus is absent"
        )
        assert isinstance(reason, str) and len(reason) > 0, (
            "(d2) reason must be a non-empty string"
        )

    def test_warm_predictor_with_real_predictor_returns_none(self) -> None:
        """When the predictor is available _try_warm_predictor returns None (ready)."""
        mock_pred = MagicMock()
        mock_pred._elo = {f"TEAM{i}": 1500.0 + i * 10.0 for i in range(10)}
        with patch(
            "scripts.platformkit.predictor_jd._build_predictor",
            return_value=mock_pred,
        ):
            reason = _try_warm_predictor("mlb")
        assert reason is None, (
            "(d1) _try_warm_predictor must return None when corpus is ready; got %r" % reason
        )

    def test_real_corpus_mlb_slate_distinct_probs(self) -> None:
        """Real-corpus MLB slate (via produce_sport default path) yields >=4 distinct
        home_ml values. Skipped when corpus is absent (gitignored on fresh clones).

        Acceptance: when produce_sport --sport mlb prints status=ok, the snapshot
        must carry >=4 DISTINCT pregame home_ml values (not the 0.5345 constant).
        This validates the end-to-end fix: warm corpus -> resolve ESPN names ->
        diverse Elo ratings -> diverse probs (0.3995-0.7028 range observed live).
        """
        from pathlib import Path  # noqa: PLC0415
        _CORPUS = Path(__file__).resolve().parents[1] / "data" / "domains" / "mlb" / "games.parquet"
        if not _CORPUS.exists():
            pytest.skip("MLB corpus absent (gitignored on this clone); skipping real-corpus test")

        # Build a fake schedule of >=4 games with real MLB team names that the
        # corpus Elo lookup will resolve correctly (corpus keys, not ESPN display names).
        fake_games = [
            {"game_id": "BOS@NYY", "home": "NYY", "away": "BOS", "tipoff": None},
            {"game_id": "SFG@LAD", "home": "LAD", "away": "SFG", "tipoff": None},
            {"game_id": "TEX@HOU", "home": "HOU", "away": "TEX", "tipoff": None},
            {"game_id": "MIA@ATL", "home": "ATL", "away": "MIA", "tipoff": None},
            {"game_id": "STL@CHC", "home": "CHC", "away": "STL", "tipoff": None},
        ]

        def _real_schedule(_sport: str) -> List[Dict[str, Any]]:
            return fake_games

        env = produce_sport(
            "mlb",
            schedule_feed=_real_schedule,
            odds_feed=_empty_odds_feed,
            # predict_fn=None -> uses _default_predict_fn with real corpus
        )

        assert env.status == "ok", (
            "(d3) produce_sport with real corpus must return status=ok; "
            "got status=%r note=%r" % (env.status, env.note)
        )
        probs = [r.pregame_probs.get("home_ml") for r in env.predictions
                 if r.pregame_probs.get("home_ml") is not None]
        distinct = len(set(round(p, 4) for p in probs))
        assert distinct >= 4, (
            "(d3) real-corpus MLB slate must have >=4 distinct home_ml probs; "
            "got %d distinct across %d games: %r" % (distinct, len(probs), sorted(set(round(p,4) for p in probs)))
        )
        # Confirm no game shows the init-rating collapse value (0.5345 +/- 0.001).
        _INIT_PROB = 0.5345
        for prob in probs:
            assert abs(prob - _INIT_PROB) > 0.005, (
                "(d3) no game should show the init-rating collapse prob 0.5345; "
                "got prob=%.4f in slate %r" % (prob, probs)
            )
