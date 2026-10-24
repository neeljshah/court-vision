# S832 -- the live checkout must never be a shallow clone (desk invariant + rule)

Row: S832 (register docs/evidence/HARNESS_GAPS_2026-09-03.md, allocated 2026-10-22). PAPER ONLY;
calibration language only.

## 1. Premise (fresh reads, master d091bc086)

- `.git/shallow` existed in C:/Users/neelj/nba-ai-system from 17:18Z 10-20 to 15:2xZ 10-22 (a
  depth-limited fetch during the owner session's public-merge sequence). While it existed,
  `git log -1 HEAD -- <file>` returned the boundary commit 25f9ba76b (2026-10-20) for every tracked
  file, so ingame_scoreboard_amendment.verify_amendment raised amendment_not_prospective (night
  10-20 scoreboard, exit 1 at 1.5 s), registry_scorer_e_night raised caller_policy_not_prospective
  (night 10-20 E) and m2_readout_io refused prereg_not_production (the 10-19 M2 read-out).
- Nothing in the desk checked the repository state: the tick (paper_desk_tick.Desk.work) runs
  capture / heartbeat / schedule / nights / census steps only; the morning run reads status.json.
- The repair (`git fetch --unshallow private`) is additive and was verified 10-22 (night 10-21 and
  10-22 scoreboard steps selected PREREG_2026-10-07 without raising).

## 2. The change (this row: (a) and (c); (b) refusal attribution stays open)

(a) New module scripts/platformkit/ops/paper_desk_repo.py: `git_is_shallow(root)` asks
`git rev-parse --is-shallow-repository`; `check_shallow(root, row, query)` journals the answer on a
tick row: `false` -> decision tick_ok / reason checked (success in the tick family, so it CLEARS a prior
shallow attention in status recovery; the answer kept under git_answer); `true` -> decision refused / reason repository_shallow / refusals
{repository_shallow: 1} (+ shallow_file_mtime when .git/shallow is a file); any other answer ->
git_answer_unreadable; a raised query -> git_query_failed. Every non-false outcome is a counted
refusal, so the tick exits 3 with reason step_refusals and status.json shows the step
`tick:repo_shallow` under attention (classification = attention; family tick needs no table change).
Desk.work runs the step FIRST, only on the live root (self.root == ROOT) or when a `git` answer is
injected (tests); construct roots skip it, so no existing tick test changes.
(c) Rule appended to docs/operations/cloud/rules/bash-cwd-prefix.md (and the local .claude/rules
original) + a How-to line in DESK_STATE: never a depth-limited fetch into the main checkout; check
`git rev-parse --is-shallow-repository` before seal / prereg / policy work; repair = unshallow.

## 3. Acceptance

- tests/platformkit/ops/test_paper_desk_s832_repo_shallow.py green (9 cases: refusal + attention
  on `true`, success on `false`, a repair clearing the pending attention in status recovery, unreadable answers, raised query, live-tick exit 3 with no night
  started, live-tick pass, construct skip, real git answer on this checkout + RuntimeError off-repo).
- tests/platformkit/ops/test_paper_desk_tick.py and the r4-r9 attention tests unchanged and green
  (no ATTENTION_TABLE change; test_paper_desk_s520_night2's key-set pin untouched).
- paper_desk_tick.py <= 300 lines (297), paper_desk_repo.py 45 lines.
- Live check after landing: the next tick journals `tick:repo_shallow` tick_ok/checked with
  git_answer false and the tick stays tick_ok.
- Risk stated: if `git` is missing from the scheduled task's PATH every tick refuses git_query_failed
  (fail closed, by design); a hanging git is bounded by the 30 s subprocess timeout (TimeoutExpired ->
  git_query_failed).

## 4. Non-goals

- (b) refusal attribution (the gates carry the commit sha + date they read) -- separate landing.
- No repair from the tick (an unshallow is an owner / session action; the tick only refuses).
- No night re-run; the night 10-20 scoreboard / E steps are closed by S825 commit B (10-23).

## 5. Tests (one process per file)

tests/platformkit/ops/test_paper_desk_s832_repo_shallow.py; tests/platformkit/ops/test_paper_desk_tick.py;
tests/platformkit/ops/test_paper_desk_r6_attention.py; tests/platformkit/ops/test_paper_desk_s520_night2.py;
tests/platformkit/ops/test_paper_desk_schedule_ack.py.

## 6. Tiers

Contract (VERIFIER_CONTRACT A/B/Q against this spec) and adversarial (probes: a `true` answer with
a worktree .git file, a hanging git, status.json recovery of the new row through recover_status,
the construct skip). Both Opus, foreground, one at a time.
