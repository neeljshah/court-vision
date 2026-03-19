"""Round-robin clip picker for benchmark loop."""
import json, os

BENCH_DIR = "data/benchmarks"
STATE_FILE = os.path.join(BENCH_DIR, "clip_rotation.json")

CLIPS = [
    {"label": "gsw_lakers_2025",  "game_id": "0022401117"},
    {"label": "bos_mia_2025",     "game_id": "0022400307"},
    {"label": "okc_dal_2025",     "game_id": None},
    {"label": "mil_chi_2025",     "game_id": None},
    {"label": "den_phx_2025",     "game_id": None},
    {"label": "lal_sas_2025",     "game_id": None},
    {"label": "atl_ind_2025",     "game_id": None},
]

os.makedirs(BENCH_DIR, exist_ok=True)
state = {}
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        state = json.load(f)

last_idx = state.get("last_idx", 1)  # bos_mia_2025 was index 1, last run
next_idx = (last_idx + 1) % len(CLIPS)
chosen = CLIPS[next_idx]

state["last_idx"] = next_idx
state["last_clip"] = chosen["label"]
with open(STATE_FILE, "w") as f:
    json.dump(state, f)

print(f"NEXT_CLIP={chosen['label']}")
print(f"GAME_ID={chosen['game_id'] or 'none'}")
