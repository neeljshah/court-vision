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
from collections import Counter, deque
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# After this many frames, lock in jersey assignments
_WARMUP_FRAMES = 300
# OCR every N frames per slot (every 15 frames ≈ 0.5s at stride=3/30fps)
_SAMPLE_EVERY       = 15
# Confidence-weighted majority vote: keep the last N OCR samples per slot
_CONF_VOTE_WINDOW   = 60  # last 60 OCR samples ≈ 30s of gameplay at 2 samples/s
# Fix B: minimum fraction of total confidence-weight that the dominant candidate
# must hold before we accept it.  If the OCR is reading random noise the weight
# is spread across 5-14 different values → dominant fraction ~10-20%.  A real
# jersey number should dominate ≥50% of the accumulated confidence weight.
_MIN_DOMINANT_FRACTION = 0.50


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

    def __init__(self, game_id: str, fps: float = 30.0, data_dir: str = None) -> None:
        self.game_id = game_id
        self.fps     = fps
        self._data_dir = data_dir  # for jersey_name_map.json save/load

        # slot → Counter of observed jersey numbers (accumulates across frames, legacy)
        self._votes: Dict[int, Counter] = {}
        # slot → deque of (number, confidence) for the last _CONF_VOTE_WINDOW OCR samples
        # Used for confidence-weighted majority vote (replaces simple Counter).
        self._conf_bufs: Dict[int, deque] = {}
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
        # Fix D: learned mapping of team abbreviation → colour label ("green"/"white").
        # Populated lazily from high-confidence slot resolutions (jersey # unique to
        # one team abbrev, slot has a stable colour label).  Once two abbrevs are
        # mapped (one per colour), the guard blocks cross-team name assignments.
        self._abbrev_to_colour: Dict[str, str] = {}

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
        # Increment relative counter (absolute frame_idx starts far above _WARMUP_FRAMES
        # for full-game videos, causing finalize() to fire before any OCR votes accumulate)
        self._frame_count += 1

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
            from src.tracking.jersey_ocr import read_jersey_number_with_conf
            result = read_jersey_number_with_conf(crop_bgr, slot=slot, frame_idx=frame_idx)
        except Exception as exc:
            log.debug("PlayerResolver OCR failed (slot %d): %s", slot, exc)
            return

        if result is not None:
            number, conf = result
            # Legacy counter for backward-compat callers
            self._votes.setdefault(slot, Counter())[number] += 1
            # Confidence-weighted buffer: newest samples replace oldest after window size
            buf = self._conf_bufs.get(slot)
            if buf is None:
                buf = deque(maxlen=_CONF_VOTE_WINDOW)
                self._conf_bufs[slot] = buf
            buf.append((number, float(conf)))

    def get_jersey_number(self, slot: int) -> Optional[int]:
        """Return the confidence-weighted majority-vote jersey number for slot, or None.

        Sums OCR confidence scores across the last _CONF_VOTE_WINDOW samples per slot
        so high-confidence reads outweigh uncertain ones.  Returns None (instead of
        the highest-weighted candidate) when the dominant candidate holds less than
        _MIN_DOMINANT_FRACTION of the total weight — this rejects noisy reads where
        confidence is spread across 5-14 different jersey values (audit: 17-35%
        dominant rate = random noise).  Falls back to plain vote count (legacy
        Counter) when the confidence buffer is empty.
        """
        buf = self._conf_bufs.get(slot)
        if buf:
            # Accumulate weighted score per candidate number
            weighted: Dict[int, float] = {}
            for num, conf in buf:
                weighted[num] = weighted.get(num, 0.0) + conf
            total = sum(weighted.values())
            if total <= 0:
                return None
            best = max(weighted, key=lambda n: weighted[n])
            # Fix B: reject if dominant candidate does not own ≥ MIN_DOMINANT_FRACTION
            # of total confidence weight.  Noisy OCR spreads weight; a real jersey
            # number should be a clear winner.
            if weighted[best] / total < _MIN_DOMINANT_FRACTION:
                return None
            return best
        # Fallback: legacy unweighted counter
        counter = self._votes.get(slot)
        if not counter:
            return None
        total_votes = sum(counter.values())
        top, top_count = counter.most_common(1)[0]
        if total_votes > 0 and top_count / total_votes < _MIN_DOMINANT_FRACTION:
            return None
        return top

    def resolve_player(self, slot: int, team: Optional[str] = None) -> Optional[dict]:
        """
        Return NBA player dict for a slot, or None if not yet resolved.

        Triggers roster fetch on first call if not already loaded.

        Fix D — team-colour guard: after resolving a jersey number to a player
        dict, check that the player's team abbreviation is consistent with the
        slot's colour label ("green"/"white").  The guard learns which abbreviation
        belongs to which colour from the first unambiguous resolutions and then
        rejects candidates that cross teams (audit 2026-05-26: 4/10 pids had
        cross-team name assignments).

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
        info = self._roster.get(key)
        if info is None:
            return None

        # Fix D: team-colour guard.
        # When the roster was fetched without jersey-number data (fallback json),
        # info["team"] may be empty — skip the guard in that case.
        abbr = info.get("team", "")
        if abbr and tm:
            # Learn the abbrev→colour mapping on the fly from unambiguous slots.
            # A slot is unambiguous when its jersey vote passes the dominant-fraction
            # gate AND the roster has exactly one abbrev for that jersey (no cross-
            # team collision).  Store in _abbrev_to_colour both ways.
            if abbr not in self._abbrev_to_colour:
                # Count how many distinct abbrevs own this jersey across the whole
                # roster (it should be exactly 1; jersey numbers unique per team).
                other_abbrevs = {
                    v["team"] for (jn, _), v in self._roster.items()
                    if jn == jersey and v.get("team") and v["team"] != abbr
                }
                if not other_abbrevs:
                    # Unambiguous: this jersey belongs only to `abbr` → learn colour.
                    self._abbrev_to_colour[abbr] = tm
                    log.debug(
                        "PlayerResolver: learned %s → colour=%s from slot %d jersey #%d",
                        abbr, tm, slot, jersey,
                    )

            # Apply the guard only once we have learned mappings for BOTH colours.
            green_abbrevs = {a for a, c in self._abbrev_to_colour.items() if c == "green"}
            white_abbrevs = {a for a, c in self._abbrev_to_colour.items() if c == "white"}
            if green_abbrevs and white_abbrevs:
                # Both sides known — enforce strict colour match.
                expected_colour = self._abbrev_to_colour.get(abbr)
                if expected_colour is not None and expected_colour != tm:
                    log.debug(
                        "resolve_player: slot %d jersey #%d → %s abbr=%s REJECTED "
                        "(team colour guard: abbr=%s is %s but slot is %s)",
                        slot, jersey, info.get("player_name"), abbr,
                        abbr, expected_colour, tm,
                    )
                    return None
        return info

    def finalize(self) -> None:
        """
        Lock in jersey assignments and populate slot_to_player_id / slot_to_player_name.

        Call this once after _WARMUP_FRAMES to backfill tracking data.
        """
        if not self._roster_loaded:
            self._fetch_roster()

        resolved = 0
        # ISSUE-057: iterate ALL seen slots (not just those with OCR votes)
        all_slots = sorted(set(self._slot_team.keys()) | set(self._votes.keys()))
        for slot in all_slots:
            info = self.resolve_player(slot)
            if info:
                self.slot_to_player_id[slot]   = info["player_id"]
                self.slot_to_player_name[slot] = info["player_name"]
                resolved += 1
            elif slot in self.slot_to_player_name and self.slot_to_player_name[slot]:
                pass  # already resolved from a previous finalize() call
            else:
                # Fallback: write team placeholder so column is never blank
                team_lbl = self._slot_team.get(slot, "")
                # Try to find abbrev from roster keys
                abbrevs = {v.get("team", "") for v in self._roster.values() if v}
                team_str = team_lbl if not abbrevs else (
                    next((a for a in abbrevs if team_lbl and a), team_lbl) or team_lbl
                )
                self.slot_to_player_name[slot] = f"{team_str}#?" if team_str else "?#?"
        self._warmup_done = True
        log.info("PlayerResolver: %d/%d slots resolved (of %d tracked)", resolved, len(all_slots), len(all_slots))

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
        """Fetch both teams' rosters from NBA API and build lookup.

        On success, saves jersey_name_map.json to data_dir for future fallback.
        On failure, loads jersey_name_map.json if available.
        """
        self._roster_loaded = True  # set before fetch to prevent re-entry on error
        try:
            self._fetch_roster_api()
        except Exception as exc:
            log.warning("PlayerResolver: roster fetch failed (%s)", exc)

        if self._roster:
            self._save_jersey_name_map()
        else:
            self._load_jersey_name_map()

    def _save_jersey_name_map(self) -> None:
        """Persist jersey→name mapping for offline fallback."""
        if not self._data_dir:
            return
        import json, os
        jmap: Dict[str, str] = {}
        seen = set()
        for (jersey_num, _label), info in self._roster.items():
            key = str(jersey_num)
            if key not in seen:
                jmap[key] = info["player_name"]
                seen.add(key)
        path = os.path.join(self._data_dir, "jersey_name_map.json")
        try:
            os.makedirs(self._data_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(jmap, f, indent=2, ensure_ascii=False)
            log.info("PlayerResolver: saved jersey_name_map.json (%d entries)", len(jmap))
        except Exception as exc:
            log.warning("PlayerResolver: jersey_name_map.json save failed: %s", exc)

    def _load_jersey_name_map(self) -> None:
        """Load jersey_name_map.json as fallback when API fails."""
        if not self._data_dir:
            return
        import json, os
        path = os.path.join(self._data_dir, "jersey_name_map.json")
        if not os.path.exists(path):
            log.warning("PlayerResolver: no jersey_name_map.json fallback at %s", path)
            return
        try:
            with open(path, encoding="utf-8") as f:
                jmap = json.load(f)
            for jersey_str, name in jmap.items():
                try:
                    jersey_num = int(jersey_str)
                except (ValueError, TypeError):
                    continue
                for label in ("green", "white"):
                    key = (jersey_num, label)
                    if key not in self._roster:
                        self._roster[key] = {
                            "player_id": 0,
                            "player_name": name,
                            "team": "",
                            "jersey": jersey_num,
                        }
            log.info("PlayerResolver: loaded jersey_name_map.json fallback (%d entries)", len(jmap))
        except Exception as exc:
            log.warning("PlayerResolver: jersey_name_map.json load failed: %s", exc)

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

        labels = ["green", "white"]

        for _, row in df.iterrows():
            try:
                # BoxScoreTraditionalV2 rarely includes jersey numbers — try both known field names
                jersey_raw = row.get("jersey_number") or row.get("JERSEY_NUM") or ""
                jersey_num = int(str(jersey_raw).strip()) if str(jersey_raw).strip().isdigit() else None
                if jersey_num is None:
                    continue

                pid  = int(row["PLAYER_ID"])
                name = str(row["PLAYER_NAME"])
                abbr = str(row["TEAM_ABBREVIATION"])

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

        log.info("PlayerResolver: BoxScore roster loaded — %d entries", len(self._roster))

        # Fallback: BoxScoreTraditionalV2 rarely has jersey numbers.
        # Use CommonTeamRoster for each team — it always has the NUM column.
        if not self._roster:
            log.info("PlayerResolver: BoxScore had no jersey data — trying CommonTeamRoster")
            self._fetch_roster_common_team(df)

    def _fetch_roster_common_team(self, box_df) -> None:
        """Fallback: fetch jersey numbers from CommonTeamRoster for each team in the game."""
        try:
            from nba_api.stats.endpoints import commonteamroster
        except ImportError:
            return

        labels = ["green", "white"]
        team_ids = box_df["TEAM_ID"].unique().tolist() if "TEAM_ID" in box_df.columns else []
        for team_id in team_ids:
            time.sleep(0.6)
            try:
                roster_ep = commonteamroster.CommonTeamRoster(team_id=int(team_id))
                rdf = roster_ep.common_team_roster.get_data_frame()
            except Exception as exc:
                log.warning("CommonTeamRoster fetch failed for team %s: %s", team_id, exc)
                continue

            if rdf is None or rdf.empty:
                continue

            # CommonTeamRoster has NUM (jersey number), PLAYER (name), TeamID, PLAYER_ID
            abbr_rows = box_df[box_df["TEAM_ID"] == team_id]["TEAM_ABBREVIATION"]
            abbr = str(abbr_rows.iloc[0]) if not abbr_rows.empty else ""

            for _, row in rdf.iterrows():
                try:
                    jersey_raw = str(row.get("NUM", "") or "").strip()
                    jersey_num = int(jersey_raw) if jersey_raw.isdigit() else None
                    if jersey_num is None:
                        continue
                    pid  = int(row["PLAYER_ID"])
                    name = str(row["PLAYER"])
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

        log.info("PlayerResolver: CommonTeamRoster fallback loaded — %d entries", len(self._roster))
        if not self._roster:
            log.warning("PlayerResolver: roster still empty after CommonTeamRoster fallback")
