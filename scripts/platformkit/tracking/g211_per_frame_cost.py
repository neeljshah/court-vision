"""Run G211's additive per-frame timing wrapper on the shared pod."""
from __future__ import annotations
import argparse, base64, io, json, re, subprocess, tarfile, time
from pathlib import Path
from typing import Any

PROJECT = "/workspace/nba-ai-system"
VIDEO = f"{PROJECT}/data/footage_corpus/wnba__wnba_01.mp4"
STAGES = ("pre_yolo", "yolo", "post_yolo", "crops_step3", "osnet", "assign_state", "render")

def _wrapper(token: str, frames: int) -> str:
    lines = [
        "import inspect,json,runpy,sys,textwrap,time", "from pathlib import Path", "from src.tracking import advanced_tracker as mod", "rows=[]",
        "class T:", " def start(self): self.last=time.perf_counter();self.current='pre_yolo';self.row={}",
        " def mark(self,n): now=time.perf_counter();self.row[self.current]=self.row.get(self.current,0)+now-self.last;self.current=n;self.last=now",
        " def finish(self): self.mark('finished');self.row.pop('finished',None);self.row['total']=sum(self.row.values());rows.append(self.row)",
        "timer=T();src=textwrap.dedent(inspect.getsource(mod.AdvancedFeetDetector.get_players_pos))",
        "edits=((\"_pose_any_ball = any(p.has_ball for p in self.players)\",\"timer.mark('yolo')\\n    _pose_any_ball = any(p.has_ball for p in self.players)\"),(\"_sp[\\\"yolo\\\"] = _subt.perf_counter() - _sp_t0\",\"_sp[\\\"yolo\\\"] = _subt.perf_counter() - _sp_t0\\n    timer.mark('post_yolo')\"),(\"detections: List[dict] = []\",\"timer.mark('crops_step3')\\n    detections: List[dict] = []\"),(\"_sp[\\\"crops_step3\\\"] = _subt.perf_counter() - _sp_last\",\"_sp[\\\"crops_step3\\\"] = _subt.perf_counter() - _sp_last\\n    timer.mark('osnet')\"),(\"_sp[\\\"osnet\\\"] = _subt.perf_counter() - _sp_last\",\"_sp[\\\"osnet\\\"] = _subt.perf_counter() - _sp_last\\n    timer.mark('assign_state')\"),(\"return self._render(\",\"timer.mark('render')\\n    return self._render(\"))",
        "for a,b in edits:\n if a != 'return self._render(' and src.count(a)!=1: raise RuntimeError('G211 anchor '+a)\n if a == 'return self._render(' and a not in src: raise RuntimeError('G211 anchor '+a)\n src=src.replace(a,b,1)",
        "ns=dict(mod.__dict__);ns['timer']=timer;exec(src,ns);original=ns['get_players_pos']", "def measured(self,*a,**k):\n timer.start()\n try:return original(self,*a,**k)\n finally:timer.finish()",
        "mod.AdvancedFeetDetector.get_players_pos=measured", f"sys.argv=['run_clip.py','--video','{VIDEO}','--frames','{frames}','--no-show','--skip-features','--data-dir','/tmp/g211_{token}_data']",
        f"try:runpy.run_path('{PROJECT}/scripts/run_clip.py',run_name='__main__')\nexcept SystemExit as e:rc=int(e.code or 0)\nelse:rc=0",
        f"Path('/tmp/g211_{token}/frames.json').write_text(json.dumps({{'exit_code':rc,'frames':rows}},sort_keys=True));raise SystemExit(rc)"]
    return base64.b64encode("\n".join(lines).encode()).decode()

def remote_script(token: str, frames: int) -> str:
    """Return a streamed wrapper that leaves the pod checkout untouched."""
    code = _wrapper(token, frames)
    commands = ["#!/usr/bin/env bash", "set -u", f"ROOT=/tmp/g211_{token}; DATA=/tmp/g211_{token}_data; PROBE=/tmp/g211_probe_{token}", "dd if=/dev/zero of=\"$PROBE\" bs=1M count=1 conv=fsync status=none", "rm -f \"$PROBE\"", "mkdir -p \"$ROOT\"", "context() {", " { date -u +%FT%TZ; echo \"cores=$(nproc)\"; echo DATA_DU_MB; du -sm /workspace/nba-ai-system/data; uptime; free -b", " nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits", " echo TOP_CPU; ps -eo pid=,ppid=,pcpu=,pmem=,rss=,etime=,args= --sort=-pcpu | head -40", f" echo SOURCE_HASHES; sha256sum {PROJECT}/scripts/run_clip.py {PROJECT}/src/pipeline/unified_pipeline.py {PROJECT}/src/tracking/advanced_tracker.py", f" echo INPUT; stat -c '%n|%s' {VIDEO}; ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames -of csv=p=0 {VIDEO}", " } > \"$ROOT/context_$1.txt\"", "}", "context before", "START=$(date +%s.%N); set +e", f"(cd {PROJECT} && echo {code} | base64 -d | /usr/local/bin/python -) > \"$ROOT/route.log\" 2>&1", "RC=$?; set -e; END=$(date +%s.%N)", "python3 - \"$ROOT/timing.json\" \"$START\" \"$END\" \"$RC\" <<'PY'", "import json,sys", "p,s,e,r=sys.argv[1:];json.dump({'started_epoch':float(s),'ended_epoch':float(e),'wall_seconds':float(e)-float(s),'exit_code':int(r)},open(p,'w'),sort_keys=True)", "PY", "context after", "du -sb \"$ROOT\" \"$DATA\" 2>/dev/null > \"$ROOT/cleanup_bytes.txt\" || du -sb \"$ROOT\" > \"$ROOT/cleanup_bytes.txt\"", "tar -C \"$ROOT\" -czf - . | base64 -w0", "rm -rf \"$ROOT\" \"$DATA\""]
    return "\n".join(commands) + "\n"

def bundle(stdout: bytes) -> dict[str, Any]:
    """Decode the temporary pod archive into local evidence data."""
    archive = tarfile.open(fileobj=io.BytesIO(base64.b64decode(stdout)), mode="r:gz")
    out: dict[str, Any] = {"text": {}, "json": {}}
    for member in archive.getmembers():
        if member.isfile():
            handle = archive.extractfile(member); assert handle is not None
            text, name = handle.read().decode("utf-8", errors="replace"), Path(member.name).name
            out["json" if name.endswith(".json") else "text"][name] = json.loads(text) if name.endswith(".json") else text
    return out

def _load1(context: str) -> float | None:
    found = re.search(r"load average: ([0-9.]+)", context)
    return float(found.group(1)) if found else None

def floor_shifted(before: str, after: str) -> bool:
    """Flag a greater-than-35-percent and greater-than-five load shift."""
    left, right = _load1(before), _load1(after)
    return left is None or right is None or abs(left-right) > max(5.0, .35*min(left,right))

def summarize(raw: dict[str, Any]) -> dict[str, Any]:
    """Make the timer's stage times a fully disjoint frame partition."""
    frames = raw["json"]["frames.json"]["frames"]
    rows = [{x: float(row.get(x, 0)) for x in (*STAGES, "total")} for row in frames]
    totals = sorted(row["total"] for row in rows)
    q = lambda p: totals[round((len(totals)-1)*p)] if totals else 0.0
    means = {x: sum(row[x] for row in rows)/len(rows) for x in (*STAGES, "total")} if rows else {}
    return {"timing":raw["json"]["timing.json"],"frame_rows":rows,"n_frames":len(rows),"distribution_seconds":{"median":q(.5),"p90":q(.9),"max":q(1)},"mean_stage_seconds":means,"mean_unattributed_seconds":means.get("total",0)-sum(means.get(x,0) for x in STAGES),"load_context_before":raw["text"].get("context_before.txt",""),"load_context_after":raw["text"].get("context_after.txt",""),"cleanup_bytes":raw["text"].get("cleanup_bytes.txt",""),"route_log":raw["text"].get("route.log","")}

def run(output: Path, ssh_config: Path, ssh_host: str, frames: int, attempts: int) -> int:
    """Measure immediately and repeat only discarded floor-shifted attempts."""
    discarded=[]
    for attempt in range(1, attempts+1):
        done=subprocess.run(["ssh","-F",str(ssh_config),ssh_host,"bash -s"],input=remote_script(f"{int(time.time())}_{attempt}",frames).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
        record=summarize(bundle(done.stdout)); record["ssh_exit_code"]=done.returncode; record["ssh_stderr"]=done.stderr.decode(errors="replace"); record["floor_shifted"]=floor_shifted(record["load_context_before"],record["load_context_after"])
        if record["floor_shifted"]: discarded.append(record); continue
        if done.returncode or record["timing"]["exit_code"]: output.write_text(json.dumps({"discarded":discarded,"failed":record},indent=2)+"\n"); return done.returncode or record["timing"]["exit_code"]
        output.write_text(json.dumps({"discarded":discarded,"accepted":record},indent=2)+"\n"); return 0
    output.write_text(json.dumps({"discarded":discarded,"failed":"floor_changed_every_attempt"},indent=2)+"\n"); return 2

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--ssh-config",type=Path,required=True); parser.add_argument("--ssh-host",default="pod"); parser.add_argument("--frames",type=int,default=360); parser.add_argument("--attempts",type=int,default=3)
    args=parser.parse_args(); return run(args.output,args.ssh_config,args.ssh_host,args.frames,args.attempts)

if __name__ == "__main__": raise SystemExit(main())
