import sys,json,time
sys.path.insert(0,r"C:\Users\neelj\nba-ai-system")
from pathlib import Path
import cv2
from scripts.platformkit.tracking.tennis_sequential_plan import run_range
V=Path(r"C:\Users\neelj\nba-ai-system\data\footage_corpus\tennis__tennis_nyYk2nPZAwY_720p.mp4")
CASES=[(43830,44129,0.56,0.53),(33105,33404,0.99,0.9933333333333333),(41985,42284,0.5733333333333334,0.5733333333333334)]
res=[]
for start,stop,ctrl,pod in CASES:
    t=time.time(); r=run_range(V,start,stop)
    res.append({"start":start,"coverage":r["solved_frame_coverage"],"control":ctrl,"pod":pod,
                "matches_control":abs(r["solved_frame_coverage"]-ctrl)<1e-9,
                "matches_pod":abs(r["solved_frame_coverage"]-pod)<1e-9,"elapsed_s":round(time.time()-t,1)})
    open(r"C:\Users\neelj\AppData\Local\Temp\claude\C--Users-neelj\03ac0c2b-15f5-441a-a0b0-1b37c64748c5\scratchpad\local_range2_result.json","w").write(
        json.dumps({"cv2":cv2.__version__,"cases":res},indent=1))
print("DONE")
