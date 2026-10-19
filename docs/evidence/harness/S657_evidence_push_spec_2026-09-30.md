GAP S657 | sport all (ops) | worktree nba-harness-h332 | log cx_s657_evidence_push
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q; self-check every line.
WHERE: local only (git + small json reads; tmp git repos in tests). No pod, no capture, no tick.
PREMISE (step 0): after a night the tick writes docs/evidence/forward/nights/<D>.json and its
step artifacts, but no process on the recorder box commits them (audit section 8: grep of the
ops and night modules finds no git call; today only the laptop Claude tasks commit). Verified
09-30: nights/2026-09-29.json and its 5 present artifacts are untracked or modified in the main
checkout. If a committer already exists on master, STOP and report FALSIFIED.
LIMIT (step 1): none measurable beyond git itself; the step can only publish what the night
record lists (steps[].artifacts[] with present true, plus the record).
CHANGE (step 2): NEW file scripts/platformkit/ops/evidence_push.py (+ its test) only. CLI:
`python -m scripts.platformkit.ops.evidence_push --date D [--root .] [--remote private]
[--branch trunk] [--dry-run]`. Order, each step refusing (exit 2, nothing staged) on failure:
 a. HEAD is a branch (not detached); the index is EMPTY (`git diff --cached` names nothing);
    tracked modifications outside the push set: none (untracked files are ignored).
 b. Read nights/<D>.json; the push set = that record + every steps[].artifacts[] path with
    present true. Every path must be relative, use "/", contain no "..", start with
    docs/evidence/forward/, and not end in RUNNER.lock; each file's sha256 must equal the
    recorded sha256 (the record itself has none).
 c. Keep only paths that are new or changed against HEAD; none -> exit 0 `nothing_to_push`.
 d. `git add -- <paths>`; the staged set must equal those paths exactly, else unstage them
    and exit 2. Commit with pathspec, subject `evidence: paper night <D> (<n> files)`.
 e. `git fetch <remote> <branch>`, `git rebase <remote>/<branch>`; on conflict `git rebase
    --abort` and exit 3 (the commit stays local for a human; nothing pushed).
 f. `git push <remote> HEAD:<branch>` (never a force flag); failure -> exit 4.
 --dry-run prints the push set and stops after c. Never `add -A`/`.`, never data/ or vault/.
ACCEPTANCE RULE (the verifier applies exactly this):
  metric        = construct cases in tests/platformkit/ops/test_evidence_push.py passing, on
                  tmp git repos (bare remote with branch trunk + a work clone), one pytest process
  before        = 0 (the module does not exist)
  bar           = all cases pass: (1) happy path pushes exactly record + present artifacts;
                  (2) a path outside docs/evidence/forward/ -> 2, index empty, remote unchanged;
                  (3) a "..": path -> 2; (4) a pre-staged foreign file -> 2, index unchanged;
                  (5) a foreign tracked modification -> 2; (6) sha mismatch -> 2; (7) remote
                  advanced without conflict -> rebased and pushed, remote tip = local tip;
                  (8) conflicting remote change -> 3, no rebase in progress, remote unchanged;
                  (9) all unchanged -> 0 nothing_to_push, no new commit; (10) present false and
                  RUNNER.lock never staged; (11) no git argv the module runs contains a force
                  flag, `-A`, `.` or `--all` (recorded through the module's git runner)
  n             = 11 (CONSTRUCT)
  eye check     = n/a (S-row); reproduction = run the one test file; read the pushed tree
  must not move = every existing file; the tick, config and seal-pinned files untouched
NON-TAUTOLOGY: cases 2-6 and 8 must fail on a module that stages without checking.
EVIDENCE: docs/evidence/harness/S657_evidence_push_memo_2026-09-30.md. PARKED, not wired into
the tick (tick files belong to the tick owner); <= 300 LOC per file; ASCII only.

AMENDMENT 1 (2026-09-30, pre-build Opus critic REVISE, all 12 items folded; simplest form each):
A1. Step a also fetches <remote> <branch> and refuses exit 5 `unpushed_local_commits` when
    <remote>/<branch>..HEAD is non-empty, and exit 5 `operation_in_progress` when a rebase or
    merge is in progress (.git/rebase-merge, rebase-apply, MERGE_HEAD). Cases 12, 13.
A2. An exit-3 run leaves its commit local; the next run exits 5. The memo names the one human
    step that clears it (resolve by hand, or `git reset --mixed <remote>/<branch>` after checking).
A3. Every git call runs with `-c core.autocrlf=false -c core.safecrlf=false`. Case 14: happy path
    in a clone with core.autocrlf=true keeps committed blob == file bytes == recorded sha.
A4. Reruns: the push set = every nights/<D>.json and nights/<D>.rN.json present, plus the
    artifacts of the HIGHEST revision only (rN with the largest N, else <D>.json). Case 15.
A5. A sha mismatch on a path under docs/evidence/forward/weeks/ (rewritten by every night of
    the week) is SKIPPED and printed `superseded`; a mismatch anywhere else refuses exit 2 (case 6).
A6. No night record for D -> exit 0 `record_absent` (nothing staged). Case 16.
A7. Any non-zero rebase: `git rebase --abort` only if a rebase directory exists, then exit 3
    (covers untracked-overwrite refusals, case 17). A commit the rebase drops as already
    upstream leaves HEAD == remote tip: exit 0.
A8. Step a refuses exit 2 `prepush_guard_absent` unless the resolved hooks/pre-push file exists
    and mentions prepush_guard (a fresh VM clone has no hook). Case 18: a hook that exits 1 ->
    exit 4, remote unchanged.
A9. Case 11 forbidden argv also: no-verify, -f, force-with-lease, mirror, any `+` refspec.
A10. Any failure after `git add` (e.g. commit fails: identity unset) unstages the paths, exit 2.
    Case 19.
A11. Cases 2-3 add a backslash path, an absolute path, and (where the OS allows) a symlink whose
    resolved target leaves <root>/docs/evidence/forward.
A12. Tracked-modification refusal lists the offending paths. Expected on the laptop (foreign
    edits in the checkout) -- a guard for the one-committer rule; on the VM a known source is
    issues/<D>.md rewritten in place by paper_desk_issues. Test repos pin core.hooksPath and
    core.autocrlf so no global config leaks in. n = 19 (CONSTRUCT).
