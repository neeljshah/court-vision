#!/usr/bin/env python3
"""
continuous_runner.py — Runs the autonomous loop indefinitely.

This script keeps the autonomous loop running continuously:
1. Runs autonomous_loop.py on different videos
2. Reads the report to see what needs fixing
3. Applies fixes automatically when safe
4. Advances to next clip when needed
5. Repeats forever

Usage:
    conda activate basketball_ai
    python continuous_runner.py
"""

import os
import json
import subprocess
import sys
import time
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
REPORT_PATH = os.path.join(DATA_DIR, "loop_report.json")
STATE_PATH = os.path.join(DATA_DIR, "loop_state.json")

CONDA_ENV = "basketball_ai"

def load_report():
    """Load the latest loop report."""
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH) as f:
            return json.load(f)
    return {}

def run_autonomous_loop(args=None):
    """Run one iteration of the autonomous loop."""
    cmd = [
        "conda", "run", "--no-capture-output",
        "-n", CONDA_ENV,
        "python", os.path.join(PROJECT_DIR, "autonomous_loop.py")
    ]
    
    if args:
        cmd.extend(args)
    
    print(f"\n{'='*80}")
    print(f"[Continuous] Running autonomous loop: {' '.join(args) if args else 'default'}")
    print(f"{'='*80}\n")
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_DIR)
    
    if result.returncode != 0:
        print(f"[Continuous] Loop failed: {result.stderr}")
        return False
    
    print(result.stdout)
    return True

def apply_safe_fix(report):
    """Apply fixes that are safe and under 20 lines."""
    action = report.get("next_action", {})
    
    if action.get("type") != "code_fix":
        return False
    
    files = action.get("files", [])
    approach = action.get("approach", "")
    
    # Only fix tracking files, not pipeline/data/analytics
    safe_files = [f for f in files if "src/tracking/" in f]
    if not safe_files:
        return False
    
    # Check if fix is simple (under 20 lines)
    if "lower YOLO confidence" in approach:
        return apply_yolo_confidence_fix()
    elif "extend Kalman fill window" in approach:
        return apply_kalman_window_fix()
    elif "extend optical-flow fallback" in approach:
        return apply_optical_flow_fix()
    elif "Reduce GALLERY_TTL" in approach:
        return apply_gallery_ttl_fix()
    elif "Increase REID_THRESHOLD" in approach:
        return apply_reid_threshold_fix()
    
    return False

def apply_yolo_confidence_fix():
    """Lower YOLO confidence from 0.5 to 0.4."""
    file_path = os.path.join(PROJECT_DIR, "src", "tracking", "advanced_tracker.py")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if "conf=0.4" in content:
            print("[Continuous] YOLO confidence already at 0.4")
            return True
        
        if "conf=0.5" in content:
            content = content.replace("conf=0.5", "conf=0.4")
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            print("[Continuous] ✅ Applied fix: YOLO confidence 0.5 → 0.4")
            return True
    
    except Exception as e:
        print(f"[Continuous] Failed to apply YOLO fix: {e}")
    
    return False

def apply_kalman_window_fix():
    """Extend Kalman fill window from 5 to 7."""
    file_path = os.path.join(PROJECT_DIR, "src", "tracking", "advanced_tracker.py")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if "lost_age <= 7" in content:
            print("[Continuous] Kalman window already at 7")
            return True
        
        if "lost_age <= 5" in content:
            content = content.replace("lost_age <= 5", "lost_age <= 7")
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            print("[Continuous] ✅ Applied fix: Kalman window 5 → 7")
            return True
    
    except Exception as e:
        print(f"[Continuous] Failed to apply Kalman fix: {e}")
    
    return False

def apply_optical_flow_fix():
    """Extend optical flow from 8 to 14 frames."""
    file_path = os.path.join(PROJECT_DIR, "src", "tracking", "ball_detect_track.py")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if "_MAX_FLOW_FRAMES = 14" in content:
            print("[Continuous] Optical flow already at 14")
            return True
        
        if "_MAX_FLOW_FRAMES = 8" in content:
            content = content.replace("_MAX_FLOW_FRAMES = 8", "_MAX_FLOW_FRAMES = 14")
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            print("[Continuous] ✅ Applied fix: Optical flow 8 → 14 frames")
            return True
    
    except Exception as e:
        print(f"[Continuous] Failed to apply optical flow fix: {e}")
    
    return False

def apply_gallery_ttl_fix():
    """Reduce gallery TTL from 300 to 200."""
    file_path = os.path.join(PROJECT_DIR, "src", "tracking", "advanced_tracker.py")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if "GALLERY_TTL = 200" in content:
            print("[Continuous] Gallery TTL already at 200")
            return True
        
        if "GALLERY_TTL = 300" in content:
            content = content.replace("GALLERY_TTL = 300", "GALLERY_TTL = 200")
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            print("[Continuous] ✅ Applied fix: Gallery TTL 300 → 200")
            return True
    
    except Exception as e:
        print(f"[Continuous] Failed to apply gallery TTL fix: {e}")
    
    return False

def apply_reid_threshold_fix():
    """Increase re-ID threshold from 0.45 to 0.55."""
    file_path = os.path.join(PROJECT_DIR, "src", "tracking", "advanced_tracker.py")
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        if "REID_THRESHOLD = 0.55" in content:
            print("[Continuous] Re-ID threshold already at 0.55")
            return True
        
        if "REID_THRESHOLD = 0.45" in content:
            content = content.replace("REID_THRESHOLD = 0.45", "REID_THRESHOLD = 0.55")
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            print("[Continuous] ✅ Applied fix: Re-ID threshold 0.45 → 0.55")
            return True
    
    except Exception as e:
        print(f"[Continuous] Failed to apply re-ID threshold fix: {e}")
    
    return False

def main():
    print(f"\n{'='*80}")
    print(f"  NBA Tracker Continuous Improvement Runner")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")
    
    run_count = 0
    
    try:
        while True:
            run_count += 1
            print(f"\n[Continuous] === Run #{run_count} at {datetime.now().strftime('%H:%M:%S')} ===")
            
            # Run the autonomous loop
            success = run_autonomous_loop()
            
            if not success:
                print("[Continuous] Loop failed, waiting 30s before retry...")
                time.sleep(30)
                continue
            
            # Read the report
            report = load_report()
            if not report:
                print("[Continuous] No report generated, waiting 10s...")
                time.sleep(10)
                continue
            
            score = report.get("overall_score", 0)
            action = report.get("next_action", {})
            action_type = action.get("type", "unknown")
            
            print(f"\n[Continuous] Score: {score}/100 | Action: {action_type}")
            
            # Apply safe fixes if needed
            if action_type == "code_fix":
                print("[Continuous] Attempting to apply safe fix...")
                if apply_safe_fix(report):
                    print("[Continuous] Fix applied, running verification...")
                    # Re-run to verify the fix
                    run_autonomous_loop(["--force-rerun"])
                else:
                    print("[Continuous] Fix too complex or unsafe, skipping...")
            
            # Auto-advance clip if needed
            elif action_type == "advance_clip":
                print("[Continuous] Advancing to next clip...")
                run_autonomous_loop(["--next-clip"])
            
            # Check if we should continue
            if score >= 90:
                print(f"\n[Continuous] ✨ Excellent score ({score}/100)! Trying next clip...")
                run_autonomous_loop(["--next-clip"])
            
            # Brief pause between runs
            print("[Continuous] Waiting 5s before next run...")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print(f"\n[Continuous] Stopped by user after {run_count} runs")
    except Exception as e:
        print(f"\n[Continuous] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
