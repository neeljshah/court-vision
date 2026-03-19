"""
monitor_loop.py — Real-time monitoring dashboard for the autonomous loop.

Shows current status, recent scores, and what the loop is working on.
Run this in a separate terminal to watch progress.

Usage:
    conda activate basketball_ai
    python monitor_loop.py
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
REPORT_PATH = os.path.join(DATA_DIR, "loop_report.json")
STATE_PATH = os.path.join(DATA_DIR, "loop_state.json")

def load_report() -> Dict:
    """Load latest loop report."""
    if os.path.exists(REPORT_PATH):
        with open(REPORT_PATH) as f:
            return json.load(f)
    return {}

def load_state() -> Dict:
    """Load loop state."""
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}

def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_dashboard(report: Dict, state: Dict):
    """Print the monitoring dashboard."""
    clear_screen()
    
    print("="*80)
    print(f"  NBA TRACKER AUTONOMOUS LOOP MONITOR")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Current status
    score = report.get("overall_score", 0)
    video = report.get("video", "Unknown")
    run_num = report.get("run_number", 0)
    passed = report.get("passed", False)
    trend = report.get("trend", "unknown")
    
    print(f"\n🎯 CURRENT RUN:")
    print(f"   Run #:     {run_num}")
    print(f"   Video:     {video}")
    print(f"   Score:      {score}/100 {'✅' if passed else '🔄'}")
    print(f"   Trend:      {trend}")
    
    # Top issue
    top_issue = report.get("top_issue")
    if top_issue:
        metric = top_issue.get("metric", "unknown")
        impact = top_issue.get("impact", "unknown")
        penalty = top_issue.get("penalty", 0)
        print(f"\n⚠️  TOP ISSUE:")
        print(f"   {metric}: {impact} impact (-{penalty} pts)")
        print(f"   {top_issue.get('description', '')[:80]}...")
    
    # Next action
    action = report.get("next_action", {})
    action_type = action.get("type", "unknown")
    action_desc = action.get("description", "No action")
    print(f"\n🔄 NEXT ACTION:")
    print(f"   Type: {action_type}")
    print(f"   {action_desc}")
    
    # Recent runs
    runs = state.get("runs", [])
    if runs:
        print(f"\n📊 RECENT RUNS (last 5):")
        print("   Run # | Score | Video                     | Trend")
        print("   ------|-------|---------------------------|-------")
        
        for run in runs[-5:]:
            r_num = runs.index(run) + 1
            r_score = run.get("score", 0)
            r_video = run.get("video", "unknown")[:25]
            r_trend = "new" if len(runs) == 1 else "stable"
            print(f"   {r_num:>5} | {r_score:>5.1f} | {r_video:<25} | {r_trend}")
    
    # Best score
    best_score = state.get("best_score", 0)
    print(f"\n🏆 BEST SCORE EVER: {best_score}/100")
    
    # Key metrics
    metrics = report.get("metrics", {})
    if metrics:
        print(f"\n📈 KEY METRICS:")
        print(f"   Avg players: {metrics.get('avg_players', 'N/A')}")
        print(f"   Team balance: {metrics.get('team_balance', 'N/A')}")
        print(f"   Ball detection: {metrics.get('ball_detection_pct', 'N/A')}")
        print(f"   Shots/min: {metrics.get('shots_per_minute', 'N/A')}")
        print(f"   Unique players: {metrics.get('unique_players_tracked', 'N/A')}")
    
    print("\n" + "="*80)
    print("Press Ctrl+C to stop monitoring. Dashboard refreshes every 10 seconds.")

def main():
    print("Starting NBA Tracker Loop Monitor...")
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            report = load_report()
            state = load_state()
            
            print_dashboard(report, state)
            
            # Wait before next refresh
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")

if __name__ == "__main__":
    main()
