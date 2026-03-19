"""
smart_loop.py — Continuous self-improving NBA tracker loop.

Runs autonomous_loop.py repeatedly, reads the report, auto-tunes tracker
parameters based on the top issue, and keeps going until the tracker scores
≥90 on 3 clips. Designed for low resource usage.

Features
--------
- Uses --frames 500 by default (≈17s of footage, fast per run)
- Parameter grid search: tries the next best param combo automatically
- Reverts params if score regresses
- Advances clip when plateaued (3+ runs with <2pt improvement)
- Fetches real NBA game stats (via game_matcher) for accurate validation
- All decisions logged to data/smart_loop_log.jsonl

Usage
-----
    conda activate basketball_ai
    python smart_loop.py                    # run forever
    python smart_loop.py --frames 300       # even lighter (10s clips)
    python smart_loop.py --max-runs 20      # stop after 20 iterations
    python smart_loop.py --target 85        # lower passing score
    python smart_loop.py --sleep 60         # longer pause between runs (seconds)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime
from typing import Optional

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

DATA_DIR      = os.path.join(PROJECT_DIR, "data")
STATE_PATH    = os.path.join(DATA_DIR, "loop_state.json")
REPORT_PATH   = os.path.join(DATA_DIR, "loop_report.json")
SMART_LOG     = os.path.join(DATA_DIR, "smart_loop_log.jsonl")
CONFIG_PATH   = os.path.join(PROJECT_DIR, "config", "tracker_params.json")
CONDA_ENV     = "basketball_ai"

DEFAULT_FRAMES = 500    # ~17s at 30fps — fast but enough for scoring
DEFAULT_SLEEP  = 45     # seconds between runs
DEFAULT_TARGET = 90     # score to declare victory per clip

# ── Parameter search space ────────────────────────────────────────────────────
# Each entry is a (param_name, candidate_values) pair.
# smart_loop tries these in order, one param at a time, guided by the top issue.

PARAM_GRID: dict[str, list] = {
    # Low avg_players → more detections
    "conf_threshold":      [0.25, 0.30, 0.35, 0.40],
    "kalman_fill_window":  [5, 7, 10, 12],
    # Team balance → appearance weights
    "appearance_w":        [0.15, 0.20, 0.25, 0.30, 0.35],
    # Too many / too few unique IDs
    "reid_threshold":      [0.35, 0.40, 0.45, 0.50, 0.55],
    "gallery_ttl":         [200, 250, 300, 350],
    # Frame crop (affects homography quality)
    "topcut":              [60, 120, 200, 320],
    # Lost track duration
    "max_lost_frames":     [60, 90, 120],
}

# Map issue metric → which params to tune first
ISSUE_TO_PARAMS: dict[str, list[str]] = {
    "avg_players":         ["conf_threshold", "kalman_fill_window"],
    "team_balance":        ["appearance_w"],
    "ball_detection_pct":  ["kalman_fill_window"],
    "shots_per_minute":    ["kalman_fill_window", "conf_threshold"],
    "unique_players_tracked": ["reid_threshold", "gallery_ttl"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(entry: dict):
    """Append a JSON entry to the smart loop log."""
    os.makedirs(DATA_DIR, exist_ok=True)
    entry["ts"] = datetime.now().isoformat()
    with open(SMART_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _load_config() -> dict:
    """Load current tracker params."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def _save_config(params: dict):
    """Write tracker params to config file."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(params, f, indent=2)
    print(f"[Smart] Config updated: {params}")


def _load_report() -> Optional[dict]:
    """Load the latest loop_report.json."""
    if not os.path.exists(REPORT_PATH):
        return None
    with open(REPORT_PATH) as f:
        return json.load(f)


def _load_state() -> dict:
    """Load loop state."""
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"runs": [], "best_score": 0.0, "clip_index": 0}


def _run_autonomous_loop(frames: int, force: bool = True) -> bool:
    """
    Run autonomous_loop.py once.

    Args:
        frames: Max frames to process.
        force:  Pass --force-rerun to always re-run the pipeline.

    Returns:
        True if succeeded, False if process failed.
    """
    cmd = [
        "conda", "run", "--no-capture-output",
        "-n", CONDA_ENV,
        "python", os.path.join(PROJECT_DIR, "autonomous_loop.py"),
        "--frames", str(frames),
    ]
    if force:
        cmd.append("--force-rerun")

    # Force UTF-8 everywhere to avoid Windows cp1252 encoding crashes
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

    print(f"\n[Smart] Running autonomous_loop --frames {frames}...")
    result = subprocess.run(cmd, capture_output=False, cwd=PROJECT_DIR, env=env)
    return result.returncode == 0


def _advance_clip():
    """Tell autonomous_loop to move to the next clip on next run."""
    state = _load_state()
    from autonomous_loop import NBA_CLIPS
    old_idx = state.get("clip_index", 0) % len(NBA_CLIPS)
    state["clip_index"]    = (old_idx + 1) % len(NBA_CLIPS)
    state["current_video"] = None
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
    new_label = NBA_CLIPS[state["clip_index"]][0]
    print(f"[Smart] Advanced clip → #{state['clip_index']}: {new_label}")
    return new_label


# ── Parameter tuning ──────────────────────────────────────────────────────────

class ParamTuner:
    """
    Maintains a cursor through PARAM_GRID and proposes the next param to try.

    Strategy:
      1. Look at the top issue metric in the report.
      2. Identify which params are relevant to that issue.
      3. Try each candidate value in order; skip values already tried this clip.
      4. If all candidates for the top issue are exhausted, try next issue's params.
    """

    def __init__(self):
        self._tried: dict[str, set] = {}   # param_name → set of tried values
        self._last_score: float     = 0.0
        self._no_improve_count: int = 0
        self._best_config: dict     = {}
        self._best_score: float     = 0.0

    def reset_for_new_clip(self):
        """Clear tried values when moving to a new clip."""
        self._tried = {}
        self._no_improve_count = 0
        print("[Smart] ParamTuner reset for new clip")

    def propose(self, report: dict, current_config: dict) -> Optional[dict]:
        """
        Return a new config dict to try, or None if exhausted.

        Args:
            report:         Latest loop_report.json
            current_config: Current tracker_params.json values

        Returns:
            New config dict, or None if nothing left to try.
        """
        issues = report.get("issues_ranked", [])
        if not issues:
            return None   # all metrics passing

        # Build ordered list of (param, value) candidates to try
        candidates: list[tuple[str, float]] = []
        for issue in issues:
            metric = issue.get("metric", "")
            for param in ISSUE_TO_PARAMS.get(metric, []):
                if param not in PARAM_GRID:
                    continue
                tried = self._tried.get(param, set())
                current_val = current_config.get(param)
                for val in PARAM_GRID[param]:
                    if val not in tried and val != current_val:
                        candidates.append((param, val))

        if not candidates:
            return None   # all candidates exhausted for all issues

        param, value = candidates[0]
        self._tried.setdefault(param, set()).add(value)

        new_config = deepcopy(current_config)
        new_config[param] = value
        print(f"[Smart] Proposing {param}: {current_config.get(param)} → {value}")
        return new_config

    def record_result(self, score: float, config: dict):
        """Update internal state after a run with the given score."""
        if score > self._best_score:
            self._best_score  = score
            self._best_config = deepcopy(config)
            self._no_improve_count = 0
        elif score <= self._last_score + 1.0:
            self._no_improve_count += 1
        self._last_score = score

    @property
    def no_improve_count(self) -> int:
        return self._no_improve_count

    @property
    def best_config(self) -> dict:
        return self._best_config

    @property
    def best_score(self) -> float:
        return self._best_score


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Smart Continuous NBA Tracker Loop")
    ap.add_argument("--frames",    type=int,   default=DEFAULT_FRAMES, help="Frames per pipeline run (default 500)")
    ap.add_argument("--max-runs",  type=int,   default=0,              help="Stop after N total iterations (0=forever)")
    ap.add_argument("--target",    type=float, default=DEFAULT_TARGET, help="Score to declare victory on a clip (default 90)")
    ap.add_argument("--sleep",     type=int,   default=DEFAULT_SLEEP,  help="Seconds to sleep between runs (default 45)")
    ap.add_argument("--no-revert", action="store_true",               help="Keep params even if score regresses")
    args = ap.parse_args()

    print(f"\n{'='*65}")
    print(f"  NBA Smart Loop — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  frames={args.frames}  target={args.target}  sleep={args.sleep}s")
    print(f"{'='*65}\n")

    tuner        = ParamTuner()
    run_count    = 0
    clips_passed = 0
    prev_config  = _load_config()

    # Save the initial (known-good) config so we can always revert
    baseline_config = deepcopy(prev_config)

    while True:
        run_count += 1
        if args.max_runs > 0 and run_count > args.max_runs:
            print(f"[Smart] Reached max-runs ({args.max_runs}). Stopping.")
            break

        print(f"\n{'─'*65}")
        print(f"[Smart] Run #{run_count}  |  {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'─'*65}")

        # ── 1. Run the pipeline + scoring ────────────────────────────────
        ok = _run_autonomous_loop(frames=args.frames, force=True)
        if not ok:
            print("[Smart] autonomous_loop failed — sleeping then retrying")
            _log({"event": "pipeline_error", "run": run_count})
            time.sleep(args.sleep)
            continue

        # ── 2. Read the report ───────────────────────────────────────────
        report = _load_report()
        if report is None:
            print("[Smart] No report found — skipping")
            time.sleep(args.sleep)
            continue

        score    = report.get("overall_score", 0.0)
        metrics  = report.get("metrics", {})
        video    = report.get("video", "?")
        top      = report.get("top_issue", {})
        data_src = report.get("real_stats", {}).get("data_source", "league_average")
        game_id  = report.get("real_stats", {}).get("game_id", None)

        print(f"\n[Smart] Score: {score:.1f}/100  |  Video: {video}")
        print(f"[Smart] Data source: {data_src}" + (f" (game {game_id})" if game_id else ""))
        def _fmt(v, spec="0.2f") -> str:
            try:
                return format(float(v), spec)
            except (TypeError, ValueError):
                return "N/A"
        print(f"[Smart] avg_players={_fmt(metrics.get('avg_players'))}  "
              f"team_balance={_fmt(metrics.get('team_balance'), '0.3f')}  "
              f"ball_det={_fmt(metrics.get('ball_detection_pct'))}  "
              f"shots/min={_fmt(metrics.get('shots_per_minute'))}")
        if top:
            print(f"[Smart] Top issue: {top.get('metric')} ({top.get('impact')}, -{top.get('penalty')} pts)")
            print(f"        → {top.get('suggested_fix', '')}")

        current_config = _load_config()
        tuner.record_result(score, current_config)

        # Revert if score regressed and --no-revert not set
        if (not args.no_revert
                and run_count > 1
                and score < tuner.best_score - 3.0):
            print(f"[Smart] Score regressed {score:.1f} vs best {tuner.best_score:.1f} — reverting config")
            _save_config(tuner.best_config if tuner.best_config else baseline_config)
            _log({
                "event":      "revert",
                "run":        run_count,
                "score":      score,
                "best_score": tuner.best_score,
            })

        _log({
            "event":      "scored",
            "run":        run_count,
            "score":      score,
            "video":      video,
            "metrics":    metrics,
            "data_source": data_src,
            "game_id":    game_id,
            "top_issue":  top.get("metric") if top else None,
            "config":     current_config,
        })

        # ── 3. Check for clip victory ─────────────────────────────────────
        if score >= args.target:
            clips_passed += 1
            print(f"\n[Smart] ✅ CLIP PASSED ({score:.1f} ≥ {args.target})  "
                  f"[{clips_passed} clips total]")
            if clips_passed >= 3:
                print(f"[Smart] 🏆 3 clips passed — tracker is performing well!")
                break
            tuner.reset_for_new_clip()
            new_clip = _advance_clip()
            _log({"event": "clip_passed", "run": run_count, "clip": video, "score": score})
            time.sleep(args.sleep)
            continue

        # ── 4. Check for plateau / ceiling ────────────────────────────────
        na_type = report.get("next_action", {}).get("type", "")
        no_improve = tuner.no_improve_count

        if na_type == "advance_clip" or no_improve >= 4:
            reason = "plateau detected" if no_improve >= 4 else report.get("next_action", {}).get("reason", "")
            print(f"[Smart] 📦 Advancing clip — {reason}")
            tuner.reset_for_new_clip()
            _save_config(tuner.best_config if tuner.best_config else baseline_config)
            new_clip = _advance_clip()
            _log({"event": "advance_clip", "run": run_count, "reason": reason})
            time.sleep(args.sleep)
            continue

        # ── 5. Propose next param to try ──────────────────────────────────
        new_config = tuner.propose(report, current_config)
        if new_config is not None:
            param_changed = {k: v for k, v in new_config.items() if v != current_config.get(k)}
            _save_config(new_config)
            _log({
                "event":         "param_tuned",
                "run":           run_count,
                "score_before":  score,
                "changed":       param_changed,
            })
        else:
            # All candidates exhausted — advance clip
            print(f"[Smart] All param candidates exhausted on this clip — advancing")
            tuner.reset_for_new_clip()
            _save_config(tuner.best_config if tuner.best_config else baseline_config)
            _advance_clip()
            _log({"event": "params_exhausted", "run": run_count})

        # ── 6. Sleep ──────────────────────────────────────────────────────
        print(f"\n[Smart] Sleeping {args.sleep}s before next run...")
        time.sleep(args.sleep)

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"  Smart Loop complete  |  {run_count} runs  |  {clips_passed} clips passed")
    state = _load_state()
    print(f"  Best score ever: {state.get('best_score', 0):.1f}")
    print(f"  Log: {SMART_LOG}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
