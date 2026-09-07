"""G313 construct: the ten-id cap is a FIXED SLOT POOL, not a measurement.

`UnifiedPipeline._build_players` (`src/pipeline/unified_pipeline.py:821`) builds exactly
eleven Player objects -- ids 1-5 "green", 6-10 "white", 0 "referee" -- and the emitted
`player_id` is that slot's id (`unified_pipeline.py:2028`, `"player_id": p.ID`). Both
matchers bound assignment by that pool per team:
`advanced_tracker.py:908`  `slots = [self._slot(p) for p in self.players if p.team == team]`
`advanced_tracker.py:1047` the same list. A detection with no free same-team slot is left
UNMATCHED by the matcher (`:1061-1062` returns it); the terminal loss is `:1604-1609`, which
this construct does not execute. Either way no clip can report more than 10 non-referee ids.

This module drives the REAL `_match_team_bytetrack` on synthetic, well-separated,
unambiguous detections. It reads `src/`; it edits nothing. Nothing here is a measurement
of tracking quality -- lifting the ceiling is not the same as tracking better.
"""
from __future__ import annotations

BOX = 60          # synthetic bbox side, px -- boxes are 200 px apart, so never ambiguous
PITCH = 200


def _detections(per_team: int) -> list[dict]:
    """Well-separated, full-confidence detections: `per_team` green then `per_team` white."""
    out = []
    for row, team in enumerate(("green", "white")):
        for col in range(per_team):
            y1, x1 = 100 + row * PITCH, 100 + col * PITCH
            out.append({"bbox": (y1, x1, y1 + BOX, x1 + BOX), "team": team,
                        "score": 1.0, "crop_bgr": None})
    return out


def run(per_team: int = 8) -> dict:
    """Offer `per_team` detections to each five-slot team pool; report what got ids."""
    from src.pipeline.unified_pipeline import UnifiedPipeline
    from src.tracking.advanced_tracker import AdvancedFeetDetector

    detector = AdvancedFeetDetector.__new__(AdvancedFeetDetector)   # no YOLO, no OSNet
    detector.players = UnifiedPipeline._build_players(None)
    detector._appearances = {}
    detector._appearance_w = 0.25
    detector._color_tracker = None
    detections = _detections(per_team)

    # Seed one Kalman prediction per slot from a distinct detection of that slot's team,
    # so stage-1 IoU is 1.0 and the cost gate cannot be what limits the count.
    detector._kf_pred = {}
    for team in ("green", "white"):
        slots = [i for i, p in enumerate(detector.players) if p.team == team]
        team_dets = [d for d in detections if d["team"] == team]
        for slot, det in zip(slots, team_dets):
            detector._kf_pred[slot] = det["bbox"]

    matched_slots, unmatched = set(), 0
    per_team_matched = {}
    for team in ("green", "white", "referee"):
        matched, _unmatched_slots, unmatched_dets = detector._match_team_bytetrack(
            team, detections)
        per_team_matched[team] = len(matched)
        matched_slots.update(slot for slot, _ in matched)
        unmatched += len(unmatched_dets)

    ids = sorted(detector.players[slot].ID for slot in matched_slots)
    return {"offered": len(detections), "per_team_offered": per_team,
            "slot_pool_size": len(detector.players),
            "per_team_matched": per_team_matched,
            "distinct_ids": len(ids), "ids": ids, "matcher_unmatched": unmatched}


def main() -> None:  # pragma: no cover
    for per_team in (3, 5, 8, 12):
        result = run(per_team)
        print("offered %2d/team -> matched %s, distinct ids %2d %s, matcher-unmatched %2d"
              % (per_team, result["per_team_matched"], result["distinct_ids"],
                 result["ids"], result["matcher_unmatched"]))
    print("slot pool is fixed at unified_pipeline.py:821 -- 5 green + 5 white + 1 referee.")
    print("NOT a quality result: naming the cap is not fixing it, and lifting it is not"
          " tracking better.")


if __name__ == "__main__":  # pragma: no cover
    main()
