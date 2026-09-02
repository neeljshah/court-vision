# Paste-ready dispatch set for 2026-09-04

Companion to `TRACKING_DAY1_EXECUTION_PLAN_2026-09-04.md`. Every spec is a file
under `specs_2026-09-04/` so it is dispatched through a scratchpad read rather
than inline text (the PreToolUse hook scans command text, and the wrapper takes
a single-quoted argument that apostrophes would break). The specs directory is
under `docs/evidence/`, which is TRACKED, so every worktree gets the specs
automatically on sync -- no copy step, unlike `.planning/` and `docs/research/`.

**Declared deviation from `CODEX_SPEC_TEMPLATE.md`:** four specs run 43 to 47
lines against the 40-line cap. The overage is entirely premise numbers quoted
verbatim (the G25 containment vector, the G28 ffprobe durations, the fold-0
metrics, the three G17 bars) so codex does not re-derive or misremember them.
That trade was the point of the loop audit; it is declared here rather than
hidden.

---

## Dispatch commands (wave A, all six at session start)

    cd /c/Users/neelj/nba-ai-system
    S=docs/evidence/tracking/specs_2026-09-04

    ~/bin/codex-sport a5 g26b_tennis_player_limit  -- "$(cat $S/g26b_tennis_player_limit.txt)"
    ~/bin/codex-sport a6 g31b_tennis_fold1_eval    -- "$(cat $S/g31b_tennis_fold1_eval.txt)"
    ~/bin/codex-sport a9 g25b_bb_mask_sanity       -- "$(cat $S/g25b_bb_mask_sanity.txt)"
    ~/bin/codex-sport a2 g28b_siblings_duration    -- "$(cat $S/g28b_siblings_duration.txt)"
    ~/bin/codex-sport a7 g33_baseball_scale_bins   -- "$(cat $S/g33_baseball_scale_bins.txt)"
    ~/bin/codex-sport a3 g34_view_denominator      -- "$(cat $S/g34_view_denominator.txt)"

Wave B, as slots free:

    ~/bin/codex-sport a8 g17c_soccer_role_limit    -- "$(cat $S/g17c_soccer_role_limit.txt)"   # after the 300 labels exist
    ~/bin/codex-sport a4 g36_baseball_day_corpus   -- "$(cat $S/g36_baseball_day_corpus.txt)"  # ONLY if G33 says 360p is not dominant

Before each dispatch, sync that worktree to master, and apply the amended rule
3: refuse the reset if the tree is **dirty** as well as if `master..HEAD` is
non-empty. Today a5, a6 and a9 hold live work and must NOT be reset; a2, a3, a4,
a7 and a8 are safe (a2 is already at master, and a6/a8 carry only disposable
`findings.md` / `task_plan.md` scratch). Confirm each log grows within 2 minutes;
a log that never grows means the wrapper died, not that the job is thinking.

**a2 needs one extra step before dispatch:** cherry-pick tag
`g28-reject-9ba9d395e` into it. a2 was reset and the rejected G28 work that G28b
builds on is reachable from nothing else.

---

## Opus lane 1 -- label 300 soccer role crops (gates G17 v3)

Start this at session open, in parallel with wave A. It is the only thing wave B
blocks on.

Crop person boxes from the 100 sealed packet frames and the G08 stream windows,
and label each crop **player / referee / other** by eye into
`docs/evidence/tracking/soccer_roles_labels/`. Sample crops evenly across all
source frames, never a head slice, and never draw only from frames the current
detector already handles -- record the sampling rule in a `README.md` beside the
labels, with the seed and the source frame index for every crop. 300 labels,
roughly balanced enough that the minority class is not a rounding error. Do not
touch the sealed packet CSVs. When the directory holds 300 labeled crops and the
README, dispatch `g17c_soccer_role_limit`.

## Opus lane 2 -- G35 gap-finder pass (whenever an Opus lane idles)

Sweep every "NOT VERIFIED" section in the memos landed since 2026-09-01, plus
the pod ledger, and file measured rows for what nobody has checked. Candidates
already visible from today's read:

- the 24 unviewed G08 renders and its persistent/changed identity tally;
- whether the pod actually took the G22 deterministic detector branch (the
  manifest records the static string "G22 deterministic helper when available",
  not which branch ran);
- the cause strings behind `coordinate_contract passed:false` on both G12 keeps
  (this is research-plan row B5);
- the stale G29 register row, which still reads as open although G29b landed at
  7daae6c7c;
- G19 coast tagging: the pod tables carry no bbox columns, so the rule can only
  ever have fired on the off-frame branch.

At least 3 new rows, each with a measured number and an evidence path. Ids come
from `NEXT_GAP_ID` (G37 and up) and are allocated by the orchestrator only.

---

## Verifier quick card (apply the spec ACCEPTANCE RULE plus contract A and B, nothing else)

A rule that is not in the spec cannot be used to reject. If a verifier needs
one, it files a new gap instead. That single discipline is what 595k wasted
codex tokens bought.

- **A1** re-run the per-file test in **master**, not the worktree
- **A2** recompute the headline yourself; never quote the lane number
- **A3** sample renders **evenly** over the decision set (head slices are how a
  0.78 once showed as 0.93)
- **A4** count **uniqueness** (2,209 rows were 2,013 unique frames)
- **A5** grep every reader of every field the diff touches
- **A6** land by `git -C <wt> archive <sha> -- <paths> | tar -x -C <repo>`, then
  pathspec commit, then the ledger line, then the register row

Automatic rejects: **B1** circular metric, **B2** non-additive schema, **B3**
fall-through loss (missing is not bad), **B4** re-claim loop, **B5**
pre-verification pod deploy, **B6** orphaned test or import, **B7** head-slice
evidence, **B8** self-fit presented as independent, **B9** degenerate
denominator, **B10** a moved bar.

Verdicts: ACCEPT | ACCEPT WITH CORRECTIONS | NOT VALIDATED (land unused, zero
callers) | REJECT (queue a named fix pass) | CLOSED AT LIMIT (no retry). Every
verdict writes exactly one `RESULTS_LEDGER.md` line and one register row.

**Expected verdicts today, so nobody reads them as failure:** G31 fold 1 is
expected to come back CLOSED AT LIMIT (fold 0 already returns
`frames_ge_4_in_7 = 0.0`), and G17 v3 closes soccer count features AT LIMIT if
any of its three bars is missed. Both are successes and both get ledger lines.
