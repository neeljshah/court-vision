"""
backfill_cv_features.py -- Register CV features from existing tracking game directories.

Reads all game directories under data/tracking/ and data/games/, extracts
per-player CV features via tracking_feature_extractor, resolves player_name
-> real NBA player_id using cached player_avgs, then writes to cv_features DB.

Usage:
    conda activate basketball_ai
    python scripts/backfill_cv_features.py
    python scripts/backfill_cv_features.py --dry-run
    python scripts/backfill_cv_features.py --game-id 0022500757
    python scripts/backfill_cv_features.py --roster-strict

Only registers players whose slot names map to a known NBA player_id.
Skips games already registered (idempotent).

Bug 6 fix (2026-05-28): Roster-validation guard added to _resolve_slot_to_nba_id().
After any channel resolves a slot to an nba_id, the id is validated against the
set of players in the actual game boxscore. Cross-team jersey collisions (e.g.
"Moses Moody CHI→GSW" phantom trade) are rejected. Behaviour is fail-soft by
default (missing boxscore = skip guard). Use --roster-strict to make a missing
roster a hard error.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Dict, Optional, Set

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR    = PROJECT_DIR / "data"
TRACKING_DIR = DATA_DIR / "tracking"
GAMES_DIR   = DATA_DIR / "games"
NBA_CACHE   = DATA_DIR / "nba"

# Seasons to look up player -> NBA ID mappings (newest first)
_LOOKUP_SEASONS = ["2025-26", "2024-25", "2023-24"]
# Cache file candidates per season (checked in order)
_CACHE_PATTERNS = ["player_full_{season}.json", "player_avgs_{season}.json"]

# ── Bug 6 roster guard ─────────────────────────────────────────────────────────
# Path for rejection log (created on first write)
_ROSTER_REJECTION_LOG = DATA_DIR / "_wave2" / "roster_rejections.jsonl"

# In-process cache: game_id -> frozenset of eligible nba player_ids
_ROSTER_CACHE: Dict[str, Optional[Set[int]]] = {}

# Global flag — set to True via --roster-strict CLI arg before backfill starts
_ROSTER_STRICT: bool = False


def _get_game_team_rosters(game_id: str) -> Optional[Set[int]]:
    """Return set of nba player_ids eligible to appear in game_id.

    Source: data/nba/boxscore_<game_id>.json  (preferred — has per-player ids)

    Returns:
        frozenset of int player_ids  — non-empty means guard is active
        None                         — no roster data found (fail-soft skip)
    """
    if game_id in _ROSTER_CACHE:
        return _ROSTER_CACHE[game_id]

    boxscore_path = NBA_CACHE / f"boxscore_{game_id}.json"
    if not boxscore_path.exists():
        _ROSTER_CACHE[game_id] = None
        return None

    try:
        with open(boxscore_path, encoding="utf-8") as f:
            bs = json.load(f)
        players = bs.get("players", [])
        ids: Set[int] = set()
        for p in players:
            pid = p.get("player_id")
            if pid:
                ids.add(int(pid))
        if ids:
            _ROSTER_CACHE[game_id] = ids
            return ids
    except Exception:
        pass

    _ROSTER_CACHE[game_id] = None
    return None


def _log_roster_rejection(game_id: str, slot_id: int, nba_id: int, channel: str) -> None:
    """Append one JSONL line to the rejection log file."""
    import time
    _ROSTER_REJECTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "game_id": game_id,
        "slot_id": slot_id,
        "rejected_nba_id": nba_id,
        "channel": channel,
    }
    try:
        with open(_ROSTER_REJECTION_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _build_name_to_id_map() -> Dict[str, int]:
    """Build player_name -> NBA player_id from cached player stats files."""
    result: Dict[str, int] = {}
    for season in _LOOKUP_SEASONS:
        for pattern in _CACHE_PATTERNS:
            cache_path = NBA_CACHE / pattern.format(season=season)
            if not cache_path.exists():
                continue
            try:
                with open(cache_path) as f:
                    cache = json.load(f)
                if isinstance(cache, list):
                    # List format: [{PLAYER_NAME: ..., PLAYER_ID: ...}, ...]
                    for row in cache:
                        name = str(row.get("PLAYER_NAME") or row.get("player_name", ""))
                        pid = row.get("PLAYER_ID") or row.get("player_id")
                        if name and pid:
                            result[_norm(name)] = int(pid)
                elif isinstance(cache, dict):
                    # Dict format: {player_name: {player_id: ..., ...}}
                    for name, data in cache.items():
                        if isinstance(data, dict):
                            pid = data.get("player_id") or data.get("PLAYER_ID")
                        else:
                            pid = None
                        if pid:
                            result[_norm(name)] = int(pid)
            except Exception:
                pass
    return result


def _load_jersey_name_map(game_dir: str) -> Dict[str, str]:
    """
    Load jersey_number -> player_full_name mapping from jersey_name_map.json.

    Supports two formats:
      Legacy flat:   {"2": "Collin Sexton", "34": "Giannis", ...}
      Nested by_team + flat: {"by_team": {...}, "flat": {"2": "Collin Sexton", ...}}

    Audit result: no cross-team jersey collisions exist in the dataset (0%
    collision rate across 252 by_team games), so the pre-built flat map is
    always sufficient. When only by_team is present (legacy), we flatten it.
    """
    jnm_path = os.path.join(game_dir, "jersey_name_map.json")
    try:
        with open(jnm_path, encoding="utf-8", errors="replace") as f:
            jnm = json.load(f)
    except Exception:
        return {}

    if "flat" in jnm and isinstance(jnm["flat"], dict) and jnm["flat"]:
        return {str(k): str(v) for k, v in jnm["flat"].items() if v}
    if "by_team" in jnm:
        flat: Dict[str, str] = {}
        for mapping in jnm["by_team"].values():
            for jnum, pname in mapping.items():
                if pname:
                    flat[str(jnum)] = str(pname)
        return flat
    # Pure flat format (top-level keys are jersey numbers)
    return {str(k): str(v) for k, v in jnm.items() if v and str(k).replace(".", "").isdigit()}


def _build_slot_data_from_tracking(
    game_dir: str,
) -> Dict[int, dict]:
    """
    Read tracking_data.csv and build per-slot:
      - jersey_counter: Counter of jersey_number values seen for this slot
      - team_abbrev_counter: Counter of team_abbrev values for this slot
      - jersey_by_quarter: Dict[quarter(1-4), Counter] — Bug 39 Phase B1 fix

    Quarter is read from scoreboard_period or quarter column when present.
    Falls back to frame-percentile bucketing (frame_idx / max_frame * 4 → [1,4])
    when the column is absent or all-blank.

    Returns {} if tracking_data.csv not found.
    """
    tracking_path = os.path.join(game_dir, "tracking_data.csv")
    if not os.path.exists(tracking_path):
        return {}

    from collections import Counter as _Counter, defaultdict as _defaultdict

    # Bug 39 Phase B1 fix: first pass to find max frame for percentile fallback
    max_frame = 1
    try:
        with open(tracking_path, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                try:
                    f_val = row.get("frame", "") or row.get("frame_idx", "")
                    if f_val and f_val not in ("nan", ""):
                        max_frame = max(max_frame, int(float(f_val)))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    slot_data: Dict[int, dict] = {}
    try:
        with open(tracking_path, newline="", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                try:
                    slot = int(row.get("player_id", 0) or 0)
                    if not slot:
                        continue
                    if slot not in slot_data:
                        slot_data[slot] = {
                            "jersey_counter": _Counter(),
                            "team_abbrev_counter": _Counter(),
                            # Bug 39 Phase B1 fix: per-quarter jersey counters
                            "jersey_by_quarter": _defaultdict(_Counter),
                        }
                    jersey_raw = str(row.get("jersey_number", "")).strip()
                    jersey = None
                    if jersey_raw and jersey_raw not in ("nan", ""):
                        try:
                            jersey = str(int(float(jersey_raw)))
                            if jersey not in ("0", "") or jersey == "0":
                                # jersey 0 is valid (e.g. Russell Westbrook)
                                slot_data[slot]["jersey_counter"][jersey] += 1
                        except (ValueError, TypeError):
                            jersey = None
                    # Bug 39 Phase B1 fix: bucket jersey by quarter
                    if jersey is not None:
                        # Prefer explicit period column; fall back to frame percentile
                        q_raw = (
                            row.get("scoreboard_period", "")
                            or row.get("quarter", "")
                            or ""
                        ).strip()
                        q = None
                        if q_raw and q_raw not in ("nan", ""):
                            try:
                                q_parsed = int(float(q_raw))
                                # Clamp to [1,4]; treat OT (5+) as Q4 for resolver purposes
                                q = max(1, min(4, q_parsed))
                            except (ValueError, TypeError):
                                pass
                        if q is None:
                            # Frame-percentile fallback
                            f_val = row.get("frame", "") or row.get("frame_idx", "")
                            if f_val and f_val not in ("nan", ""):
                                try:
                                    fnum = int(float(f_val))
                                    q = max(1, min(4, int(fnum / max_frame * 4) + 1))
                                except (ValueError, TypeError):
                                    q = 1
                            else:
                                q = 1
                        slot_data[slot]["jersey_by_quarter"][q][jersey] += 1
                    abbrev = str(row.get("team_abbrev", "")).strip()
                    if not abbrev or abbrev in ("nan", ""):
                        abbrev = str(row.get("team", "")).strip()
                    if abbrev and abbrev not in ("nan", ""):
                        slot_data[slot]["team_abbrev_counter"][abbrev] += 1
                except (ValueError, TypeError):
                    pass
    except Exception:
        return {}
    return slot_data


def _build_slot_pbp_names(shot_log_path: str) -> Dict[int, "Counter"]:
    """
    Read shot_log.csv and build per-slot Counter of clean player_name values.
    Excludes names with '#' or '?' characters (OCR failures).
    """
    from collections import Counter as _Counter
    slot_names: Dict[int, _Counter] = {}
    try:
        with open(shot_log_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    slot = int(row.get("player_id", 0) or 0)
                    name = str(row.get("player_name", "")).strip()
                    if slot and name and "?" not in name and "#" not in name and name:
                        slot_names.setdefault(slot, _Counter())[name] += 1
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return slot_names


def _resolve_slot_to_nba_id(
    game_dir: str,
    name_to_id: Dict[str, int],
    slot_id: int,
    jersey_to_name: Dict[str, str],
    slot_data: Dict[int, dict],
    slot_pbp_names: Dict[int, "Counter"],
    suffix_idx: Dict[str, list],
    game_id: str = "",
    quarter: Optional[int] = None,
) -> tuple:
    """
    Resolve a single tracker slot_id to an NBA player_id.

    Channel priority (Bug 2 fix 2026-05-28): PBP fires FIRST when present —
    PBP names are emitted by EventDetector on actual shot events and are far
    more reliable than ambient jersey OCR. Mode-jersey is fallback.

    Tries channels in order:
      1. PBP-resolved player_name from shot_log (most common clean name) -> NBA id
      2. Mode jersey from tracking_data.csv -> jersey_name_map -> NBA id
         (skipped if jersey is contested: mode_jersey_frac < 0.5)
         Bug 39 Phase B1 fix: when quarter is given, uses jersey_by_quarter[slot][quarter]
         instead of the game-wide counter, so each quarter resolves independently.
      3. Last-name suffix match on PBP name (with single-candidate tiebreaker)

    Bug 6 fix (2026-05-28): After each channel resolves an nba_id, it is checked
    against the game's boxscore roster. If the resolved id is not on either team,
    the resolution is rejected and the next channel is tried. This prevents
    cross-team jersey collisions (e.g. same jersey number on two teams) from
    creating phantom trades like "Moses Moody CHI→GSW".

    Roster guard is fail-soft: if no boxscore exists for game_id the guard is
    skipped entirely (all channels behave as before). Set _ROSTER_STRICT=True
    (via --roster-strict flag) to treat missing roster as a hard error.

    Bug 39 Phase B1 fix (2026-05-28): quarter kwarg enables per-quarter resolution.
    When quarter is supplied, Channel 2 draws from jersey_by_quarter[slot_id][quarter]
    instead of the game-wide jersey_counter. Channels 1 and 3 are unchanged.

    Returns (nba_id, channel) where channel is 'pbp'|'jersey'|'suffix'|None.
    """
    # ── Pre-load roster for this game (Bug 6 guard) ────────────────────────────
    eligible_ids: Optional[Set[int]] = None
    if game_id:
        eligible_ids = _get_game_team_rosters(game_id)
        if eligible_ids is None and _ROSTER_STRICT:
            # Hard-fail: no roster data and strict mode active
            return None, None

    def _roster_ok(nba_id: int, channel: str) -> bool:
        """Return True if nba_id passes roster check (or guard is inactive)."""
        if eligible_ids is None:
            return True  # fail-soft: no roster data, skip guard
        if nba_id in eligible_ids:
            return True
        _log_roster_rejection(game_id, slot_id, nba_id, channel)
        return False

    # ── Channel 1 (NEW PRIORITY): PBP mode name (exact) -> NBA id ─────────────
    pbp_norm_name = None
    if slot_id in slot_pbp_names and slot_pbp_names[slot_id]:
        mode_name = slot_pbp_names[slot_id].most_common(1)[0][0]
        pbp_norm_name = _norm(mode_name)
        nba_id = name_to_id.get(pbp_norm_name)
        if nba_id and _roster_ok(nba_id, "pbp"):
            return nba_id, "pbp"

    # ── Channel 2: mode jersey -> jersey_name_map -> NBA id (contest guard) ──
    if jersey_to_name and slot_id in slot_data:
        # Bug 39 Phase B1 fix: use per-quarter counter when quarter is given,
        # fall back to game-wide counter otherwise.
        if quarter is not None:
            jbq = slot_data[slot_id].get("jersey_by_quarter", {})
            jc = jbq.get(quarter, {})
        else:
            jc = slot_data[slot_id].get("jersey_counter", {})
        if jc:
            mode_jersey = max(jc, key=jc.get)
            total_jersey_reads = sum(jc.values())
            mode_jersey_frac = (
                jc[mode_jersey] / total_jersey_reads if total_jersey_reads else 0
            )
            # Skip Channel 2 when the jersey count is contested (Bug 2 fix):
            # frequent OCR collisions between adjacent slots make the plurality
            # vote unreliable below 50%.
            if mode_jersey_frac >= 0.5:
                full_name = jersey_to_name.get(mode_jersey)
                if full_name:
                    nba_id = name_to_id.get(_norm(full_name))
                    if nba_id and _roster_ok(nba_id, "jersey"):
                        return nba_id, "jersey"

    # ── Channel 3: suffix match on PBP last name ──────────────────────────────
    if pbp_norm_name and " " not in pbp_norm_name:
        candidates = suffix_idx.get(pbp_norm_name, [])
        if len(candidates) == 1:
            nba_id = candidates[0][1]
            if _roster_ok(nba_id, "suffix"):
                return nba_id, "suffix"
        elif len(candidates) > 1:
            # Try team_abbrev tiebreaker
            team_abbrev = ""
            if slot_id in slot_data:
                tc = slot_data[slot_id].get("team_abbrev_counter", {})
                if tc:
                    team_abbrev = max(tc, key=tc.get)
            if team_abbrev:
                # We don't store team per player_id so can't do a strict filter.
                # Skip ambiguous suffix matches.
                pass  # fall through to None

    return None, None


def _build_suffix_index(
    name_to_id: Dict[str, int],
) -> Dict[str, list]:
    """
    Build a reverse index: normalized_last_name -> [(normalized_full_name, player_id), ...].

    Used to resolve OCR'd last-name-only entries (e.g. "Antetokounmpo" ->
    "giannis antetokounmpo") when exact full-name match fails.
    """
    suffix_idx: Dict[str, list] = {}
    for norm_name, pid in name_to_id.items():
        parts = norm_name.split()
        if parts:
            last = parts[-1]
            suffix_idx.setdefault(last, []).append((norm_name, pid))
    return suffix_idx


def _resolve_player_names_from_shot_log(
    shot_log_path: str,
    name_to_id: Dict[str, int],
) -> Dict[int, int]:
    """
    Return mapping: tracker_slot_id -> real_nba_player_id.

    Reads player_name column from shot_log.csv and matches against the NBA
    player_id cache.  Matching is attempted in this order:
      1. Exact normalized full-name match (fast path).
      2. Suffix match: OCR name has no spaces → try candidate whose full name
         ends with the OCR'd token.  If multiple candidates share that last
         name, log the collision and skip that slot (too ambiguous without
         jersey data).
      3. Any unresolved slots are logged for later audit.
    """
    slot_to_name: Dict[int, str] = {}
    try:
        with open(shot_log_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    slot = int(row.get("player_id", 0) or 0)
                    name = str(row.get("player_name", "")).strip()
                    if slot and name and "?" not in name and "#" not in name:
                        slot_to_name.setdefault(slot, name)
                except (ValueError, TypeError):
                    pass
    except Exception:
        return {}

    suffix_idx = _build_suffix_index(name_to_id)

    slot_to_nba: Dict[int, int] = {}
    unresolved: list = []

    for slot, name in slot_to_name.items():
        norm = _norm(name)

        # 1. Exact match
        nba_id = name_to_id.get(norm)
        if nba_id:
            slot_to_nba[slot] = nba_id
            continue

        # 2. Suffix match (last-name-only OCR)
        if " " not in norm:
            candidates = suffix_idx.get(norm, [])
            if len(candidates) == 1:
                slot_to_nba[slot] = candidates[0][1]
            elif len(candidates) > 1:
                # Ambiguous — log for audit, skip
                cand_names = [c[0] for c in candidates]
                unresolved.append(
                    f"slot={slot} name={name!r} ambiguous suffix: {cand_names}"
                )
            else:
                unresolved.append(f"slot={slot} name={name!r} no suffix match")
        else:
            unresolved.append(f"slot={slot} name={name!r} no exact match")

    if unresolved:
        import warnings
        warnings.warn(
            f"[backfill_cv] {shot_log_path}: {len(unresolved)} unresolved slots: "
            + "; ".join(unresolved[:5])
            + (" ..." if len(unresolved) > 5 else "")
        )

    return slot_to_nba


def _already_registered(game_id: str) -> bool:
    """Return True if this game_id already has rows in cv_features."""
    try:
        from src.data.db import get_connection
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM cv_features WHERE game_id = ?",
                (game_id,),
            )
            count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def process_game(
    game_id: str,
    game_dir: str,
    name_to_id: Dict[str, int],
    suffix_idx: Dict[str, list],
    dry_run: bool = False,
) -> tuple:
    """
    Extract and register CV features for one game.

    Bug 39 Phase B1 fix (2026-05-28): per-quarter resolution.
    Instead of resolving each slot once per game, resolve each (slot, quarter)
    pair independently. A slot that held player A in Q1 and player B in Q3 now
    produces TWO registrations (one per player) rather than collapsing both into
    the mode-jersey winner.

    Limitation (Phase B1): features are NOT partitioned by quarter — each player
    registered from a shared slot receives the SLOT's full-game feature vector,
    not just their own quarters' signal. A cv_share_factor column (1/n_players
    for that slot) is attached so downstream models can de-weight shared-slot rows.
    Phase B2 will partition features by quarter inside tracking_feature_extractor.
    # Bug 39 Phase B1 fix: quarter-resolution but not yet quarter-aware feature
    # aggregation. Phase B2 will partition features by quarter.

    Uses a unified multi-channel resolver applied PER (SLOT, QUARTER):
      Channel 1: mode jersey from tracking_data -> jersey_name_map -> NBA id
      Channel 2: PBP-resolved player_name mode from shot_log -> NBA id
      Channel 3: last-name suffix match on PBP name (unambiguous only)

    Returns (n_registered, n_jersey, n_pbp, n_suffix, n_unresolved).
    """
    from src.pipeline.tracking_feature_extractor import extract
    from src.pipeline.cv_feature_registry import register

    shot_log = os.path.join(game_dir, "shot_log.csv")
    if not os.path.exists(shot_log):
        return 0, 0, 0, 0, 0

    # Load data for all channels upfront
    jersey_to_name = _load_jersey_name_map(game_dir)
    slot_data = _build_slot_data_from_tracking(game_dir)
    slot_pbp_names = _build_slot_pbp_names(shot_log)

    # Collect all slot IDs seen in either tracking_data or shot_log
    all_slots = set(slot_data.keys()) | set(slot_pbp_names.keys())

    # ── Bug 39 Phase B1 fix: per-quarter resolution ───────────────────────────
    # Build (slot_id, quarter) -> nba_id map.
    # For each slot, try quarters 1-4 with per-quarter jersey counters.
    # If all 4 quarters resolve to the SAME nba_id, collapse to one entry.
    QUARTERS = [1, 2, 3, 4]
    # slot_quarter_to_nba: Dict[(slot_id, quarter), int]
    slot_quarter_to_nba: Dict[tuple, int] = {}
    channel_counts = {"jersey": 0, "pbp": 0, "suffix": 0}
    unresolved_slots = []

    for slot_id in all_slots:
        quarter_results: Dict[int, int] = {}  # quarter -> nba_id
        for q in QUARTERS:
            # Check if this slot has any jersey reads in this quarter
            jbq = slot_data.get(slot_id, {}).get("jersey_by_quarter", {})
            if not jbq.get(q):
                continue  # No jersey data for this slot/quarter — skip
            nba_id, channel = _resolve_slot_to_nba_id(
                game_dir, name_to_id, slot_id,
                jersey_to_name, slot_data, slot_pbp_names, suffix_idx,
                game_id=game_id,
                quarter=q,
            )
            if nba_id:
                quarter_results[q] = nba_id
                channel_counts[channel] += 1

        if not quarter_results:
            unresolved_slots.append(slot_id)
            continue

        # Deduplicate: if all resolved quarters map to the same nba_id, use q=None
        unique_ids = set(quarter_results.values())
        if len(unique_ids) == 1:
            # No substitution detected — register once (backwards-compatible)
            slot_quarter_to_nba[(slot_id, None)] = unique_ids.pop()
        else:
            # Substitution(s) detected — register once per distinct nba_id
            for q, nba_id in quarter_results.items():
                slot_quarter_to_nba[(slot_id, q)] = nba_id

    if not slot_quarter_to_nba:
        return 0, 0, 0, 0, len(unresolved_slots)

    # ── Compute cv_share_factor per slot ──────────────────────────────────────
    # Count how many distinct nba_ids share each slot.
    from collections import Counter as _Counter
    slot_player_count: Dict[int, int] = _Counter()
    for (slot_id, q), nba_id in slot_quarter_to_nba.items():
        slot_player_count[slot_id] += 1  # count (slot, quarter) entries per slot
    # Normalize: slots with only 1 entry (None quarter) get share_factor=1.0
    # Slots with N entries get share_factor=1/N (features are unpartitioned)

    # Extract CV features keyed by slot_id.
    parent_of_game_dir = os.path.dirname(game_dir)
    if os.path.basename(parent_of_game_dir) == "tracking":
        data_root = str(os.path.dirname(parent_of_game_dir))
    else:
        project_data = str(os.path.dirname(parent_of_game_dir))
        tracking_mirror = os.path.join(project_data, "tracking", game_id)
        if os.path.isdir(tracking_mirror):
            data_root = project_data
        else:
            data_root = project_data

    cv_by_slot = extract(game_id, data_root=data_root)
    if not cv_by_slot:
        cv_by_slot = extract(game_id)

    if not cv_by_slot:
        return 0, 0, 0, 0, len(unresolved_slots)

    registered = 0
    ghost_skipped = 0
    sparse_skipped = 0
    # Track which nba_ids have already been registered for this game (dedup)
    registered_nba_ids: set = set()

    for (slot_id, q), nba_id in slot_quarter_to_nba.items():
        feats = cv_by_slot.get(slot_id) or cv_by_slot.get(str(slot_id))
        if not feats:
            continue
        # Bug 2 fix 2026-05-28: skip pure-ghost slots (touches=0 AND n_shots=0).
        # An OSNet boundary artifact that absorbed jersey OCR noise — registering
        # it under a star player's nba_id corrupts cv_features.
        if feats.get("touches_per_game", 0) == 0 and feats.get("n_shots_tracked", 0) == 0:
            ghost_skipped += 1
            continue
        # Bug 36 fix 2026-05-28: generalize the ghost-skip. Reject any slot that
        # produces fewer than 3 non-zero features — these are not OSNet boundary
        # artifacts (they pass touches OR shots gate) but they have no other
        # measurable behavioral signal (no shot zones, no fatigue, no spacing).
        # Registering them adds 169 rows of 14% EAV noise that silently corrupts
        # downstream aggregations and inflates ghost counts in audits.
        # cv_archetype is excluded from the count (assigned post-registration).
        nonzero_real = sum(
            1 for k, v in feats.items()
            if v not in (None, 0, 0.0) and k != "cv_archetype"
        )
        if nonzero_real < 3:
            sparse_skipped += 1
            continue
        # Dedup: don't register the same nba_id twice for a game
        # (can happen if two quarters resolve to same player from different slots)
        if nba_id in registered_nba_ids:
            continue
        registered_nba_ids.add(nba_id)
        # Bug 39 Phase B1 fix: attach cv_share_factor.
        # 1.0 = slot held one player all game; 0.5 = slot held 2 players, etc.
        n_sharing = slot_player_count.get(slot_id, 1)
        share_factor = round(1.0 / n_sharing, 4) if n_sharing > 0 else 1.0
        feats_with_share = dict(feats)
        feats_with_share["cv_share_factor"] = share_factor
        if not dry_run:
            register(player_id=nba_id, game_id=game_id, features=feats_with_share)
        registered += 1

    return (
        registered,
        channel_counts["jersey"],
        channel_counts["pbp"],
        channel_counts["suffix"],
        len(unresolved_slots),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing")
    parser.add_argument("--game-id", help="Process only this game ID")
    parser.add_argument("--force", action="store_true",
                        help="Re-process games already in DB (overwrite)")
    parser.add_argument(
        "--roster-strict",
        action="store_true",
        help=(
            "Bug 6 guard: treat missing boxscore roster as a hard error (reject all "
            "resolutions for that game). Default is fail-soft (skip guard when no "
            "boxscore file is found)."
        ),
    )
    args = parser.parse_args()

    # Propagate roster-strict flag to module-level guard
    global _ROSTER_STRICT
    _ROSTER_STRICT = args.roster_strict
    if _ROSTER_STRICT:
        print("[roster-guard] STRICT mode enabled — games without boxscores will reject all slots")

    name_to_id = _build_name_to_id_map()
    suffix_idx = _build_suffix_index(name_to_id)
    print(f"Player name->ID map: {len(name_to_id)} entries loaded")

    # Collect all game directories
    dirs_to_check: list[tuple[str, str]] = []  # (game_id, game_dir_path)
    for base_dir in (TRACKING_DIR, GAMES_DIR):
        if not base_dir.exists():
            continue
        for d in sorted(base_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            gid = d.name
            if args.game_id and gid != args.game_id:
                continue
            dirs_to_check.append((gid, str(d)))

    print(f"Found {len(dirs_to_check)} game directories to check")

    total_registered = 0
    skipped_already = 0
    skipped_no_names = 0
    total_jersey = 0
    total_pbp = 0
    total_suffix = 0

    for game_id, game_dir in dirs_to_check:
        if not args.dry_run and not args.force and _already_registered(game_id):
            skipped_already += 1
            continue

        shot_log = os.path.join(game_dir, "shot_log.csv")
        if not os.path.exists(shot_log):
            continue

        result = process_game(game_id, game_dir, name_to_id, suffix_idx, dry_run=args.dry_run)
        n, n_jersey, n_pbp, n_suffix, n_unresolved = result
        if n == 0:
            skipped_no_names += 1
            if args.dry_run:
                print(f"  {game_id}: no resolvable player names -> skip")
        else:
            total_registered += n
            total_jersey += n_jersey
            total_pbp += n_pbp
            total_suffix += n_suffix
            status = "[DRY RUN]" if args.dry_run else "registered"
            print(
                f"  {game_id}: resolved {n} slots "
                f"({n_jersey} via jersey, {n_pbp} via PBP, {n_suffix} via suffix) {status}"
            )

    print(f"\nDone: {total_registered} player-game records registered, "
          f"{skipped_already} already in DB, {skipped_no_names} skipped (no name match)")
    print(f"Channel breakdown: jersey={total_jersey}, PBP={total_pbp}, suffix={total_suffix}")


if __name__ == "__main__":
    main()
