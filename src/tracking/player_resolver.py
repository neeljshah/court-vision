"""
player_resolver.py — Tracker slot → real NBA player_id resolver.

Two-step process:
  A. Jersey number OCR: accumulates votes per slot over 300+ frames
     (delegates to JerseyVotingBuffer + read_jersey_number from player_identity.py).
  B. Roster lookup: fetches both teams' rosters from NBA API BoxScoreTraditionalV3
     and maps jersey_number → {player_id, player_name, team_abbrev}.

After 300 frames the resolved player_id can be used to backfill tracking CSV rows.

Public API
----------
    PlayerResolver(game_id, fps)
    .update(frame, slot, team, crop_bgr, frame_idx) -> None
    .get_jersey_number(slot)   -> Optional[int]
    .resolve_player(slot, team) -> Optional[dict]
    .resolution_report()        -> str
    .slot_to_player_id          -> Dict[int, int]     # slot → NBA player_id
    .slot_to_player_name        -> Dict[int, str]     # slot → player name
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# After this many frames, lock in jersey assignments
_WARMUP_FRAMES = 300
# OCR every N frames per slot — lowered 60→10 so jerseys visible <2s still get a vote
# (at 30fps/stride=3 effective rate: 10-frame interval ≈ 0.33s between samples)
_SAMPLE_EVERY  = 10


class PlayerResolver:
    """
    Maps tracker slots (integer IDs 1-10) to real NBA player_ids.

    Workflow:
      1. Call .update() every frame with the player crop.
      2. After _WARMUP_FRAMES, jersey numbers are stable.
      3. .resolve_player() returns the NBA player dict for a slot.

    Args:
        game_id: NBA game ID used to fetch rosters from the API.
        fps:     Video frame rate (not currently used; kept for API consistency).
    """

    def __init__(self, game_id: str, fps: float = 30.0) -> None:
        self.game_id = game_id
        self.fps     = fps

        # slot → Counter of observed jersey numbers (accumulates across frames)
        self._votes: Dict[int, Counter] = {}
        # slot → confirmed (highest-voted) jersey number
        self._jersey: Dict[int, int]    = {}
        # slot → team label ("green" | "white")
        self._slot_team: Dict[int, str] = {}
        # Roster lookup: (jersey_number, team_label) → player dict
        self._roster: Dict[tuple, dict] = {}
        # Resolved maps (populated lazily after warmup)
        self.slot_to_player_id:   Dict[int, int] = {}
        self.slot_to_player_name: Dict[int, str] = {}

        self._roster_loaded = False
        self._warmup_done   = False
        self._frame_count   = 0

    # ── public ────────────────────────────────────────────────────────────────

    def update(
        self,
        slot: int,
        team: str,
        crop_bgr: "Optional[object]",
        frame_idx: int,
    ) -> None:
        """
        Process one player crop for jersey OCR.

        Args:
            slot:      Tracker slot index (1-10).
            team:      Team label ("green" or "white").
            crop_bgr:  BGR numpy array of the player bounding box, or None.
            frame_idx: Absolute video frame index.
        """
        self._slot_team[slot] = team
        self._frame_count     = max(self._frame_count, frame_idx)

        # Only run OCR on every _SAMPLE_EVERY frames and non-empty crops
        if frame_idx % _SAMPLE_EVERY != 0:
            return
        if crop_bgr is None:
            return
        try:
            import numpy as np
            if not isinstance(crop_bgr, np.ndarray) or crop_bgr.size == 0:
                return
        except ImportError:
            return

        try:
            from src.tracking.jersey_ocr import read_jersey_number
            number = read_jersey_number(crop_bgr)
        except Exception as exc:
            log.debug("PlayerResolver OCR failed (slot %d): %s", slot, exc)
            return

        if number is not None:
            self._votes.setdefault(slot, Counter())[number] += 1

    def get_jersey_number(self, slot: int) -> Optional[int]:
        """Return the most-voted jersey number for slot, or None."""
        counter = self._votes.get(slot)
        if not counter:
            return None
        return counter.most_common(1)[0][0]

    def resolve_player(self, slot: int, team: Optional[str] = None) -> Optional[dict]:
        """
        Return NBA player dict for a slot, or None if not yet resolved.

        Triggers roster fetch on first call if not already loaded.

        Returns:
            {"player_id": int, "player_name": str, "team": str, "jersey": int}
            or None.
        """
        jersey = self.get_jersey_number(slot)
        if jersey is None:
            return None

        if not self._roster_loaded:
            self._fetch_roster()

        tm = team or self._slot_team.get(slot, "")
        key = (jersey, tm)
        return self._roster.get(key)

    def finalize(self) -> None:
        """
        Lock in jersey assignments and populate slot_to_player_id / slot_to_player_name.

        Call this once after _WARMUP_FRAMES to backfill tracking data.
        """
        if not self._roster_loaded:
            self._fetch_roster()

        resolved = 0
        for slot in list(self._votes.keys()):
            info = self.resolve_player(slot)
            if info:
                self.slot_to_player_id[slot]   = info["player_id"]
                self.slot_to_player_name[slot] = info["player_name"]
                resolved += 1
        self._warmup_done = True
        log.info("PlayerResolver: %d/%d slots resolved", resolved, len(self._votes))

    @property
    def warmup_complete(self) -> bool:
        """True once enough frames have been processed to attempt resolution."""
        return self._frame_count >= _WARMUP_FRAMES

    def resolution_report(self) -> str:
        """Return a human-readable resolution summary."""
        lines: List[str] = ["PlayerResolver — Jersey OCR Resolution Report"]
        lines.append(f"  frames processed : {self._frame_count}")
        lines.append(f"  slots with votes : {len(self._votes)}")
        lines.append(f"  roster entries   : {len(self._roster)}")
        lines.append("")
        for slot in sorted(self._votes.keys()):
            jersey   = self.get_jersey_number(slot)
            team     = self._slot_team.get(slot, "?")
            pid      = self.slot_to_player_id.get(slot)
            name     = self.slot_to_player_name.get(slot, "?")
            top5     = self._votes[slot].most_common(5)
            lines.append(
                f"  slot {slot:2d} ({team:5s}) → jersey #{jersey} "
                f"pid={pid} name={name!r}  votes={top5}"
            )
        return "\n".join(lines)

    # ── internal ──────────────────────────────────────────────────────────────

    def _fetch_roster(self) -> None:
        """Fetch both teams' rosters from BoxScoreTraditionalV3 and build lookup."""
        self._roster_loaded = True  # set before fetch to prevent re-entry on error
        try:
            self._fetch_roster_api()
        except Exception as exc:
            log.warning("PlayerResolver: roster fetch failed (%s) — identity disabled", exc)

    def _fetch_roster_api(self) -> None:
        """Internal: call NBA Stats API and populate self._roster."""
        try:
            from nba_api.stats.endpoints import boxscoretraditionalv2
        except ImportError:
            log.warning("nba_api not installed — jersey→player_id resolution disabled")
            return

        time.sleep(0.6)  # rate-limit
        try:
            box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=self.game_id)
            df  = box.player_stats.get_data_frame()
        except Exception as exc:
            log.warning("BoxScoreTraditionalV2 fetch failed: %s", exc)
            return

        if df is None or df.empty:
            return

        # Determine which team label (green/white) corresponds to which abbrev.
        # We can't know this without color calibration, so we add both team labels
        # for every player.  The resolver uses both team colors as candidate keys.
        team_abbrevs = df["TEAM_ABBREVIATION"].unique().tolist()
        labels       = ["green", "white"]

        for _, row in df.iterrows():
            try:
                jersey_str = str(row.get("START_POSITION", "") or "")
                # The API doesn't always expose jersey numbers in BoxScore.
                # Try the jersey_number field first, fall back to team-level lookup.
                jersey_raw = row.get("jersey_number") or row.get("JERSEY_NUM") or ""
                jersey_num = int(str(jersey_raw).strip()) if str(jersey_raw).strip().isdigit() else None
                if jersey_num is None:
                    continue

                pid   = int(row["PLAYER_ID"])
                name  = str(row["PLAYER_NAME"])
                abbr  = str(row["TEAM_ABBREVIATION"])

                # Map to both team labels (green/white) since we don't know which
                # team the tracker assigned to which color
                for label in labels:
                    key = (jersey_num, label)
                    self._roster[key] = {
                        "player_id":   pid,
                        "player_name": name,
                        "team":        abbr,
                        "jersey":      jersey_num,
                    }
            except (ValueError, KeyError, TypeError):
                continue

        log.info("PlayerResolver: roster loaded — %d entries", len(self._roster))
        if not self._roster:
            # Fallback: try PlayerGameLog-based approach or print debug info
            log.warning("PlayerResolver: roster empty — jersey column may not be available "
                        "in BoxScoreTraditionalV2 for this game")
