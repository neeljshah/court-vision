import csv
from pathlib import Path
GRID = 101  # fixed candidate tick grid per section; interior-5 draws strictly inside it
rows = list(csv.DictReader(open("/workspace/g382_scratch/census.csv")))
out = []
for r in rows:
    n = int(r["nb_frames"])
    for k in range(GRID):
        idx = int(round(k * (n - 1) / (GRID - 1)))
        out.append({"section_id": r["section_id"], "video_id": r["video_id"],
                    "frame_order": str(idx), "native_path": r["native_path"],
                    "frame_key": "%s:%06d" % (r["section_id"], idx)})
p = Path("/workspace/g382_scratch/projection.csv")
with p.open("w", newline="") as h:
    w = csv.DictWriter(h, fieldnames=["frame_key","section_id","video_id","frame_order","native_path"], lineterminator="\n")
    w.writeheader(); w.writerows(out)
print("PROJECTION rows", len(out), "sections", len({r["section_id"] for r in out}))
