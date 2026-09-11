import csv, json, os, re, subprocess, sys, time
from pathlib import Path
ROOTS = ["/workspace/g364_scratch/val", "/workspace/g380_scratch/sources"]
LEDGER = Path("/workspace/data/tracking/track_daemon_ledger.jsonl")
census_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
led = {}
for line in LEDGER.read_text().splitlines():
    try: d = json.loads(line)
    except Exception: continue
    if d.get("game_id"): led[d["game_id"]] = d
rows = []
for root in ROOTS:
    for p in sorted(Path(root).glob("*.mp4")):
        stem = p.stem
        sec = re.sub(r"^[a-z_]+__", "", stem)
        m = re.match(r"^(.*)_s(\d+)$", sec)
        vid, off = (m.group(1), int(m.group(2))) if m else (sec, 0)
        try:
            out = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
                "stream=width,height,nb_frames,avg_frame_rate,duration","-of","json",str(p)],
                capture_output=True, text=True, timeout=60).stdout
            st = json.loads(out)["streams"][0]
        except Exception as exc:
            st = {"error": str(exc)}
        l = led.get(sec, {})
        rows.append({"section_id": sec, "video_id": vid, "sec_offset": off, "native_path": str(p),
            "bytes": p.stat().st_size, "width": st.get("width",""), "height": st.get("height",""),
            "nb_frames": st.get("nb_frames",""), "fps": st.get("avg_frame_rate",""),
            "duration": st.get("duration",""), "probe_error": st.get("error",""),
            "ledger_status": l.get("status",""), "ledger_rows": l.get("rows",""),
            "ledger_decoded": l.get("decoded_frames",""), "ledger_stride": l.get("stride",""),
            "ledger_res": l.get("source_resolution",""), "sport": stem.split("__")[0] if "__" in stem else ""})
out = Path("/workspace/g382_scratch/census.csv")
with out.open("w", newline="") as h:
    w = csv.DictWriter(h, fieldnames=list(rows[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(rows)
Path("/workspace/g382_scratch/census_meta.json").write_text(json.dumps({"CENSUS_UTC": census_utc,
  "roots": ROOTS, "n_sections": len(rows), "n_videos": len({r["video_id"] for r in rows}),
  "ledger_lines": len(led)}, indent=2)+"\n")
print("CENSUS_UTC", census_utc, "sections", len(rows), "videos", len({r["video_id"] for r in rows}))
