import sys,json,time
sys.path.insert(0,r"C:\Users\neelj\nba-ai-system")
from pathlib import Path
import cv2
t=time.time()
from scripts.platformkit.tracking.tennis_sequential_plan import run_range
v=Path(r"C:\Users\neelj\nba-ai-system\data\footage_corpus\tennis__tennis_nyYk2nPZAwY_720p.mp4")
r=run_range(v,5715,6014)
out={"cv2":cv2.__version__,"coverage":r["solved_frame_coverage"],"decoded_frames":r["decoded_frames"],
     "fresh_solves":r["fresh_solves"],"drift_checked_reuses":r["drift_checked_reuses"],
     "elapsed_s":round(time.time()-t,1),"pod_value":0.6,"g26b_control":0.61}
open(r"C:\Users\neelj\AppData\Local\Temp\claude\C--Users-neelj\03ac0c2b-15f5-441a-a0b0-1b37c64748c5\scratchpad\local_range_result.json","w").write(json.dumps(out,indent=1))
print("DONE",json.dumps(out))
