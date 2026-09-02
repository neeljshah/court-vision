"""worktree_data_links.py aN [aM ...] -- provision junctions of the local data stores into codex worktrees.

data/ is gitignored, so a fresh git worktree cannot see any parquet/jsonl store (S01 and S02 attempt 1 returned
NO STORE on 2026-09-03 for exactly this reason). Windows directory junctions: zero disk, always current, no admin.
NEVER links data/cache/eval_gate (the FWER ledger backtest_fwer.jsonl stays main-repo-only) and NEVER data/registry.
Python, not sh: Git Bash rewrites `mklink /J` into a path. Idempotent. ASCII. stdlib only.
"""
import os
import subprocess
import sys

MAIN = r"C:\Users\neelj\nba-ai-system\data"
RELS = ["domains", "models", "frontend", "cache/combo", "cache/ingame_grade_joined", "cache/ingame",
        "cache/pit", "cache/inplay_odds", "cache/ingame_grade", "cache/clv", "cache/pm_paper"]
FORBIDDEN = ["cache/eval_gate", "registry"]


def main(homes):
    for h in homes:
        wt = r"C:\Users\neelj\nba-track-" + h
        if not os.path.isdir(wt):
            print("SKIP %s: no worktree" % h)
            continue
        os.makedirs(os.path.join(wt, "data", "cache"), exist_ok=True)
        os.makedirs(os.path.join(wt, "data", "videos"), exist_ok=True)
        for rel in RELS:
            parts = rel.split("/")
            src = os.path.join(MAIN, *parts)
            dst = os.path.join(wt, "data", *parts)
            if not os.path.isdir(src) or os.path.lexists(dst):
                continue
            r = subprocess.run(["cmd", "/c", "mklink", "/J", dst, src], capture_output=True, text=True)
            print("%s %s data/%s %s" % ("LINK" if r.returncode == 0 else "FAIL", h, rel, r.stderr.strip()[:80]))
        for rel in FORBIDDEN:
            if os.path.lexists(os.path.join(wt, "data", *rel.split("/"))):
                print("WARN %s has data/%s -- must never be linked to main" % (h, rel))


if __name__ == "__main__":
    main(sys.argv[1:])
