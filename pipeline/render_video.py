"""
Render tracking overlays onto a video for visual inspection.

Draws on every frame:
  - Bounding boxes (green=player, orange=ball)
  - Track ID label
  - Team label (team_a=blue, team_b=red, ref=gray)
  - Speed (ft/s)
  - Velocity arrow

Output: a new video file you can scrub through.

Usage:
  python -m pipeline.render_video --video game.mp4 --game-id <uuid>
  python -m pipeline.render_video --video game.mp4 --game-id <uuid> --out reviewed.mp4
  python -m pipeline.render_video --video game.mp4 --game-id <uuid> --start 500 --end 1500
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

from tracking.database import get_connection

# Colors: BGR
_TEAM_A  = (219, 100,  45)   # blue
_TEAM_B  = ( 50,  50, 220)   # red
_BALL    = ( 30, 165, 255)   # orange
_REF     = (160, 160, 160)   # gray
_DEFAULT = (180, 180,  50)   # yellow fallback
_WHITE   = (255, 255, 255)
_BLACK   = (  0,   0,   0)


def _team_color(team: str) -> tuple:
    return {
        "team_a": _TEAM_A,
        "team_b": _TEAM_B,
        "ball":   _BALL,
        "ref":    _REF,
    }.get(team or "", _DEFAULT)


def _load_tracks(game_id: str, start_frame: int, end_frame: int) -> dict[int, list[dict]]:
    """Load tracking rows from DB, keyed by frame_number."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT frame_number, track_id, object_type, team,
                       x, y, speed, velocity_x, velocity_y, confidence,
                       bbox_x1, bbox_y1, bbox_x2, bbox_y2
                FROM tracking_coordinates
                WHERE game_id = %s
                  AND frame_number BETWEEN %s AND %s
                ORDER BY frame_number, track_id
                """,
                (game_id, start_frame, end_frame),
            )
            rows = cur.fetchall()

    by_frame: dict[int, list[dict]] = {}
    for r in rows:
        fn, tid, obj_type, team, cx, cy, speed, vx, vy, conf, bx1, by1, bx2, by2 = r
        by_frame.setdefault(fn, []).append({
            "track_id":    tid,
            "object_type": obj_type,
            "team":        team or "",
            "cx":          float(cx or 0),
            "cy":          float(cy or 0),
            "speed":       float(speed or 0),
            "vx":          float(vx or 0),
            "vy":          float(vy or 0),
            "conf":        float(conf or 0),
            "bbox":        (bx1, by1, bx2, by2) if bx1 is not None else None,
        })
    return by_frame


def _draw_frame(frame: np.ndarray, tracks: list[dict]) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]

    for t in tracks:
        cx = int(t["cx"])
        cy = int(t["cy"])
        is_ball = t["object_type"] == "ball"
        color = _team_color(t["team"])

        if is_ball:
            cv2.circle(out, (cx, cy), 12, color, 2)
            cv2.circle(out, (cx, cy),  3, color, -1)
            label = f"ball  {t['speed']:.1f}ft/s"
            _draw_label(out, label, cx, cy - 18, color)
        else:
            # Use stored bbox if available, else estimate
            if t["bbox"] and t["bbox"][0] is not None:
                x1, y1, x2, y2 = (int(v) for v in t["bbox"])
            else:
                bw, bh = 40, 80
                x1, y1 = cx - bw // 2, cy - bh // 2
                x2, y2 = cx + bw // 2, cy + bh // 2

            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

            # Velocity arrow (scaled)
            if abs(t["vx"]) + abs(t["vy"]) > 0.5:
                scale = 2.0
                ax = int(cx + t["vx"] * scale)
                ay = int(cy + t["vy"] * scale)
                cv2.arrowedLine(out, (cx, cy), (ax, ay), color, 2, tipLength=0.3)

            team_label = t["team"] or "?"
            label = f"#{t['track_id']} {team_label}  {t['speed']:.1f}ft/s"
            _draw_label(out, label, x1, y1 - 6, color)

    return out


def _draw_label(img: np.ndarray, text: str, x: int, y: int, color: tuple) -> None:
    font       = cv2.FONT_HERSHEY_SIMPLEX
    scale      = 0.45
    thickness  = 1
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    pad = 2
    # Background pill
    cv2.rectangle(img,
                  (x - pad, y - th - pad),
                  (x + tw + pad, y + pad),
                  _BLACK, -1)
    cv2.putText(img, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def render(
    video_path: str,
    game_id: str,
    out_path: str | None = None,
    start_frame: int = 0,
    end_frame: int | None = None,
) -> str:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    end_frame = end_frame if end_frame is not None else total

    if out_path is None:
        stem = Path(video_path).stem
        out_path = str(Path(video_path).parent / f"{stem}_tracked.mp4")

    writer = cv2.VideoWriter(
        out_path,
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    print(f"[render] Loading tracks from DB (frames {start_frame}–{end_frame})…")
    tracks_by_frame = _load_tracks(game_id, start_frame, end_frame)
    print(f"[render] Loaded {len(tracks_by_frame)} frames with tracking data")

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_num = start_frame
    written   = 0

    print(f"[render] Rendering to {out_path} …")
    while frame_num <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        tracks = tracks_by_frame.get(frame_num, [])
        rendered = _draw_frame(frame, tracks)

        # Frame counter overlay
        cv2.putText(rendered, f"frame {frame_num}  |  {len(tracks)} objects",
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, _WHITE, 1, cv2.LINE_AA)

        writer.write(rendered)
        written   += 1
        frame_num += 1

        if written % 300 == 0:
            print(f"[render]   {written} / {end_frame - start_frame} frames written…")

    cap.release()
    writer.release()
    print(f"[render] Done — {written} frames → {out_path}")
    return out_path


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Render tracking overlays onto video")
    p.add_argument("--video",    required=True,  help="Original video file")
    p.add_argument("--game-id",  required=True,  help="Game UUID from the DB")
    p.add_argument("--out",      default=None,   help="Output path (default: <name>_tracked.mp4 next to input)")
    p.add_argument("--start",    type=int, default=0,    help="First frame to render (default 0)")
    p.add_argument("--end",      type=int, default=None, help="Last frame to render (default: end of video)")
    args = p.parse_args()

    render(args.video, args.game_id, args.out, args.start, args.end)
