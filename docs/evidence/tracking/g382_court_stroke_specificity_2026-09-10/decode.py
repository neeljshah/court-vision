import csv, hashlib, json, subprocess, sys, time
from collections import defaultdict
from pathlib import Path
SCR = Path("/workspace/g382_scratch"); FR = SCR/"frames"; FR.mkdir(exist_ok=True)
def sha(p):
    h = hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda: f.read(1<<20), b""): h.update(b)
    return h.hexdigest()
rows = list(csv.DictReader(open(SCR/"frames_planned.csv")))
bysec = defaultdict(list)
for r in rows: bysec[r["section_id"]].append(r)
out, pins = [], []
for sec, members in sorted(bysec.items()):
    src = Path(members[0]["native_path"])
    t0 = time.time()
    if not src.exists():
        for r in members: out.append(dict(r, retained="MISSING_SOURCE", frame_path="", native_width="", native_height="", source_sha256=""))
        pins.append({"section_id": sec, "path": str(src), "status": "VANISHED_BEFORE_CAPTURE"}); continue
    pre = sha(src); size = src.stat().st_size
    probe = json.loads(subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
        "stream=width,height,nb_frames,avg_frame_rate","-of","json",str(src)],capture_output=True,text=True).stdout)["streams"][0]
    idxs = [int(r["frame_order"]) for r in members]
    expr = "+".join("eq(n\,%d)" % i for i in idxs)
    cmd = ["ffmpeg","-nostdin","-v","error","-y","-i",str(src),"-vf","select=%s" % expr,
           "-vsync","0","-frames:v",str(len(idxs)),str(FR/(sec+"_%03d.png"))]
    rc = subprocess.run(cmd,capture_output=True,text=True)
    post = sha(src)
    pins.append({"section_id": sec, "path": str(src), "bytes": size, "sha256_pre": pre, "sha256_post": post,
                 "stable": pre == post, "width": probe.get("width"), "height": probe.get("height"),
                 "nb_frames": probe.get("nb_frames"), "fps": probe.get("avg_frame_rate"),
                 "ffmpeg_rc": rc.returncode, "ffmpeg_err": rc.stderr[:200], "seconds": round(time.time()-t0,1)})
    for k, r in enumerate(sorted(members, key=lambda z: int(z["frame_order"])), start=1):
        png = FR/("%s_%03d.png" % (sec, k))
        ok = png.exists() and pre == post and rc.returncode == 0
        out.append(dict(r, retained="RETAINED" if ok else "DECODE_FAILED",
            frame_path=str(png) if ok else "", native_width=str(probe.get("width","")) if ok else "",
            native_height=str(probe.get("height","")) if ok else "", source_sha256=pre))
    print("SEC", sec, "rc", rc.returncode, "stable", pre==post, flush=True)
with (SCR/"frames.csv").open("w",newline="") as h:
    w = csv.DictWriter(h, fieldnames=list(out[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(out)
(SCR/"pins.json").write_text(json.dumps(pins, indent=2)+"\n")
print("DECODE_DONE retained", sum(1 for r in out if r["retained"]=="RETAINED"), "of", len(out))
