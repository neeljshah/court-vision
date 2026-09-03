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
RELS = ["domains", "models", "frontend", "footage_corpus", "tracking", "videos/reference",
        "videos/bridge",
        "cache/combo", "cache/ingame_grade_joined", "cache/ingame",
        "cache/pit", "cache/inplay_odds", "cache/ingame_grade", "cache/clv", "cache/pm_paper",
        # 2026-09-03: absent here, an S-register lane could not see 34 cycle-history
        # files (24,612 rows) and declared a FALSE FALSIFIED. Same landmine as the
        # tracking and reference-clip misses earlier the same day.
        "cache/ingame_shadow_history"]
# footage_corpus and tracking added 2026-09-02: G25b, G33b and G44b all returned NOT VALIDATED
# because a worktree could not see any source clip or tracking table. Linking them is necessary
# but NOT sufficient -- the local main repo holds 2 clips and the pod holds 63 (6.6 GB), so any
# measurement that decodes frames still belongs on the pod. See FOOTAGE_CORPUS_INVENTORY.md.
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
            if not os.path.isdir(src):
                continue
            if os.path.lexists(dst):
                # A REAL directory sitting where a junction belongs is the silent
                # failure this whole script exists to prevent: the lane sees an
                # empty store and reports an honest-looking NOT VALIDATED that is
                # really a provisioning defect. G158 read 0 of 359 tables and G159
                # saw no download growth on 2026-09-03 for exactly this reason.
                # An empty one is safe to replace; a non-empty one is somebody's
                # work and is reported LOUDLY rather than destroyed.
                if os.path.islink(dst):
                    continue
                if os.listdir(dst):
                    print("WARN %s data/%s is a NON-EMPTY real directory, not a "
                          "junction -- the lane will not see main's store" % (h, rel))
                    continue
                os.rmdir(dst)
                print("REPLACE %s data/%s (was an empty real directory)" % (h, rel))
            r = subprocess.run(["cmd", "/c", "mklink", "/J", dst, src], capture_output=True, text=True)
            print("%s %s data/%s %s" % ("LINK" if r.returncode == 0 else "FAIL", h, rel, r.stderr.strip()[:80]))
        for rel in FORBIDDEN:
            if os.path.lexists(os.path.join(wt, "data", *rel.split("/"))):
                print("WARN %s has data/%s -- must never be linked to main" % (h, rel))


if __name__ == "__main__":
    main(sys.argv[1:])
