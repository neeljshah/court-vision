"""domains.basketball_wnba.atlas_extract_common -- shared loaders/formulas for
the WNBA zero-new-fetch atlas extraction (build_queue rank 1, see
docs/research/intel-layer/WNBA_TRUTH_SPEC_2026-07-04.md Section 3 priority 1
and intelligence_program.json build_queue[0]).

WHY THIS MODULE: atlas_extract_player.py and atlas_extract_team.py both need
the same raw-JSON walk (168 games under cdn_backfill/<gid>/{boxscore,
playbyplay}.json), the same ISO8601 minutes parser, and the same shooting-
efficiency formulas (TS%/eFG%). Factored here so neither builder duplicates
the parse/formula logic (efficiency ladder: reuse over reinvent).

ZERO NEW FETCH: every function here is pure/read-only against files already
on disk (data/domains/wnba/cdn_backfill/). No network calls anywhere in this
module or its two sibling builders.

PROVENANCE (storage R5, baked in at write time, not retrofit): every atlas
row this pipeline produces carries as_of/n/confidence/corpus_id columns, per
intelligence_program.json's "provenance_note": "write as_of/corpus_id/season
columns at creation".

INVARIANTS: standalone; <=300 LOC; ASCII only; no pip installs; never raises
(a malformed/missing game degrades to a skipped game, not an aborted run).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_atlas_extract_common.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]
BACKFILL_DIR = _REPO_ROOT / "data" / "domains" / "wnba" / "cdn_backfill"
ATLAS_OUT_DIR = _REPO_ROOT / "data" / "cache"

CORPUS_ID = "wnba_cdn_backfill_2026"  # single-season corpus, see truth-spec limit #4
SEASON = "2026"

_MIN_SEC = re.compile(r"PT(?:(\d+)M)?(?:([\d.]+)S)?")


def iso_minutes(duration: Optional[str]) -> Optional[float]:
    """ISO8601 'PT12M23.00S' -> minutes (float). None/'' -> 0.0 (DNP convention
    observed on this corpus: minutesCalculated=='PT00M' for played=='0').
    Malformed strings -> None (honest gap, never a fabricated 0.0)."""
    if duration is None:
        return None
    if duration == "":
        return 0.0
    m = _MIN_SEC.match(str(duration))
    if not m or (m.group(1) is None and m.group(2) is None):
        return None
    minutes = float(m.group(1) or 0)
    seconds = float(m.group(2) or 0)
    return round(minutes + seconds / 60.0, 4)


def true_shooting_pct(points: float, fga: float, fta: float) -> Optional[float]:
    """TS% = points / (2 * (fga + 0.44*fta)). None if denominator is 0 (no
    fabricated 0.0 for a player with zero field-goal/free-throw attempts)."""
    denom = 2.0 * (fga + 0.44 * fta)
    if denom <= 0:
        return None
    return round(points / denom, 4)


def effective_fg_pct(fgm: float, fg3m: float, fga: float) -> Optional[float]:
    """eFG% = (fgm + 0.5*fg3m) / fga. None if fga==0."""
    if fga <= 0:
        return None
    return round((fgm + 0.5 * fg3m) / fga, 4)


def team_pace_proxy(fga: float, fta: float, orb: float, tov: float) -> Optional[float]:
    """Standard pace/possessions estimator: FGA + 0.44*FTA - ORB + TOV.
    Team-game level (not per-48 normalized -- WNBA quarters are 10min not
    12min, so any per-48 conversion would be an NBA-borrowed assumption this
    spec explicitly warns against; leave as a raw per-game possession
    estimate). None if all inputs are falsy/missing."""
    if fga is None or fta is None or orb is None or tov is None:
        return None
    return round(fga + 0.44 * fta - orb + tov, 4)


def load_game_pair(game_id: str) -> Optional[Dict[str, dict]]:
    """{'boxscore':.., 'playbyplay':..} game dicts for *game_id*, or None if
    either file is absent/malformed. Never raises."""
    d = BACKFILL_DIR / str(game_id)
    out: Dict[str, dict] = {}
    for name in ("boxscore", "playbyplay"):
        p = d / f"{name}.json"
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        game = payload.get("game")
        if not isinstance(game, dict):
            return None
        out[name] = game
    return out


def iter_backfilled_games(backfill_dir: Optional[Path] = None
                           ) -> Iterator[Tuple[str, Dict[str, dict]]]:
    """Yield (game_id, {'boxscore':.., 'playbyplay':..}) for every game under
    *backfill_dir* (default BACKFILL_DIR) whose pair loads cleanly. Skips (does
    not raise on) any directory missing/malformed files."""
    root = backfill_dir if backfill_dir is not None else BACKFILL_DIR
    if not root.exists():
        return
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        pair = load_game_pair(d.name) if backfill_dir is None else _load_pair_from(d)
        if pair is None:
            continue
        yield d.name, pair


def _load_pair_from(game_dir: Path) -> Optional[Dict[str, dict]]:
    """Same as load_game_pair but reads from an explicit directory (used when
    iter_backfilled_games is pointed at a non-default root, e.g. a test's
    tmp_path)."""
    out: Dict[str, dict] = {}
    for name in ("boxscore", "playbyplay"):
        p = game_dir / f"{name}.json"
        if not p.exists():
            return None
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        game = payload.get("game")
        if not isinstance(game, dict):
            return None
        out[name] = game
    return out


def safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    """Nested dict.get chain that never raises on a non-dict intermediate."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


def atlas_write_path(name: str) -> Path:
    """data/cache/atlas_wnba_<name>.parquet -- matches the NBA atlas naming
    convention (atlas_player_*/atlas_team_*) with a wnba_ infix so the two
    sport atlases never collide on disk."""
    return ATLAS_OUT_DIR / f"atlas_wnba_{name}.parquet"


__all__ = [
    "BACKFILL_DIR", "ATLAS_OUT_DIR", "CORPUS_ID", "SEASON",
    "iso_minutes", "true_shooting_pct", "effective_fg_pct", "team_pace_proxy",
    "load_game_pair", "iter_backfilled_games", "safe_get", "atlas_write_path",
]
