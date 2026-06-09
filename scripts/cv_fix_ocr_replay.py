"""
cv_fix_ocr_replay.py — Fast IDENTITY-layer replay harness.

Re-runs ONLY the jersey-OCR → slot → player resolution against a completed
tracking_data.csv + the source video, WITHOUT re-running YOLO/homography/tracking.
Lets us iterate OCR params + the PlayerResolver finalize logic in minutes instead
of a 40-min full pipeline run.

Usage:
    python scripts/cv_fix_ocr_replay.py <game_id> [--video PATH] [--sample N] [--maxframes M]

Outputs a diagnostic report:
  - per-slot raw jersey vote Counter (reveals 10-slot collapse: votes spread = collapsed)
  - per-slot dominant fraction
  - resolved slot -> player name / nba_id
  - whether each named star (esp. Wembanyama #1 SAS) appears in any slot's votes
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from src.tracking.player_resolver import PlayerResolver  # noqa: E402

PROD_PATH = False


def load_tracking_rows(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            try:
                fr = int(float(r["frame"]))
                pid = int(float(r["player_id"]))
            except (ValueError, KeyError):
                continue
            bb = (r.get("bbox_x1"), r.get("bbox_y1"), r.get("bbox_x2"), r.get("bbox_y2"))
            if any(v in (None, "") for v in bb):
                continue
            try:
                x1, y1, x2, y2 = [int(float(v)) for v in bb]
            except ValueError:
                continue
            rows.append({
                "frame": fr, "slot": pid, "team": r.get("team", ""),
                "team_abbrev": r.get("team_abbrev", ""),
                "bbox": (x1, y1, x2, y2),
            })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id")
    ap.add_argument("--video", default=None)
    ap.add_argument("--sample", type=int, default=10, help="use every Nth distinct tracked frame")
    ap.add_argument("--maxframes", type=int, default=2500, help="cap frames OCR'd")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--production-path", action="store_true",
                    help="use resolver.update() (skip-cache + sample gating) like the real pipeline")
    args = ap.parse_args()
    global PROD_PATH
    PROD_PATH = args.production_path

    gid = args.game_id
    data_dir = args.data_dir or f"data/tracking/{gid}"
    video = args.video or f"/root/nba_videos/{gid}.mp4"
    track_csv = os.path.join(data_dir, "tracking_data.csv")

    print(f"[replay] game={gid}")
    print(f"[replay] video={video}  exists={os.path.exists(video)}")
    print(f"[replay] tracking={track_csv}  exists={os.path.exists(track_csv)}")

    rows = load_tracking_rows(track_csv)
    by_frame = defaultdict(list)
    for r in rows:
        by_frame[r["frame"]].append(r)
    frames_sorted = sorted(by_frame.keys())
    sampled = frames_sorted[:: args.sample][: args.maxframes]
    print(f"[replay] tracked rows={len(rows)} distinct frames={len(frames_sorted)} "
          f"sampled={len(sampled)} (every {args.sample}th)")

    # team label per slot = modal 'team' colour across the game
    slot_team_votes = defaultdict(Counter)
    for r in rows:
        slot_team_votes[r["slot"]][r["team"]] += 1
    slot_team = {s: c.most_common(1)[0][0] for s, c in slot_team_votes.items()}

    resolver = PlayerResolver(game_id=gid, fps=30.0, data_dir=data_dir)
    # Record EVERY raw OCR read so we can iterate resolution logic offline (no re-OCR).
    from src.tracking.jersey_ocr import read_jersey_number_with_conf
    all_reads = []  # (slot, team_color, jersey_num, conf, crop_h, crop_w)

    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        print("[replay] ERROR cannot open video")
        return
    total_v = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[replay] video frames={total_v}")

    t0 = time.time()
    ocr_calls = 0
    for i, fr in enumerate(sampled):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fr)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        fh, fw = frame.shape[:2]
        for r in by_frame[fr]:
            x1, y1, x2, y2 = r["bbox"]
            x1 = max(0, min(fw - 1, x1)); x2 = max(0, min(fw, x2))
            y1 = max(0, min(fh - 1, y1)); y2 = max(0, min(fh, y2))
            if x2 <= x1 or y2 <= y1:
                continue
            crop = frame[y1:y2, x1:x2]
            ch, cw = crop.shape[:2]
            slot = r["slot"]; tcol = slot_team.get(slot, r["team"])
            ocr_calls += 1
            if PROD_PATH:
                # Replicate production exactly: resolver.update() with real frame_idx,
                # which applies _SAMPLE_EVERY gating + the 30-frame skip-cache.
                resolver.update(slot=slot, team=tcol, crop_bgr=crop, frame_idx=fr)
                continue
            resolver._slot_team[slot] = tcol
            resolver._frame_count += 1
            # Single OCR call (no skip-cache so every appearance is read independently)
            res = read_jersey_number_with_conf(crop)
            if res is not None:
                num, conf = int(res[0]), float(res[1])
                resolver._votes.setdefault(slot, Counter())[num] += 1
                from collections import deque as _dq
                buf = resolver._conf_bufs.get(slot)
                if buf is None:
                    buf = _dq(maxlen=10_000)  # unbounded for offline tuning
                    resolver._conf_bufs[slot] = buf
                buf.append((num, conf))
                all_reads.append([slot, tcol, num, round(conf, 3), ch, cw])
        if i % 200 == 0 and i:
            print(f"[replay] {i}/{len(sampled)} frames  {time.time()-t0:.0f}s  ocr_feeds={ocr_calls}")
    cap.release()
    dt = time.time() - t0
    print(f"[replay] OCR replay done in {dt:.0f}s  feeds={ocr_calls}")

    # Dump raw reads + roster for offline resolution-logic tuning (no re-OCR needed)
    roster_dump = {f"{jn}|{lbl}": {"name": info["player_name"], "pid": info["player_id"],
                                   "team": info.get("team", "")}
                   for (jn, lbl), info in resolver._roster.items()}
    dump = {"game_id": gid, "slot_team": slot_team, "reads": all_reads, "roster": roster_dump}
    dump_path = os.path.join(data_dir, "ocr_raw_reads.json")
    with open(dump_path, "w") as f:
        json.dump(dump, f)
    print(f"[replay] dumped {len(all_reads)} raw reads -> {dump_path}")

    # Force full-game finalize (the fix we're validating)
    resolver._warmup_done = False
    resolver.finalize()

    # ---- DIAGNOSTIC REPORT ----
    print("\n===== PER-SLOT VOTE DIAGNOSTIC =====")
    star_jerseys = {}  # name -> jersey, for the resolved roster
    for (jn, lbl), info in resolver._roster.items():
        star_jerseys[info["player_name"]] = jn
    all_slots = sorted(set(slot_team.keys()))
    resolved_real = 0
    for s in all_slots:
        votes = resolver._votes.get(s, Counter())
        top = votes.most_common(5)
        tot = sum(votes.values())
        domfrac = (top[0][1] / tot) if tot else 0.0
        jn = resolver.get_jersey_number(s)
        name = resolver.slot_to_player_name.get(s, "?")
        pid = resolver.slot_to_player_id.get(s, "")
        is_real = name and "#?" not in str(name) and name != "?"
        if is_real:
            resolved_real += 1
        print(f"slot {s:2d} team={slot_team.get(s,'?'):6s} jersey=#{jn} "
              f"name={name!r} pid={pid} domfrac={domfrac:.2f} votes(top5)={top} n={tot}")

    print(f"\n[replay] SLOTS RESOLVED TO REAL PLAYER: {resolved_real}/{len(all_slots)}")

    # Star check
    stars = ["Victor Wembanyama", "Shai Gilgeous-Alexander", "Chet Holmgren",
             "Jalen Williams", "De'Aaron Fox", "Devin Vassell", "Luguentz Dort",
             "Stephon Castle", "Harrison Barnes"]
    print("\n===== STAR RESOLUTION =====")
    resolved_names = {resolver.slot_to_player_name.get(s) for s in all_slots}
    for star in stars:
        jn = star_jerseys.get(star)
        # which slots saw this jersey in raw votes
        slots_with = [s for s in all_slots if jn in resolver._votes.get(s, Counter())]
        got = star in resolved_names
        print(f"  {star:28s} #{jn}  resolved={got}  slots_saw_jersey={slots_with}")


if __name__ == "__main__":
    main()
