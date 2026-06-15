"""scripts.platformkit.predictor_jd — demo JointDistribution per sport from the validated predictors.

The central cohesion seam: each sport ships a validated domains/<sport>/predictor.py with a
to_jd() that emits a coherent JointDistribution (ML/spread/total all read off ONE sample
matrix). This thin module instantiates the sport's Predictor for ONE representative demo
matchup and returns that JD, so the cohesive read's assemble_read can run on the SAME
distribution our best predictor produces (instead of carrying surface=None).

GUARDED: every call is wrapped try/except -> None; building a Predictor reads gitignored
parquet corpora, so a fresh clone (no data/) degrades gracefully to None (no surface, no
fabricated numbers). Predictors are lazily built and cached per sport so repeated reads do
not replay the corpus.

No edge is implied: the JD is the predictor's calibrated structure; markets are efficient.

Public API:
    get_demo_jd(sport) -> JointDistribution | None
    demo_matchup(sport) -> dict (the representative matchup label, for provenance)
INVARIANTS: never edit src/ or kernel/; reuse the domain predictors; <=300 LOC; no secrets.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# Representative demo matchups per sport (two strong sides / top players present in the corpus).
# Each value is the positional args to the predictor's to_jd(...).
_DEMO_MATCHUPS: Dict[str, Dict[str, Any]] = {
    "nba": {"label": "BOS vs LAL", "args": ("BOS", "LAL"), "kwargs": {}},
    "mlb": {"label": "NYY vs BOS", "args": ("NYY", "BOS"), "kwargs": {}},
    "soccer": {"label": "Arsenal vs Man City", "args": ("Arsenal", "Man City"), "kwargs": {}},
    "tennis": {"label": "Novak Djokovic vs Carlos Alcaraz",
               "args": ("Novak Djokovic", "Carlos Alcaraz"),
               "kwargs": {"surface": "Hard", "best_of": 3}},
}

# Lazily-built, cached predictor instances (corpus replay is expensive — do it once per sport).
_PREDICTOR_CACHE: Dict[str, Any] = {}
# Cached JDs (None is a valid cached value meaning "tried and failed/unavailable").
_JD_CACHE: Dict[str, Any] = {}
_JD_CACHE_SET: set = set()


def demo_matchup(sport: str) -> Optional[Dict[str, Any]]:
    """Return the representative demo matchup descriptor for *sport* (label/args/kwargs)."""
    return _DEMO_MATCHUPS.get(sport.lower())


def _build_predictor(sport: str) -> Optional[Any]:
    """Instantiate (and cache) the sport's Predictor. Returns None on any failure."""
    s = sport.lower()
    if s in _PREDICTOR_CACHE:
        return _PREDICTOR_CACHE[s]
    pred: Optional[Any] = None
    try:
        if s == "nba":
            from domains.basketball_nba.predictor import NBAPredictor  # noqa: PLC0415
            pred = NBAPredictor()
        elif s == "mlb":
            from domains.mlb.predictor import MLBPredictor  # noqa: PLC0415
            pred = MLBPredictor()
        elif s == "soccer":
            from domains.soccer.predictor import SoccerPredictor  # noqa: PLC0415
            pred = SoccerPredictor()
        elif s == "tennis":
            from domains.tennis.predictor import TennisPredictor  # noqa: PLC0415
            pred = TennisPredictor()
    except Exception:  # noqa: BLE001 — gitignored corpus absent / import error -> degrade
        pred = None
    _PREDICTOR_CACHE[s] = pred
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
    except Exception:  # noqa: BLE001 — never let a predictor failure break the read
        jd = None
    _JD_CACHE[s] = jd
    _JD_CACHE_SET.add(s)
    return jd


def clear_cache() -> None:
    """Drop cached predictors/JDs (used by tests to force a fresh build)."""
    _PREDICTOR_CACHE.clear()
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
