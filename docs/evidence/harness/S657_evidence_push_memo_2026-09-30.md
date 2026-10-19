# S657 evidence push step -- result memo (2026-09-30, CLOUD-READY lead)

VERDICT: BUILT + VERIFIED, PARKED (not wired into the tick; the tick files belong to the tick
owner). Branch `s657-evidence-push` in worktree C:/Users/neelj/nba-harness-h332.

What it is: `python -m scripts.platformkit.ops.evidence_push --date D [--root .] [--remote
private] [--branch trunk] [--dry-run]`. After the paper night for D it publishes exactly the night
record(s) nights/<D>.json / <D>.rN.json and the artifacts the newest record lists (present true,
sha256 equal to the record), all under docs/evidence/forward/: commit, rebase on the remote
branch only when it moved, push. Exit 0 pushed / nothing_to_push / record_absent / dry_run;
2 refused (nothing left staged); 3 rebase failed (aborted, commit stays local); 4 fetch or push
failed (incl. the pre-push guard refusing); 5 unpushed local commits or a git operation in
progress. Every git call runs with core.autocrlf=false; add-all, force flags, no-verify, mirror
and `+` refspecs are refused inside the module's git runner.

Loop: spec 6aba25877; pre-build Opus critic REVISE (12 items) folded as AMENDMENT 1 720c4aff3;
build d5aa4437a; CONTRACT tier (Opus) ACCEPT WITH CORRECTIONS (4 items: in-progress check before
the detached-HEAD check, RUNNER.lock parametrize case, exit codes asserted in cases 13/18, this
memo) all applied in the fix round, plus two of its NEW GAPs (hook lookup from a linked worktree
via `rev-parse --git-path`; a dry-run test); ADVERSARIAL tier: see the register row.

Tests (one pytest process, tmp git repos, isolated global/system git config):
`python -m pytest tests/platformkit/ops/test_evidence_push.py -q` -> 27 passed, 1 skipped
(case 3b symlink: symlinks not permitted on this Windows account). One unexplained single
failure was seen once in the first seven builder runs (test id not captured); not reproduced in
the next nine runs by the builder and the contract tier.

HUMAN STEPS / KNOWN LIMITS
- A2: after exit 3 the evidence commit stays local and every later run exits 5
  (`unpushed_local_commits`). Clear it by hand on the recorder box: resolve the conflict and push,
  or inspect `git log <remote>/<branch>..HEAD` and `git reset --mixed <remote>/<branch>` (the
  files stay on disk) so the next run re-stages them.
- A dirty superseded weeks/<W>.json (rewritten by a later night) plus a remote that moved makes
  git refuse the rebase (exit 3). Pushing each night the morning it runs avoids it.
- Expected refusal on the laptop: its checkout holds foreign tracked edits, so it exits 2
  (`tracked_modifications_outside_push_set`). This is the one-committer guard (audit section 8).
  On the VM a known source is issues/<D>.md, rewritten in place by paper_desk_issues.
- A fresh VM clone has no pre-push hook: the step refuses (`prepush_guard_absent`) until
  scripts/hooks/install_prepush.sh is run there.

- A listed path whose case or form differs from git's canonical name (e.g. "Qualification/",
  "forward//x") passes the checks but is silently left out (nothing_to_push), not refused.
- A malformed night record gives a traceback and exit 1 (nothing staged), not exit 2 JSON.

ADVERSARIAL tier (Opus): ACCEPT WITH CORRECTIONS (memo-only); 10 of 10 run mutants killed; the
staged_set_mismatch refusal has no reaching test (a backstop; mutant survives by reading); a
detached-HEAD case was added in the final round.

NOT VERIFIED: the staged_set_mismatch refusal (no test reaches it); the symlink case on an account that allows symlinks; behaviour against the real
private remote and a VM clone (tmp repos only); a commit dropped by the rebase as already
upstream (exit 0 path, untested); a listed artifact that is gitignored would read as unchanged
(no current forward path is ignored).
