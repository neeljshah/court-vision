"""Quality gate: score processed games into CLEAN/PARTIAL/REJECT tiers."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

TRACKING_ROOT = Path(__file__).parents[2] / "data" / "tracking"

# Thresholds for CLEAN tier
CLEAN_BALL_PCT   = 40.0
CLEAN_HOMO_PCT   = 99.9   # coord-sanity %: tight bound — a healthy homography
                          # has ~100% in-bound ball projections. Sub-1% out of
                          # range = material corruption (e.g. 0022500047
                          # showed 99.83% = ball coords up to 3.3M px on bad
                          # frames). Single-frame outliers stay ≥99.99%.
CLEAN_CONTINUITY = 0.6
CLEAN_EVENTS_MIN = 50
CLEAN_EVENTS_MAX = 400
# Court-space coordinate bounds (pano is 3698px wide; 6000 is a safe ceiling).
_COORD_MIN = -100.0
_COORD_MAX = 6000.0

Tier = str   # "CLEAN" | "PARTIAL" | "REJECT"


def _load_tracking(game_id: str, tracking_root: Optional[Path] = None) -> Optional[Dict]:
    """Return metrics dict from tracking CSVs, or None if missing."""
    root = (tracking_root or TRACKING_ROOT) / game_id
    td = root / "tracking_data.csv"
    bt = root / "ball_tracking.csv"
    sl = root / "shot_log.csv"

    if not td.exists():
        return None

    try:
        import csv

        with td.open() as fh:
            rows = list(csv.DictReader(fh))
        total = len(rows)
        if total == 0:
            return {"ball_valid_pct": 0.0, "homography_valid_pct": 0.0,
                    "player_track_continuity": 0.0, "event_count": 0, "total_rows": 0}

        # homography_valid_pct is now computed below from BALL COORDINATE SANITY,
        # not from a column. Previous version read tracking_data.csv["homography_valid"]
        # which never existed → metric was silently always 0 and the gate could
        # never tier any game as CLEAN. The replacement catches the verified
        # failure mode: near-singular M/M1 projects the ball to million-px values.

        # Continuity: fraction of rows where player kept same ID vs total possible switches
        id_switches = 0
        prev_ids: dict = {}
        for r in rows:
            pid = r.get("player_id", "")
            team = r.get("team", "")
            key = (team, r.get("frame", ""))
            prev_ids[key] = pid
        # Simple proxy: fraction of frames with ≥1 player tracked
        frames_with_players = len({r.get("frame", "") for r in rows})
        all_frames = max(int(rows[-1].get("frame", 1)), 1) if rows else 1
        continuity = min(1.0, frames_with_players / max(all_frames / 30, 1))

        # Ball tracking + homography-corruption proxy.
        # A near-singular M/M1 explodes the ball perspective division to garbage
        # (millions of px). Out-of-range ball_x2d/y2d is a direct signal that the
        # frame's homography is broken — even though the ball was detected in
        # the image. Counts each ball row toward homography sanity (parse fail
        # also counts as insane).
        ball_valid = 0
        homo_sane = 0
        homo_total = 0
        if bt.exists():
            with bt.open() as fh:
                brows = list(csv.DictReader(fh))
            for r in brows:
                if str(r.get("detected", "")).strip() == "1":
                    ball_valid += 1
                homo_total += 1
                try:
                    bx = float(r.get("ball_x2d") or 0.0)
                    by = float(r.get("ball_y2d") or 0.0)
                    if (_COORD_MIN <= bx < _COORD_MAX
                            and _COORD_MIN <= by < _COORD_MAX
                            and bx == bx and by == by):  # NaN check
                        homo_sane += 1
                except (ValueError, TypeError):
                    pass  # unparseable → counts against sanity
            ball_total = len(brows) or 1
            ball_pct = 100.0 * ball_valid / ball_total
        else:
            ball_pct = 0.0
        homo_pct = 100.0 * homo_sane / max(homo_total, 1)

        # Event count (shots)
        event_count = 0
        if sl.exists():
            with sl.open() as fh:
                event_count = sum(1 for _ in csv.DictReader(fh))

        return {
            "ball_valid_pct": round(ball_pct, 1),
            "homography_valid_pct": round(homo_pct, 2),
            "player_track_continuity": round(continuity, 3),
            "event_count": event_count,
            "total_rows": total,
        }

    except Exception as exc:
        logger.warning("quality: error reading tracking for %s: %s", game_id, exc)
        return None


def _passes(metrics: Dict) -> Tuple[bool, bool, bool, bool]:
    """Return (ball_ok, homo_ok, cont_ok, events_ok)."""
    return (
        metrics["ball_valid_pct"]        >= CLEAN_BALL_PCT,
        metrics["homography_valid_pct"]  >= CLEAN_HOMO_PCT,
        metrics["player_track_continuity"] >= CLEAN_CONTINUITY,
        CLEAN_EVENTS_MIN <= metrics["event_count"] <= CLEAN_EVENTS_MAX,
    )


def score(game_id: str, tracking_root: Optional[Path] = None) -> Tuple[Tier, Optional[str], Dict]:
    """
    Score a processed game.
    Returns (tier, reject_reason, metrics).
    tier: "CLEAN" | "PARTIAL" | "REJECT"
    """
    metrics = _load_tracking(game_id, tracking_root)
    if metrics is None:
        return "REJECT", "no_tracking_output", {}

    checks = _passes(metrics)
    passed = sum(checks)

    if passed == 4:
        tier = "CLEAN"
        reason = None
    elif passed >= 2:
        tier = "PARTIAL"
        labels = ["ball", "homography", "continuity", "events"]
        failed = [labels[i] for i, ok in enumerate(checks) if not ok]
        reason = f"partial: failed={','.join(failed)}"
    else:
        tier = "REJECT"
        labels = ["ball", "homography", "continuity", "events"]
        failed = [labels[i] for i, ok in enumerate(checks) if not ok]
        reason = f"reject: failed={','.join(failed)}"

    return tier, reason, metrics
