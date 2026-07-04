"""scripts.platformkit.ingame.ingame_tail_scan_multi -- LANE C: multi-sport price-band
(tail) miscalibration scan (tennis + soccer_intl / World Cup + wnba + npb + kbo),
generalizing ingame_tail_scan.py (MLB-only) to run per-sport over whatever
outcome-graded in-play ticks exist on disk right now.

WHY A SEPARATE MODULE (not a param on ingame_tail_scan.scan)
-------------------------------------------------------------
ingame_tail_scan.scan() is MLB-specific end to end: its outcome_lookup defaults
to MlbOutcomeResolver + the ESPN numeric-id boxscore parquet. This module reuses
its BAND MATH (band_stats / band_label / tick loading) unchanged via import, but
supplies a per-sport outcome_lookup dispatcher: soccer_intl games resolve via
SoccerOutcomeResolver (home_win derived from final_score, draw -> None -- a draw
is not a binary home-win label so it is excluded, never guessed); tennis has NO
resolver and (as of this scan) NO captured grade files at all -- inplay_capture_
loop.DEFAULT_SPORTS is currently ["mlb", "soccer_intl"] only, so tennis capture
has not started. That is reported honestly as INSUFFICIENT_N with the real n=0,
not stretched or faked. wnba/npb/kbo (2026-07-04 LANE 5 addition) dispatch to
WnbaOutcomeResolver / NpbOutcomeResolver / KboOutcomeResolver (same
home_win(ticker)->{0,1}|None contract) -- their in-play capture has not started
as of this addition either, so they too read INSUFFICIENT_N n=0 honestly until
capture begins.

HONESTY: calibration measurement only; edge_claimed is ALWAYS False; a sport
with fewer than MIN_GAMES_SPORT outcome-graded games gets verdict
INSUFFICIENT_N with the EXACT n, never a stretched verdict.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; no network; no data/registry
write; no flag flip.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_scan_multi.py -q
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame.ingame_tail_scan import (
    DEFAULT_GRADE_DIR,
    MIN_GAMES_BAND,
    scan as _mlb_style_scan,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]

# Sports this scan knows how to run, in report order. "soccer" (club leagues) has
# no captured grade dir yet either (only "mlb" and "soccer_intl" exist on disk at
# time of writing) but is listed so a future capture start is picked up with zero
# code change -- an empty/missing dir just reads INSUFFICIENT_N n=0, honestly.
# wnba/npb/kbo added 2026-07-04 (LANE 5 pre-registration) -- capture has not
# started for them yet either, so they read INSUFFICIENT_N n=0 until it does.
SPORTS: List[str] = ["tennis", "soccer_intl", "soccer", "wnba", "npb", "kbo"]

MIN_GAMES_SPORT: int = 20  # per the brief: <20 graded games -> INSUFFICIENT_N

OutcomeLookup = Callable[[str], Optional[int]]


def _out_path(sport: str) -> Path:
    return _REPO_ROOT / "data" / "domains" / sport.lower() / "ingame_tail_scan.json"


# --------------------------------------------------------------------------------------- #
# per-sport outcome lookup dispatch                                                        #
# --------------------------------------------------------------------------------------- #
def _soccer_lookup() -> OutcomeLookup:
    """stem (Kalshi WC ticker) -> home_win in {0,1} or None. A draw resolves to
    a real final_score but is NOT a binary home-win label, so it is excluded
    (returns None) rather than guessed as either 0 or 1."""
    try:
        from scripts.platformkit.ingame.soccer_outcome import SoccerOutcomeResolver
        res = SoccerOutcomeResolver()
    except Exception as exc:  # noqa: BLE001 -- resolver unavailable -> every game unresolved
        logger.debug("ingame_tail_scan_multi soccer resolver unavailable: %s", exc)
        return lambda stem: None

    def lookup(stem: str) -> Optional[int]:
        try:
            score = res.final_score(stem)
        except Exception as exc:  # noqa: BLE001
            logger.debug("soccer final_score(%s) failed: %s", stem, exc)
            return None
        if score is None:
            return None
        hs, as_ = score
        if hs == as_:
            return None  # draw: not a home-win label
        return int(hs > as_)
    return lookup


def _tennis_lookup() -> OutcomeLookup:
    """tennis_outcome_resolver.TennisOutcomeResolver.home_win, disk-first (fresh
    espn_matches.parquet) else live ESPN scoreboard fallback (keyless). "home" =
    the ticker's FIRST surname code, a consistent but arbitrary convention (see
    tennis_outcome_resolver's module docstring) -- tennis in-play capture only
    just started (inplay_capture_loop.DEFAULT_SPORTS now includes 'tennis'), so
    this mostly reads INSUFFICIENT_N with a real n until enough games settle."""
    try:
        from scripts.platformkit.ingame.tennis_outcome_resolver import TennisOutcomeResolver
        res = TennisOutcomeResolver()
    except Exception as exc:  # noqa: BLE001 -- resolver unavailable -> every game unresolved
        logger.debug("ingame_tail_scan_multi tennis resolver unavailable: %s", exc)
        return lambda stem: None
    return res.home_win


def _wnba_lookup() -> OutcomeLookup:
    """wnba_outcome_resolver.WnbaOutcomeResolver.home_win keyed off the Kalshi
    KXWNBAGAME ticker (see that module's docstring for the ticker-shape
    derivation). Added 2026-07-04 (LANE 5 pre-registration); WNBA in-play
    capture has not started yet so this mostly reads INSUFFICIENT_N n=0."""
    try:
        from scripts.platformkit.ingame.wnba_outcome_resolver import WnbaOutcomeResolver
        res = WnbaOutcomeResolver()
    except Exception as exc:  # noqa: BLE001 -- resolver unavailable -> every game unresolved
        logger.debug("ingame_tail_scan_multi wnba resolver unavailable: %s", exc)
        return lambda stem: None
    return res.home_win


def _npb_lookup() -> OutcomeLookup:
    """npb_outcome_resolver.NpbOutcomeResolver.home_win keyed off the Kalshi
    KXNPBGAME ticker. Added 2026-07-04 (LANE 5 pre-registration); NPB in-play
    capture has not started yet so this mostly reads INSUFFICIENT_N n=0."""
    try:
        from scripts.platformkit.ingame.npb_outcome_resolver import NpbOutcomeResolver
        res = NpbOutcomeResolver()
    except Exception as exc:  # noqa: BLE001 -- resolver unavailable -> every game unresolved
        logger.debug("ingame_tail_scan_multi npb resolver unavailable: %s", exc)
        return lambda stem: None
    return res.home_win


def _kbo_lookup() -> OutcomeLookup:
    """kbo_outcome_resolver.KboOutcomeResolver.home_win keyed off the Kalshi
    KXKBOGAME ticker. Added 2026-07-04 (LANE 5 pre-registration); KBO in-play
    capture has not started yet so this mostly reads INSUFFICIENT_N n=0."""
    try:
        from scripts.platformkit.ingame.kbo_outcome_resolver import KboOutcomeResolver
        res = KboOutcomeResolver()
    except Exception as exc:  # noqa: BLE001 -- resolver unavailable -> every game unresolved
        logger.debug("ingame_tail_scan_multi kbo resolver unavailable: %s", exc)
        return lambda stem: None
    return res.home_win


_LOOKUP_BUILDERS: Dict[str, Callable[[], OutcomeLookup]] = {
    "soccer_intl": _soccer_lookup,
    "soccer": _soccer_lookup,
    "tennis": _tennis_lookup,
    "wnba": _wnba_lookup,
    "npb": _npb_lookup,
    "kbo": _kbo_lookup,
}


def _n_graded_games(grade_dir: Path, sport: str, lookup: OutcomeLookup) -> int:
    base = Path(grade_dir) / sport.lower()
    if not base.is_dir():
        return 0
    files = [f for f in sorted(base.glob("*.jsonl")) if not f.name.startswith("_")]
    n = 0
    for f in files:
        try:
            if lookup(f.stem) is not None:
                n += 1
        except Exception as exc:  # noqa: BLE001 -- a bad stem must not sink the count
            logger.debug("ingame_tail_scan_multi lookup(%s) failed: %s", f.stem, exc)
    return n


def scan_sport(sport: str, grade_dir: Optional[Path] = None,
               outcome_lookup: Optional[OutcomeLookup] = None,
               iters: int = 2000, since: Optional[str] = None,
               min_games: int = MIN_GAMES_SPORT) -> Dict[str, Any]:
    """Run the band scan for one sport. Returns a result dict shaped like
    ingame_tail_scan.scan()'s output, PLUS a top-level 'n_games_graded' /
    'sport_verdict' pair. If n_games_graded < min_games the sport_verdict is
    INSUFFICIENT_N (n reported exactly) and 'bands' is still populated from
    whatever the underlying scan found (so an operator can see the partial
    picture), but no band/pooled verdict may be read as SHIP-class evidence
    below the floor."""
    gd = Path(grade_dir) if grade_dir is not None else DEFAULT_GRADE_DIR
    lookup = outcome_lookup or _LOOKUP_BUILDERS.get(sport.lower(), lambda: (lambda s: None))()
    n_graded = _n_graded_games(gd, sport, lookup)
    result = _mlb_style_scan(grade_dir=gd, sport=sport, outcome_lookup=lookup,
                              iters=iters, since=since)
    result["n_games_graded"] = n_graded
    result["min_games_sport"] = min_games
    result["sport_verdict"] = (
        "INSUFFICIENT_N" if n_graded < min_games else "SCANNED"
    )
    result["component"] = "m_ingame_tail_scan_multi"
    return result


def scan_all(sports: Optional[List[str]] = None, grade_dir: Optional[Path] = None,
             iters: int = 2000, since: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Run scan_sport for every sport in *sports* (default SPORTS). Never raises
    -- a per-sport exception is caught and that sport reports sport_verdict
    ERROR with the exception string, so one bad sport can never sink the rest."""
    out: Dict[str, Dict[str, Any]] = {}
    for sport in (sports or SPORTS):
        try:
            out[sport] = scan_sport(sport, grade_dir=grade_dir, iters=iters, since=since)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ingame_tail_scan_multi scan_sport(%s) failed: %s", sport, exc)
            out[sport] = {
                "component": "m_ingame_tail_scan_multi", "sport": sport,
                "sport_verdict": "ERROR", "error": str(exc),
                "n_games_graded": 0, "edge_claimed": False,
            }
    return out


def write_artifacts(results: Dict[str, Dict[str, Any]]) -> Dict[str, Path]:
    """Write one JSON artifact per sport to data/domains/<sport>/ingame_tail_scan.json.
    Atomic write (tmp + replace). Returns {sport: path}."""
    paths: Dict[str, Path] = {}
    for sport, result in results.items():
        p = _out_path(sport)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        tmp.replace(p)
        paths[sport] = p
    return paths


def main() -> None:
    results = scan_all()
    print("in-game price-band multi-sport scan | %s" %
          datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for sport, res in results.items():
        print("  %-12s verdict=%-14s n_graded=%d (min=%d)" % (
            sport, res.get("sport_verdict"), res.get("n_games_graded", 0),
            res.get("min_games_sport", MIN_GAMES_SPORT)))
    paths = write_artifacts(results)
    for sport, p in paths.items():
        print("  artifact[%s]: %s" % (sport, p))
    print("NOTE: calibration measurement only -- fees/fills not modeled; no edge claimed.")


if __name__ == "__main__":
    main()
