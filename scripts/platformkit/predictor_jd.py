"""scripts.platformkit.predictor_jd -- demo JointDistribution per sport from the validated predictors.

The central cohesion seam: each sport ships a validated domains/<sport>/predictor.py with a
to_jd() that emits a coherent JointDistribution (ML/spread/total all read off ONE sample
matrix). This thin module instantiates the sport's Predictor for ONE representative demo
matchup and returns that JD, so the cohesive read's assemble_read can run on the SAME
distribution our best predictor produces (instead of carrying surface=None).

GUARDED: every call is wrapped try/except -> None; building a Predictor reads gitignored
parquet corpora, so a fresh clone (no data/) degrades gracefully to None (no fabricated
numbers). Predictors are lazily built and cached per sport so repeated reads do
not replay the corpus.

DEGENERACY GUARD (P0 MLB flat-prior fix): _validate_predictor_for_slate() checks that a
freshly-built predictor has >2 distinct Elo ratings across the slate's teams. A warm-up
race (corpus absent -> init-rating collapse -> all teams rated identically) is detected and
REFUSED from the cache so a constant-prior snapshot can never persist as status='ok'.

No edge is implied: the JD is the predictor's calibrated structure; markets are efficient.

Public API:
    get_demo_jd(sport) -> JointDistribution | None
    demo_matchup(sport) -> dict (the representative matchup label, for provenance)
    validate_predictor_for_slate(sport, teams) -> bool
INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC; no secrets.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

# Representative demo matchups per sport (two strong sides / top players present in the corpus).
# Each value is the positional args to the predictor's to_jd(...).
_DEMO_MATCHUPS: Dict[str, Dict[str, Any]] = {
    "nba": {"label": "BOS vs LAL", "args": ("BOS", "LAL"), "kwargs": {}},
    "mlb": {"label": "NYY vs BOS", "args": ("NYY", "BOS"), "kwargs": {}},
    "soccer": {"label": "Arsenal vs Man City", "args": ("Arsenal", "Man City"), "kwargs": {}},
    "soccer_intl": {"label": "England vs Croatia (WC, neutral)",
                    "args": ("England", "Croatia"), "kwargs": {"neutral": True}},
    "tennis": {"label": "Novak Djokovic vs Carlos Alcaraz",
               "args": ("Novak Djokovic", "Carlos Alcaraz"),
               "kwargs": {"surface": "Hard", "best_of": 3}},
}

# Lazily-built, cached predictor instances (corpus replay is expensive -- do it once per sport).
_PREDICTOR_CACHE: Dict[str, Any] = {}
# Build wall-clock (time.time()) per cached sport -- backs the TTL below (see
# golive_hardening_backlog_2026_07_17 finding #7: this cache never expired,
# so an always-on process kept serving a frozen predictor snapshot forever
# while the source parquet was refreshed underneath it). Mirrors the
# 3600s TTL discipline already used by frontend/serve.py's snapshot cache.
_PREDICTOR_CACHE_BUILT_AT: Dict[str, float] = {}
_PREDICTOR_TTL_SECONDS = 3600.0
# Cached JDs (None is a valid cached value meaning "tried and failed/unavailable").
_JD_CACHE: Dict[str, Any] = {}
_JD_CACHE_SET: set = set()

# Minimum distinct Elo ratings required across a slate's teams before the predictor is
# accepted into the cache. <= this threshold means the predictor has not replayed a real
# corpus (all teams share the init rating -> flat prior collapse -> degenerate probs).
_MIN_DISTINCT_RATINGS = 2


def demo_matchup(sport: str) -> Optional[Dict[str, Any]]:
    """Return the representative demo matchup descriptor for *sport* (label/args/kwargs)."""
    return _DEMO_MATCHUPS.get(sport.lower())


def _elo_ratings(pred: Any) -> Optional[Dict[str, float]]:
    """Extract the Elo ratings dict from a predictor instance, or None if not present.

    Covers the MLBPredictor (_elo attribute) used by the MLB degeneracy guard. Other
    sports do not have a flat-prior failure mode so returning None is safe.
    """
    elo = getattr(pred, "_elo", None)
    if isinstance(elo, dict):
        return elo
    return None


def validate_predictor_for_slate(sport: str, teams: List[str]) -> bool:
    """Return True iff the cached predictor for *sport* has >_MIN_DISTINCT_RATINGS across *teams*.

    A predictor that has NOT replayed a real corpus (fresh clone, warm-up race, or
    corpus-absent fallback) will assign every unknown team the init rating, producing
    identical p_home_win for every game. We detect this by checking the number of
    distinct Elo ratings across the slate's teams in the cached predictor.

    Returns True (safe) when:
      - the predictor is not cached yet (nothing to validate)
      - the predictor has no _elo dict (non-MLB sport; not subject to this collapse)
      - the slate's teams collectively map to >_MIN_DISTINCT_RATINGS distinct rating values
    Returns False (degenerate) when <=_MIN_DISTINCT_RATINGS distinct ratings are found for
    at least one pair of teams on the slate (flat prior collapse).
    """
    s = sport.lower()
    pred = _PREDICTOR_CACHE.get(s)
    if pred is None:
        return True  # not cached yet; nothing to invalidate
    elo = _elo_ratings(pred)
    if elo is None:
        return True  # sport has no _elo dict; degeneracy guard not applicable
    if not teams:
        return True  # no slate teams to check

    # Collect the Elo values for the slate teams (resolve best-effort: corpus key first,
    # then strip + upper; init rating is the fallback inside _elo_of so we can't call it
    # directly here without importing the predictor module. We read _elo directly instead).
    ratings: List[float] = []
    for team in teams:
        # Try corpus key directly, then uppercase form.
        val = elo.get(team) or elo.get(str(team).strip().upper())
        if val is not None:
            ratings.append(float(val))
    if len(ratings) < 2:
        return True  # too few resolved teams to judge; allow through

    distinct = len(set(round(r, 4) for r in ratings))
    return distinct > _MIN_DISTINCT_RATINGS


def _build_predictor(sport: str) -> Optional[Any]:
    """Instantiate (and cache) the sport's Predictor. Returns None on any failure.

    DEGENERACY GUARD: for MLB, after building, if the predictor's _elo dict has
    <=_MIN_DISTINCT_RATINGS distinct values across ALL known teams (init-rating collapse)
    the predictor is cached as None so a flat-prior snapshot is never emitted.
    """
    s = sport.lower()
    if s in _PREDICTOR_CACHE:
        built_at = _PREDICTOR_CACHE_BUILT_AT.get(s, 0.0)
        if (time.time() - built_at) < _PREDICTOR_TTL_SECONDS:
            return _PREDICTOR_CACHE[s]
        # TTL expired -- fall through and rebuild so a long-lived process
        # (e.g. :8098) eventually picks up a refreshed corpus on disk.
    pred: Optional[Any] = None
    try:
        if s == "nba":
            from domains.basketball_nba.predictor import NBAPredictor  # noqa: PLC0415
            pred = NBAPredictor()
        elif s == "mlb":
            # Prefer ratings refreshed to the current season (domains/mlb/refresh_ratings);
            # fall back to the frozen-2021 predictor if the current corpus is absent
            # (fresh clone) so a missing local file never fabricates or crashes.
            from domains.mlb.predictor import MLBPredictor  # noqa: PLC0415
            try:
                from domains.mlb.refresh_ratings import refreshed_predictor  # noqa: PLC0415
                pred = refreshed_predictor()
            except Exception:  # noqa: BLE001 -- current corpus absent -> frozen ratings
                pred = MLBPredictor()
        elif s == "soccer":
            from domains.soccer.predictor import SoccerPredictor  # noqa: PLC0415
            pred = SoccerPredictor()
        elif s == "soccer_intl":
            from domains.soccer_intl.predictor import IntlSoccerPredictor  # noqa: PLC0415
            pred = IntlSoccerPredictor()
        elif s == "tennis":
            from domains.tennis.predictor import TennisPredictor  # noqa: PLC0415
            pred = TennisPredictor()
        elif s == "wnba":
            # WNBA has no to_jd() (no score-distribution model yet -- see
            # domains/basketball_wnba/adapter.py); the predictor is still built
            # + cached here so bet_board/live_board/paper_today_support can
            # reach predict()/predict_live_state() through the SAME cached
            # factory as every other sport. get_demo_jd("wnba") degrades to
            # None (hasattr(pred, "to_jd") is False) -- honest, not a gap here.
            from domains.basketball_wnba.adapter import WNBAAdapter  # noqa: PLC0415
            pred = WNBAAdapter()
        elif s == "npb":
            # NPB (LANE 4): same shape as wnba -- no to_jd() (no runs/score-
            # distribution model, no predict_live -- see domains/baseball_npb/
            # adapter.py). predict() alone is enough for bet_board's
            # moneyline-only path. get_demo_jd("npb") degrades to None
            # (no _DEMO_MATCHUPS entry either) -- both honest, not gaps here.
            from domains.baseball_npb.adapter import NPBAdapter  # noqa: PLC0415
            pred = NPBAdapter()
        elif s == "kbo":
            # KBO (LANE 4): same shape as npb (see domains/baseball_kbo/adapter.py).
            from domains.baseball_kbo.adapter import KBOAdapter  # noqa: PLC0415
            pred = KBOAdapter()
    except Exception:  # noqa: BLE001 -- gitignored corpus absent / import error -> degrade
        pred = None

    # DEGENERACY GUARD (MLB flat-prior): refuse to cache a predictor whose Elo ratings
    # dict is nearly constant across all known teams (init-rating collapse). This catches
    # the warm-up race where corpus replay fails silently and every team gets _INIT.
    if pred is not None and s == "mlb":
        elo = _elo_ratings(pred)
        if elo is not None and len(elo) >= 2:
            all_vals = [round(v, 4) for v in elo.values()]
            distinct_all = len(set(all_vals))
            if distinct_all <= _MIN_DISTINCT_RATINGS:
                # Flat prior across ALL corpus teams: this predictor is unusable.
                pred = None

    _PREDICTOR_CACHE[s] = pred
    _PREDICTOR_CACHE_BUILT_AT[s] = time.time()
    return pred


def get_demo_jd(sport: str) -> Optional[Any]:
    """Build (cached) the demo JointDistribution for *sport* from its validated predictor.

    Returns a JointDistribution or None. NEVER raises: a missing corpus, an unknown sport, a
    predictor failure, or a to_jd error all degrade gracefully to None so the cohesive read
    simply carries no surface (no fabricated numbers).
    """
    s = sport.lower()
    if s in _JD_CACHE_SET:
        return _JD_CACHE.get(s)
    jd: Optional[Any] = None
    try:
        spec = _DEMO_MATCHUPS.get(s)
        pred = _build_predictor(s)
        if spec is not None and pred is not None and hasattr(pred, "to_jd"):
            jd = pred.to_jd(*spec["args"], **spec["kwargs"])
    except Exception:  # noqa: BLE001 -- never let a predictor failure break the read
        jd = None
    _JD_CACHE[s] = jd
    _JD_CACHE_SET.add(s)
    return jd


def clear_cache() -> None:
    """Drop cached predictors/JDs (used by tests to force a fresh build)."""
    _PREDICTOR_CACHE.clear()
    _PREDICTOR_CACHE_BUILT_AT.clear()
    _JD_CACHE.clear()
    _JD_CACHE_SET.clear()


def _main(argv: Optional[list] = None) -> int:
    import argparse  # noqa: PLC0415
    ap = argparse.ArgumentParser(description="Build the demo JD per sport from its predictor.")
    ap.add_argument("--sport", default="nba")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    sports: Tuple[str, ...] = (("nba", "mlb", "soccer", "tennis") if a.all else (a.sport,))
    for sp in sports:
        mu = demo_matchup(sp)
        jd = get_demo_jd(sp)
        label = mu["label"] if mu else "(unknown sport)"
        if jd is None:
            print(f"{sp.upper():7s} {label:35s} -> JD=None (predictor/corpus unavailable)")
        else:
            ns = getattr(jd, "n_sims", "?")
            ko = getattr(jd, "n_outcomes", "?")
            print(f"{sp.upper():7s} {label:35s} -> JD ok  n_sims={ns} n_outcomes={ko}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
