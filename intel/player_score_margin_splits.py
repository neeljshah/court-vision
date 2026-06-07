"""ARM-B atlas section: ``score_margin_splits`` — per-player production by score state.

Implements :class:`AtlasSection` for the ``"score_margin_splits"`` section of a
player's persistent profile.  Measures how a player's usage, eFG%, pace/tempo, and
shot mix shift when their team is **leading**, **tied**, or **trailing** during a game.

**Data flow:**
  1. Parse ``data/cache/quarter_box/<game_id>_q<N>.json`` to get per-quarter team pts
     and per-player per-quarter box stats (fgm, fga, fg3m, fg3a, pts, reb, ast, min).
  2. Accumulate team pts entering each quarter → score state at START of quarter:
       leading  if team_lead > +5
       tied     if |team_lead| <= 5
       trailing if team_lead < -5
  3. Filter player-quarter rows by ``game_date <= as_of`` using the game_date map
     from ``data/player_adv_stats.parquet`` (game_id → game_date).
  4. Aggregate per score-state bucket: pts_pg, reb_pg, ast_pg, fg3m_pg, min_pg,
     efg_pct (=fgm+0.5*fg3m)/fga), fg3a_rate (=fg3a/fga), fga_pg, n_quarters,
     n_games.

**Sub-field coverage:**

REAL (populated from quarter_box JSONs + adv_stats game_date join):
  leading.*   — pts_pg, reb_pg, ast_pg, fg3m_pg, fga_pg, efg_pct, fg3a_rate, min_pg,
                n_quarters, n_games
  tied.*      — same fields
  trailing.*  — same fields

DEFER (no per-quarter opponent context available):
  pace.*      — DEFER: team pace per quarter is not stored in quarter_box JSONs
                (would need play-by-play event counts or shot-clock data per quarter)
  shot_mix.*  — DEFER: zone/type breakdown per score state unavailable in repo
                (would need shot-chart parquet with score state tagging)

RESERVED CV SLOTS (value=None, CV branch fills later):
  cv_usage_leading   — mean CV-derived usage rate (possessions used / poss played)
                       in leading quarters, from CV EventDetector + homography.
  cv_usage_trailing  — same for trailing quarters.
  cv_drive_rate_trailing — drive attempts per minute when trailing (CV EventDetector);
                       captures tendency to attack vs coast under deficit.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.loop.atlas import AtlasArtifact, AtlasSection, CVSlot, confidence_from_n
from src.loop.profile_factory_bridge import register_section

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = DATA / "cache"
QBOX_DIR = CACHE / "quarter_box"

# Score-state thresholds (points, at start of quarter)
_LEADING_THRESH = 5    # team_lead > +5  -> leading
_TRAILING_THRESH = -5  # team_lead < -5  -> trailing
# (between -5 and +5 inclusive -> tied)

# ---------------------------------------------------------------------------
# Module-level lazy caches (cleared if needed by tests)
# ---------------------------------------------------------------------------

_GAME_DATE_MAP: Optional[Dict[str, str]] = None   # game_id -> "YYYY-MM-DD"
_QBOX_CACHE: Dict[str, Dict[int, dict]] = {}       # game_id -> {quarter: parsed_qbox}


def _list_qbox_files() -> List[Path]:
    """Return all quarter_box JSON file paths; extracted for testability."""
    if QBOX_DIR.exists():
        return list(QBOX_DIR.glob("*_q[1-4].json"))
    return []


def _load_game_date_map() -> Dict[str, str]:
    """Return game_id -> game_date string from player_adv_stats.parquet (cached)."""
    global _GAME_DATE_MAP
    if _GAME_DATE_MAP is None:
        path = DATA / "player_adv_stats.parquet"
        if not path.exists():
            _GAME_DATE_MAP = {}
        else:
            try:
                adv = pd.read_parquet(path, columns=["game_id", "game_date"])
                _GAME_DATE_MAP = (
                    adv.drop_duplicates("game_id")
                    .set_index("game_id")["game_date"]
                    .astype(str)
                    .to_dict()
                )
            except Exception:
                _GAME_DATE_MAP = {}
    return _GAME_DATE_MAP


def _load_qbox(game_id: str) -> Dict[int, dict]:
    """Load all available quarters for a game from quarter_box JSONs.

    Returns ``{quarter_int: parsed_dict}`` where each dict has:
      ``teams``: list of team dicts (team_abbreviation, pts, ...)
      ``players``: list of player dicts (player_id, team_abbreviation, fgm, fga,
                   fg3m, fg3a, pts, reb, ast, min as 'MM:SS' string, ...)
    """
    if game_id in _QBOX_CACHE:
        return _QBOX_CACHE[game_id]
    quarters: Dict[int, dict] = {}
    for q in range(1, 5):
        fpath = QBOX_DIR / f"{game_id}_q{q}.json"
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                quarters[q] = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
    _QBOX_CACHE[game_id] = quarters
    return quarters


def _parse_min(min_val: Any) -> float:
    """Parse a 'MM:SS' string or numeric minutes value to float minutes.

    Critical: quarter_box JSONs store minutes as 'MM:SS' strings.
    """
    if min_val is None:
        return 0.0
    if isinstance(min_val, (int, float)):
        f = float(min_val)
        return 0.0 if (np.isnan(f) or np.isinf(f) or f < 0) else f
    s = str(min_val).strip()
    if ":" in s:
        parts = s.split(":")
        try:
            mm = float(parts[0])
            ss = float(parts[1]) if len(parts) > 1 else 0.0
            return mm + ss / 60.0
        except (ValueError, IndexError):
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _score_state(team_lead: float) -> str:
    """Categorise a score lead (positive = my team ahead) into state label."""
    if team_lead > _LEADING_THRESH:
        return "leading"
    if team_lead < _TRAILING_THRESH:
        return "trailing"
    return "tied"


def _rd(v: Any) -> Optional[float]:
    """Clean scalar: NaN/inf -> None, round to 4 dp."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if np.isnan(f) or np.isinf(f):
        return None
    return round(f, 4)


def _compute_margin_splits(
    pid: int,
    as_of: _dt.datetime,
) -> Tuple[Dict[str, Any], int]:
    """Core computation: aggregate player stats by score-margin state.

    Returns ``(splits_dict, n_games)`` where splits_dict has keys
    ``leading``, ``tied``, ``trailing``.  Each value is a sub-dict of aggregated
    stats.  ``n_games`` is the count of unique games contributing data.

    Leak-safe: only games with game_date <= as_of are included.
    """
    gd_map = _load_game_date_map()
    as_of_str = as_of.date().isoformat()

    # Accumulators per state: lists of per-quarter row dicts
    state_rows: Dict[str, List[dict]] = {
        "leading": [], "tied": [], "trailing": []
    }
    game_ids_seen: set = set()

    # Scan all quarter_box files for this player
    # We look for any game_id that appears in game_date_map first (filtered by as_of)
    # then parse the qbox for matching player rows
    valid_game_ids = {
        gid for gid, gd in gd_map.items()
        if gd and gd[:10] <= as_of_str
    }

    all_files = _list_qbox_files()

    # Group files by game_id
    files_by_game: Dict[str, List[Path]] = {}
    for fpath in all_files:
        # filename: <game_id>_q<N>.json
        stem = fpath.stem  # e.g. "0022400001_q1"
        parts = stem.rsplit("_", 1)
        if len(parts) != 2:
            continue
        gid = parts[0]
        files_by_game.setdefault(gid, []).append(fpath)

    for game_id, _ in files_by_game.items():
        # Leak filter
        if game_id not in valid_game_ids:
            continue

        quarters = _load_qbox(game_id)
        if not quarters:
            continue

        # Check if player appears in any quarter
        player_present = any(
            any(p["player_id"] == pid for p in qdata.get("players", []))
            for qdata in quarters.values()
        )
        if not player_present:
            continue

        # Determine player's team_abbreviation from first quarter they appear in
        player_team: Optional[str] = None
        for q in sorted(quarters.keys()):
            for p in quarters[q].get("players", []):
                if p["player_id"] == pid:
                    player_team = p.get("team_abbreviation")
                    break
            if player_team:
                break

        if player_team is None:
            continue

        game_ids_seen.add(game_id)

        # Accumulate cumulative pts per team entering each quarter
        team_cum: Dict[str, float] = {}

        for q in sorted(quarters.keys()):
            qdata = quarters[q]

            # Score state at START of this quarter (cumulative entering, before q pts)
            if not team_cum:
                # Q1 start: both teams at 0
                my_pts = 0.0
                opp_pts_total = 0.0
                team_lead = 0.0
            else:
                my_pts = team_cum.get(player_team, 0.0)
                opp_pts_total = sum(
                    v for k, v in team_cum.items() if k != player_team
                )
                team_lead = my_pts - opp_pts_total

            state = _score_state(team_lead)

            # Find this player's row in this quarter
            player_row: Optional[dict] = None
            for p in qdata.get("players", []):
                if p["player_id"] == pid:
                    player_row = p
                    break

            # Update cumulative team pts for NEXT quarter's state computation
            for t in qdata.get("teams", []):
                ta = t.get("team_abbreviation", "")
                if ta:
                    team_cum[ta] = team_cum.get(ta, 0.0) + float(t.get("pts", 0) or 0)

            if player_row is None:
                continue  # player didn't play this quarter (DNP or sat out)

            fgm = float(player_row.get("fgm", 0) or 0)
            fga = float(player_row.get("fga", 0) or 0)
            fg3m = float(player_row.get("fg3m", 0) or 0)
            fg3a = float(player_row.get("fg3a", 0) or 0)
            pts = float(player_row.get("pts", 0) or 0)
            reb = float(player_row.get("reb", 0) or 0)
            ast = float(player_row.get("ast", 0) or 0)
            min_played = _parse_min(player_row.get("min", 0))

            state_rows[state].append({
                "game_id": game_id,
                "quarter": q,
                "fgm": fgm,
                "fga": fga,
                "fg3m": fg3m,
                "fg3a": fg3a,
                "pts": pts,
                "reb": reb,
                "ast": ast,
                "min": min_played,
            })

    # Aggregate each state bucket
    splits: Dict[str, Any] = {}
    for state in ("leading", "tied", "trailing"):
        rows = state_rows[state]
        if not rows:
            splits[state] = None
            continue

        n_q = len(rows)
        n_g = len(set(r["game_id"] for r in rows))
        total_min = sum(r["min"] for r in rows)

        # Per-game averages (accumulate per-game then average)
        # Group by game to compute per-game totals first
        game_agg: Dict[str, dict] = {}
        for r in rows:
            gid = r["game_id"]
            if gid not in game_agg:
                game_agg[gid] = {
                    "pts": 0.0, "reb": 0.0, "ast": 0.0,
                    "fg3m": 0.0, "fgm": 0.0, "fga": 0.0,
                    "fg3a": 0.0, "min": 0.0,
                }
            for k in ("pts", "reb", "ast", "fg3m", "fgm", "fga", "fg3a", "min"):
                game_agg[gid][k] += r[k]

        g_vals = list(game_agg.values())
        n_g_actual = len(g_vals)

        def _mean(key: str) -> Optional[float]:
            if not g_vals:
                return None
            return _rd(sum(g[key] for g in g_vals) / n_g_actual)

        pts_pg = _mean("pts")
        reb_pg = _mean("reb")
        ast_pg = _mean("ast")
        fg3m_pg = _mean("fg3m")
        fga_pg = _mean("fga")
        min_pg = _mean("min")

        # eFG% = (fgm + 0.5 * fg3m) / fga  (season aggregate, not per-game mean)
        total_fgm = sum(r["fgm"] for r in rows)
        total_fg3m = sum(r["fg3m"] for r in rows)
        total_fga = sum(r["fga"] for r in rows)
        total_fg3a = sum(r["fg3a"] for r in rows)

        efg_pct: Optional[float] = None
        if total_fga > 0:
            efg_raw = (total_fgm + 0.5 * total_fg3m) / total_fga
            # Clamp to [0, 1.6] per validator eFG ceiling rule
            efg_pct = _rd(min(efg_raw, 1.6))
            if efg_pct is not None and efg_pct < 0:
                efg_pct = None

        fg3a_rate: Optional[float] = None
        if total_fga > 0:
            rate = total_fg3a / total_fga
            # _rate must be in [0, 1]
            fg3a_rate = _rd(min(max(rate, 0.0), 1.0))

        splits[state] = {
            "pts_pg": pts_pg,
            "reb_pg": reb_pg,
            "ast_pg": ast_pg,
            "fg3m_pg": fg3m_pg,
            "fga_pg": fga_pg,
            "efg_pct": efg_pct,
            "fg3a_rate": fg3a_rate,
            "min_pg": min_pg,
            "n_quarters": n_q,
            "n_games": n_g_actual,
        }

    n_games = len(game_ids_seen)
    return splits, n_games


# ---------------------------------------------------------------------------
# Main AtlasSection implementation
# ---------------------------------------------------------------------------


class PlayerScoreMarginSplits(AtlasSection):
    """Player production splits by score-margin state (leading / tied / trailing).

    Section key: ``"score_margin_splits"``.
    Entity: ``"player"``.

    Computes per-player averages (pts, reb, ast, fg3m, fga, eFG%, fg3a_rate, min)
    for each score-state bucket, where state is determined at the START of each
    quarter based on cumulative team pts entering that quarter.

    Thresholds: leading > +5 pts, trailing < -5 pts, else tied.

    Sources:
      - ``data/cache/quarter_box/<game_id>_q<N>.json`` (per-quarter player + team stats)
      - ``data/player_adv_stats.parquet`` (game_id -> game_date for leak-safe filter)

    DEFER sections (no source available):
      - pace.*      : team pace per quarter (would need PBP possession counts per Q)
      - shot_mix.*  : zone/type breakdown by score state (no shot-chart parquet)

    RESERVED CV SLOTS (value=None):
      - cv_usage_leading, cv_usage_trailing, cv_drive_rate_trailing
    """

    name: str = "score_margin_splits"
    entity: str = "player"
    source_name: str = (
        "quarter_box/*.json + player_adv_stats.parquet"
    )
    conf_cap: Optional[str] = None

    def build(self, entity_id: Any, as_of: _dt.datetime) -> Optional[AtlasArtifact]:
        """Build the score_margin_splits artifact for player ``entity_id`` as-of ``as_of``.

        Leak guarantee: only game_ids whose game_date (from player_adv_stats) is
        <= as_of are included in aggregations.

        Returns None when fewer than 1 quarter of data is found for this player.
        """
        pid = int(entity_id)
        as_of_str = as_of.date().isoformat()

        splits, n_games = _compute_margin_splits(pid, as_of)

        # Bail if no data at all (player absent from all quarter_box sources)
        if n_games == 0 and all(splits.get(s) is None for s in ("leading", "tied", "trailing")):
            return None

        # DEFER sub-dicts (no data source available)
        pace: Dict[str, Any] = {
            "_note": (
                "DEFER: per-quarter team pace (possessions) not available in "
                "quarter_box JSONs. Requires play-by-play possession counts per quarter."
            )
        }
        shot_mix: Dict[str, Any] = {
            "_note": (
                "DEFER: shot zone/type breakdown by score state not available. "
                "Requires shot-chart parquet tagged with score state per shot."
            )
        }

        sub_fields: Dict[str, Any] = {
            "leading": splits.get("leading"),
            "tied": splits.get("tied"),
            "trailing": splits.get("trailing"),
            "pace": pace,
            "shot_mix": shot_mix,
            "_thresholds": {
                "leading_min_lead": _LEADING_THRESH,
                "trailing_max_lead": _TRAILING_THRESH,
                "_note": "score state determined at START of each quarter",
            },
        }

        n = n_games
        confidence = confidence_from_n(n, cap=self.conf_cap)

        provenance: Dict[str, Any] = {
            "source": self.source_name,
            "n": n,
            "confidence": confidence,
            "as_of": as_of_str,
        }

        return AtlasArtifact(
            section=self.name,
            entity=self.entity,
            entity_id=pid,
            value=None,
            sub_fields=sub_fields,
            provenance=provenance,
            confidence=confidence,
            as_of=as_of_str,
            cv_fields=self.cv_fields(),
        )

    def validate(self, artifact: AtlasArtifact) -> bool:
        """Face-validity check: required sub-field keys present, values in range.

        Full leak/coverage/dedup gate lives in src.loop.intel_validator.
        """
        if artifact.section != self.name or artifact.entity != self.entity:
            return False

        sf = artifact.sub_fields
        required_keys = {"leading", "tied", "trailing", "pace", "shot_mix"}
        if not required_keys.issubset(sf.keys()):
            return False

        # Check populated state buckets for range validity
        for state in ("leading", "tied", "trailing"):
            bucket = sf.get(state)
            if bucket is None:
                continue  # missing state bucket is OK (player may never trail badly)
            if not isinstance(bucket, dict):
                return False

            # efg_pct must be [0, 1.6] (eFG ceiling rule)
            efg = bucket.get("efg_pct")
            if efg is not None and not (0.0 <= efg <= 1.6):
                return False

            # fg3a_rate must be [0, 1]
            fg3a_rate = bucket.get("fg3a_rate")
            if fg3a_rate is not None and not (0.0 <= fg3a_rate <= 1.0):
                return False

            # Per-game rates must be non-negative
            for key in ("pts_pg", "reb_pg", "ast_pg", "fg3m_pg", "fga_pg", "min_pg"):
                v = bucket.get(key)
                if v is not None and v < 0:
                    return False

            # n_quarters and n_games must be positive integers
            for key in ("n_quarters", "n_games"):
                v = bucket.get(key)
                if v is not None and v < 0:
                    return False

        # CV fields must be declared and all values null (reserved)
        for slot_name, slot in artifact.cv_fields.items():
            if getattr(slot, "value", None) is not None:
                return False

        return True

    def cv_fields(self) -> Dict[str, CVSlot]:
        """Reserved CV-slot schema for score_margin_splits (all values None).

        These slots capture behavioural signatures from CV tracking that are
        orthogonal to box-score stats: whether a player attacks harder under
        deficit or coasts when comfortably ahead.
        """
        return {
            "cv_usage_leading": CVSlot(
                name="cv_usage_leading",
                dtype="float",
                description=(
                    "CV-derived usage rate (possessions used / total team possessions "
                    "when player on court) averaged across quarters where team was "
                    "leading by > 5 pts at quarter start. From CV EventDetector "
                    "possession tagging + homography."
                ),
                unit=None,
                value=None,
            ),
            "cv_usage_trailing": CVSlot(
                name="cv_usage_trailing",
                dtype="float",
                description=(
                    "CV-derived usage rate in quarters where team was trailing by "
                    "> 5 pts at quarter start.  Compared to cv_usage_leading, a large "
                    "positive delta indicates a player who 'takes over' when behind."
                ),
                unit=None,
                value=None,
            ),
            "cv_drive_rate_trailing": CVSlot(
                name="cv_drive_rate_trailing",
                dtype="float",
                description=(
                    "Drive attempts per minute when trailing (score state = trailing), "
                    "from CV EventDetector drive-event detection.  Captures tendency "
                    "to attack the paint under deficit vs pull up for 3s."
                ),
                unit="drives/min",
                value=None,
            ),
        }


# ---------------------------------------------------------------------------
# Module-level registration (called by orchestrator / batch build)
# ---------------------------------------------------------------------------

def build_and_register(
    player_ids: Optional[List[int]] = None,
    as_of: Optional[_dt.datetime] = None,
    *,
    store: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Build score_margin_splits for a list of player_ids and register via the bridge.

    Args:
        player_ids: list of NBA player_ids.  If None, discovers from adv_stats.
        as_of:      leak boundary date (defaults to today UTC midnight).
        store:      PointInTimeStore; when provided, artifacts are written to the store.
        dry_run:    skip all disk writes.

    Returns:
        manifest dict from ``register_section``.
    """
    if as_of is None:
        as_of = _dt.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if player_ids is None:
        # Discover from adv_stats (largest player_id universe)
        path = DATA / "player_adv_stats.parquet"
        if path.exists():
            try:
                adv = pd.read_parquet(path, columns=["player_id"])
                player_ids = (
                    adv["player_id"].dropna().astype(int).unique().tolist()
                )
            except Exception:
                player_ids = []
        else:
            player_ids = []

    section = PlayerScoreMarginSplits()
    artifacts = []
    for pid in player_ids:
        try:
            art = section.build(pid, as_of)
        except Exception:
            art = None
        if art is not None and section.validate(art):
            artifacts.append(art)

    return register_section(section, artifacts, store=store, dry_run=dry_run)
