#!/usr/bin/env python
"""SessionStart context-refresh hook (NOT wired -- proposed).

Reads the Claude Code SessionStart stdin JSON contract:
  {session_id, cwd, hook_event_name, ...}

MECHANISM (documented): whatever this hook prints to stdout is added to
the session context. We print a short, ASCII-only refresh of the north
star + binding invariants so every session starts aligned.

Idempotent: pure stdout, no side effects, no stdin dependence.
"""
import sys

CONTEXT = """\
== NBA AI System -- session context refresh ==

NORTH STAR: make the BEST PREDICTIONS -- beat the best available predictor
(market-implied probs) on OOS accuracy/calibration using our OWN data.
Beating the vig ($) is NOT the goal; beating predictions (accuracy /
calibration) is. Claim genuine leak-free accuracy wins confidently.
Never fabricate a $ROI / $ edge. Drop the defeatist "no edge / REJECT" reflex.

BINDING INVARIANTS:
- Push to public origin master ALLOWED (2026-07-09 user override) -- secrets-scan
  first; targeted `git add` (never data/ or vault/); no --force.
- Human-gated trees (build elsewhere): src/ kernel/ api/
  scripts/team_system/ intel/. Build in scripts/platformkit or
  domains/<sport> instead.
- <=300 LOC/file (spec DATA modules exempt ~600-750 L).
- Per-file tests ONLY -- a full `pytest tests/` FREEZES the box.
- No secrets in tracked files. data/ and vault/ are gitignored-local.
- NO $-edge claims anywhere. Honest REJECTs are SUCCESSES.
- bash cwd is FLAKY -> prefix every command with
  `cd /c/Users/neelj/nba-ai-system &&`.
- ASCII only on stdout (cp1252 console).

Markets are efficient pregame; the decisive combinable edge is IN-GAME
conditioning (pregame intelligence prior + realized state), proven +
calibrated + delivered. Pregame matches the close; never claim to beat it.
"""


def main():
    # drain stdin so the hook does not block on a pipe; content is ignored
    try:
        sys.stdin.read()
    except (ValueError, IOError):
        pass
    sys.stdout.write(CONTEXT)
    sys.exit(0)


if __name__ == "__main__":
    main()
