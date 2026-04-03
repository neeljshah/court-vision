#!/usr/bin/env python3
"""
CourtVision -- Master GitHub Cleanup Script
Run once from repo root: python cleanup_for_github.py
Dry-run first: python cleanup_for_github.py --dry-run
"""

import os
import shutil
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DRY = False

def log(msg): print(f"  {msg}")
def header(msg): print(f"\n{'='*60}\n  {msg}\n{'='*60}")
def run(cmd):
    if DRY: print(f"  [DRY] {cmd}"); return
    result = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
    if result.stdout.strip(): print(f"  {result.stdout.strip()}")
    if result.returncode != 0 and result.stderr.strip():
        print(f"  [warn] {result.stderr.strip()[:200]}")

def rm_file(p: Path):
    if p.exists():
        log(f"DELETE {p.relative_to(ROOT)}")
        if not DRY: p.unlink()

def rm_dir(p: Path):
    if p.exists():
        log(f"DELETE DIR {p.relative_to(ROOT)}")
        if not DRY: shutil.rmtree(p, ignore_errors=True)

def mv(src: Path, dst: Path):
    if src.exists():
        log(f"MOVE {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")
        if not DRY:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

def mkdir(p: Path):
    if not p.exists():
        log(f"MKDIR {p.relative_to(ROOT)}")
        if not DRY: p.mkdir(parents=True, exist_ok=True)


# --- PHASE 1: Create canonical folder structure ------------------------------
def phase1_structure():
    header("PHASE 1: Ensure canonical folder structure")
    dirs = [
        "docs", "config", ".planning/phases", ".planning/quick",
        "data/seeds", "data/models", "data/videos",
        "scripts", "src/data", "src/features", "src/pipeline",
        "src/prediction", "src/tracking",
        "tests", "api/routers", "database/migrations",
        "dashboards", "resources/panos",
        "_archive/throwaway_scripts", "_archive/debug_scripts",
    ]
    for d in dirs:
        mkdir(ROOT / d)

    # .gitkeep for dirs that must exist but stay empty
    for d in ["data/models", "data/videos", "logs", "resources/panos"]:
        keep = ROOT / d / ".gitkeep"
        if not keep.exists() and not DRY:
            (ROOT / d).mkdir(parents=True, exist_ok=True)
            keep.touch()
            log(f"TOUCH {d}/.gitkeep")


# --- PHASE 2: Delete root-level junk -----------------------------------------
def phase2_root_junk():
    header("PHASE 2: Delete root-level junk files")
    junk = [
        "bus.jpg", "OPUS_PROMPT.txt", "remote_ls.txt",
        "reprocess_safe.bat", "cleanup.py",
        ".claude_session_changes.json",
    ]
    for f in junk:
        rm_file(ROOT / f)

    # Model weights at root -- large binaries, should be downloaded at runtime
    weights = ["yolo26n.pt", "yolov8n.pt", "yolov8n-pose.pt", "yolov8x.pt",
               "yolov8n.onnx", "yolov8n-pose.onnx"]
    log("\n  -- Root-level model weights (delete -- download at runtime) --")
    for f in weights:
        rm_file(ROOT / f)


# --- PHASE 3: Move docs to proper locations -----------------------------------
def phase3_move_docs():
    header("PHASE 3: Move loose docs to docs/")
    moves = {
        "EXECUTION_GUIDE.md":      "docs/EXECUTION_GUIDE.md",
        "START_HERE.md":           "docs/START_HERE.md",
        "STITCH_INTEGRATION_GUIDE.md": "docs/STITCH_INTEGRATION_GUIDE.md",
        "REPROCESS_PLAN.md":       ".planning/REPROCESS_PLAN.md",
    }
    for src, dst in moves.items():
        mv(ROOT / src, ROOT / dst)


# --- PHASE 4: Archive throwaway scripts --------------------------------------
def phase4_scripts():
    header("PHASE 4: Archive scripts/_*.py throwaway scripts")
    scripts_dir = ROOT / "scripts"
    archive_dir = ROOT / "_archive" / "throwaway_scripts"
    if scripts_dir.exists():
        for f in scripts_dir.iterdir():
            if f.name.startswith("_") and f.suffix in (".py", ".sh"):
                mv(f, archive_dir / f.name)


# --- PHASE 5: Clean runtime artifacts ----------------------------------------
def phase5_runtime_artifacts():
    header("PHASE 5: Delete runtime artifacts")

    # data/ log and pid files
    data_dir = ROOT / "data"
    if data_dir.exists():
        for f in data_dir.iterdir():
            if f.is_file() and f.suffix in (".log", ".pid"):
                rm_file(f)
            if f.is_file() and f.name in (
                "CLEANUP_MANIFEST.txt", "audit_output.txt", "diag_output.txt",
                "enrich_output.txt", "recall_output.txt",
                "chain_pid.txt", "season_batch_pid.txt",
                "chain_log.txt",
            ):
                rm_file(f)

    # logs/
    rm_dir(ROOT / "logs")
    mkdir(ROOT / "logs")
    if not DRY: (ROOT / "logs" / ".gitkeep").touch()

    # pycache
    for p in ROOT.rglob("__pycache__"):
        if ".git" not in str(p): rm_dir(p)

    # pytest cache
    rm_dir(ROOT / ".pytest_cache")

    # .bak files
    for f in ROOT.rglob("*.bak"):
        if ".git" not in str(f): rm_file(f)


# --- PHASE 6: Nested git repos -----------------------------------------------
def phase6_nested_git():
    header("PHASE 6: Remove nested .git repos (not submodules)")
    nested = ["court-visions/.git", "teflon-quant-dashboard/.git"]
    for g in nested:
        rm_dir(ROOT / g)


# --- PHASE 7: Write .gitignore -----------------------------------------------
def phase7_gitignore():
    header("PHASE 7: Update .gitignore")
    content = """\
# =============================================================================
# CourtVision -- .gitignore
# =============================================================================

# -- Large Binaries / Video ---------------------------------------------------
data/videos/
*.mp4
*.avi
*.mov
*.mkv

# -- YOLO / Model Weights -----------------------------------------------------
*.pt
*.onnx
*.engine
*.trt
*.pkl
models/weights/
data/models/*.pkl
data/models/*.json
!data/models/.gitkeep

# -- Python -------------------------------------------------------------------
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.eggs/
*.whl

# -- Secrets & Environment ----------------------------------------------------
.env
.env.local
.env.production
.env.staging
*.env
.venv/
venv/
env/
conda-env/

# -- IDE & Editor -------------------------------------------------------------
.vscode/
.windsurf/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db
desktop.ini

# -- Runtime / Debug ----------------------------------------------------------
data/*.log
data/*.pid
data/*.txt
data/chain_*.txt
data/output/
data/game_results/
data/props/
data/predictions/
data/edges/
data/model_reports/
data/ball_yolo/

# -- Generated CV / Tracking data ---------------------------------------------
data/tracking/
data/games/
data/nba/
data/external/
resources/panos/
!resources/panos/.gitkeep

# -- SQLite databases ---------------------------------------------------------
*.db
*.sqlite3

# -- Logs ---------------------------------------------------------------------
logs/
*.log

# -- Tests --------------------------------------------------------------------
.pytest_cache/
.coverage
htmlcov/
coverage.xml
.hypothesis/

# -- Jupyter ------------------------------------------------------------------
.ipynb_checkpoints/
*.ipynb

# -- Node / Frontend ----------------------------------------------------------
node_modules/
.next/
dist/
.nuxt/
.output/
.cache/

# -- Separate projects / nested repos -----------------------------------------
court-visions/
court-vision-landing/
teflon-quant-dashboard/

# -- Archive (safe-moved code) -------------------------------------------------
_archive/
legacy/

# -- Throwaway scripts --------------------------------------------------------
scripts/_*

# -- Claude / RunPod / MCP session state --------------------------------------
.runpod
.mcp.json
.claude_session_changes.json
.claude/worktrees/
.claude/settings.local.json

# -- Benchmark / Diagnostic outputs -------------------------------------------
data/benchmarks/report_*.json
bus.jpg
remote_ls.txt
OPUS_PROMPT.txt
reprocess_safe.bat
cleanup.py

# -- Backup files -------------------------------------------------------------
*.bak
*.orig
*.tmp
"""
    gitignore = ROOT / ".gitignore"
    log(f"WRITE .gitignore ({len(content.splitlines())} lines)")
    if not DRY:
        with open(gitignore, "w") as f:
            f.write(content)


# --- PHASE 8: Write .env.example ----------------------------------------------
def phase8_env_example():
    header("PHASE 8: Write .env.example")
    content = """\
# CourtVision -- Environment Variables Template
# Copy to .env and fill in real values. Never commit .env.

# -- Database ----------------------------------------------------------------
DATABASE_URL=postgresql://nba_user:PASSWORD@localhost:5432/nba_ai
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=nba_ai
POSTGRES_USER=nba_user
DB_PASSWORD=

# -- Redis --------------------------------------------------------------------
REDIS_URL=redis://localhost:6379

# -- API Keys -----------------------------------------------------------------
NBA_API_KEY=
CLAUDE_API_KEY=
THE_ODDS_API_KEY=

# -- App -----------------------------------------------------------------------
ENV=development
DEBUG=false
"""
    p = ROOT / ".env.example"
    log("WRITE .env.example")
    if not DRY:
        with open(p, "w") as f:
            f.write(content)


# --- PHASE 9: Git -- unstage ignored files -------------------------------------
def phase9_git_unstage():
    header("PHASE 9: Git -- remove now-ignored files from tracking")
    cmds = [
        "git rm -r --cached data/models/ 2>/dev/null || true",
        "git rm -r --cached resources/panos/ 2>/dev/null || true",
        "git rm -r --cached logs/ 2>/dev/null || true",
        "git rm -r --cached _archive/ 2>/dev/null || true",
        "git rm -r --cached legacy/ 2>/dev/null || true",
        "git rm --cached .runpod 2>/dev/null || true",
        "git rm --cached .mcp.json 2>/dev/null || true",
        "git rm --cached .claude_session_changes.json 2>/dev/null || true",
        "git rm --cached data/nba_ai.db 2>/dev/null || true",
        "git rm --cached data/full_game_results.json 2>/dev/null || true",
        "git rm --cached data/tracking_results.json 2>/dev/null || true",
        "git rm --cached data/phase_g_metrics.csv 2>/dev/null || true",
        "git rm --cached data/phase_g_processed.txt 2>/dev/null || true",
        "git rm --cached data/models/win_prob_metrics.json 2>/dev/null || true",
        "git rm --cached data/models/win_probability.pkl 2>/dev/null || true",
        "git rm --cached data/models/xfg_v1.pkl 2>/dev/null || true",
    ]
    for cmd in cmds:
        run(cmd)


# --- PHASE 10: Git commit -----------------------------------------------------
def phase10_git_commit():
    header("PHASE 10: Git -- stage and commit cleanup")
    run("git add .gitignore .env.example")
    run("git add -A")
    run('git status --short')
    commit_msg = (
        "chore: pre-publish cleanup\\n\\n"
        "- Remove junk files from repo root (bus.jpg, OPUS_PROMPT.txt, etc.)\\n"
        "- Archive 36 throwaway scripts/_*.py\\n"
        "- Delete runtime artifacts (logs, pids, .bak files)\\n"
        "- Remove root-level model weights (download at runtime)\\n"
        "- Harden .gitignore (secrets, binaries, CV outputs, nested repos)\\n"
        "- Add .env.example template\\n"
        "- Move loose docs to docs/ and .planning/\\n"
        "- Remove nested .git in court-visions/\\n"
        "- Unstage tracked files that should be ignored"
    )
    run(f'git commit -m "{commit_msg}"')


# --- PHASE 11: Pre-push security audit ---------------------------------------
def phase11_audit():
    header("PHASE 11: Pre-push security audit")

    print("\n  [1] Secrets scan -- checking for hardcoded keys/passwords:")
    result = subprocess.run(
        'grep -rn "sk-\\|ghp_\\|password=\\|API_KEY=\\|api_key=" '
        '--include="*.py" --include="*.yml" --include="*.json" '
        '--exclude-dir=".git" --exclude-dir="node_modules" .',
        shell=True, cwd=ROOT, capture_output=True, text=True
    )
    hits = [l for l in result.stdout.splitlines() if ".env.example" not in l and ".gitignore" not in l]
    if hits:
        print(f"  [WARN] FOUND {len(hits)} potential secret(s):")
        for h in hits[:10]: print(f"    {h}")
    else:
        print("  [OK] No secrets found")

    print("\n  [2] Files >10MB still tracked:")
    result = subprocess.run(
        'git ls-files | python -c "import sys,os; [print(f) for f in sys.stdin.read().splitlines() if os.path.exists(f) and os.path.getsize(f) > 10*1024*1024]"',
        shell=True, cwd=ROOT, capture_output=True, text=True
    )
    if result.stdout.strip():
        print(f"  [WARN] Large files:\n{result.stdout.strip()}")
    else:
        print("  [OK] No large files tracked")

    print("\n  [3] .env files tracked:")
    result = subprocess.run('git ls-files | grep -i "\\.env"', shell=True, cwd=ROOT, capture_output=True, text=True)
    if result.stdout.strip():
        print(f"  [WARN] .env tracked: {result.stdout.strip()}")
    else:
        print("  [OK] No .env files tracked")

    print("\n  [4] Binary model files tracked:")
    result = subprocess.run(
        'git ls-files | grep -E "\\.(pkl|pt|onnx|engine|trt|mp4|db)$"',
        shell=True, cwd=ROOT, capture_output=True, text=True
    )
    if result.stdout.strip():
        print(f"  [WARN] Binary files tracked:\n{result.stdout.strip()}")
    else:
        print("  [OK] No binary model/video files tracked")


# --- MAIN ---------------------------------------------------------------------
def main():
    global DRY
    parser = argparse.ArgumentParser(description="CourtVision GitHub cleanup script")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions, make no changes")
    parser.add_argument("--skip-git", action="store_true", help="Skip git phases (9+10)")
    parser.add_argument("--audit-only", action="store_true", help="Run security audit only")
    args = parser.parse_args()
    DRY = args.dry_run

    if DRY: print("\n  *** DRY RUN MODE -- no changes will be made ***\n")

    if args.audit_only:
        phase11_audit()
        return

    phase1_structure()
    phase2_root_junk()
    phase3_move_docs()
    phase4_scripts()
    phase5_runtime_artifacts()
    phase6_nested_git()
    phase7_gitignore()
    phase8_env_example()

    if not args.skip_git:
        phase9_git_unstage()
        phase10_git_commit()

    phase11_audit()

    print("\n" + "="*60)
    print("  CLEANUP COMPLETE")
    print("  Next: git remote add origin <url> && git push -u origin master")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
