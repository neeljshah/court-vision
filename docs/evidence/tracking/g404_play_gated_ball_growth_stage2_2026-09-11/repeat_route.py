"""G404 repeat route: regenerate the census join and the gate-audit scoring."""
import subprocess
import sys

OUT = "docs/evidence/tracking/g404_play_gated_ball_growth_stage2_2026-09-11"
MASTER = "C:/Users/neelj/nba-ai-system/docs/evidence/tracking"
EVID = "docs/evidence/tracking"
CENSUS = [sys.executable, "scripts/platformkit/tracking/g404_census.py",
          "--census-jsonl", OUT + "/census.jsonl", "--digests", OUT + "/digests.txt",
          "--out-dir", OUT, "--census-utc", "2026-09-11T20:39:09Z",
          "--old-source", EVID + "/g389_ball_reference_completion_2026-09-11/frames_v3.csv::game::G389 development plus held-out split identities",
          "--old-source", EVID + "/g389_ball_reference_completion_2026-09-11/dev_boxes_v3.csv::game::530-box accepted reference games",
          "--old-source", EVID + "/g387_paint_localization_controls_2026-09-11/selection.csv::video_id::G387 context identities",
          "--old-source", EVID + "/g394_ball_person_negatives_2026-09-11/context.csv::game::G394 context identities",
          "--old-source", EVID + "/g398_a8_high_resolution_dev_shadow_2026-09-11/dev_manifest.csv::game::G398 dev shadow identities",
          "--old-source", MASTER + "/g400_ball_reference_growth_stage1_2026-09-11/draw.csv::video_id::G400 stage-1 rated games landed on master and absent from the a18 base",
          "--old-source", MASTER + "/g400_ball_reference_growth_stage1_2026-09-11/census.csv::video_id::G400 censused pool landed on master and absent from the a18 base"]
FINISH = [sys.executable, "scripts/platformkit/tracking/g404_finish.py", "--out-dir", OUT,
          "--cards", "C:/Users/neelj/g404_receiver/cards",
          "--claude-labels", OUT + "/gate_raw/gate_raw_claude.csv",
          "--prereg-commit", "5112012e9", "--amendment-commit", "039ac8811",
          "--verdict", "PARTIAL"]
for command in (CENSUS, FINISH):
    result = subprocess.run(command, capture_output=True, text=True, env={"PYTHONPATH": "."})
    print(command[1].split("/")[-1], "rc", result.returncode, result.stdout.strip()[-200:])
