# Codex push 2026-10-02 -- index

PAPER ONLY. Calibration and execution-quality language only. This directory holds the tracked subset of one day's
multi-model review, build and planning push on the paper desk (owner directive 13:25Z and 16:15Z 2026-10-02). The
orchestrator was a Claude session; the workers were codex lanes on four model tiers (astra for plans, reviews of
plans and verification; three sol and terra tiers for builds, fixes, branch reviews and web research). Nothing in
this directory was landed as code: it is evidence and planning. Statements in these files are dated observations,
not proof of current runtime health.

## Read first

0. `OWNER_BRIEF.md` -- the three things only the owner can do this week, deadlines, and pick-one decisions.
   `LANDING_BOARD.md` -- one line per row with its candidate, latest verify verdict and readiness, plus the strictly
   ordered landing queue (seven rows ready, twelve ready after a named small fix). Nothing on the board was landed
   by this push: an automated lander launch was refused by the permission layer, so landing is the owner's call.
   The FINAL PLAN that supersedes `MASTER_PLAN_V2.md` (it answers a cross-model critique point by point and makes
   the seven-day schedule executable) is local-only on the recorder laptop at
   `.planning/codex_push_2026-10-02/out/px_g1.md`, with the critique at `px_e4.md` and plan v3 at `px_e2.md`.
1. `MASTER_PLAN_V2.md` -- the synthesized plan: where the desk stands, the one binding constraint and its fix order,
   the next seven days, twelve weekly milestones, the ranked backlog, owner decisions, what to stop, top risks.
   Superseded by the local FINAL PLAN where they differ (soccer slot dates, the S720 dispatch premise, the size of
   the day-three integration, three backlog items replaced).
2. `STATUS_TABLE.md` -- one line per row touched today: cross-family review verdict, Windows test result on the
   cloud branch tip, candidate branch, verify rounds, status (generated at commit time; later rounds continue).
3. `REVIEW_r1.md` .. `REVIEW_r4.md` -- independent pre-landing reviews of the unlanded `private/cloud/S6xx-S7xx`
   branches by a different model family from their builders and verifiers. Two more review files and three plan
   files are kept local-only (see the last section).
4. `WINDOWS_INTEGRATION_TESTS.md` -- every cloud branch merged into a TEST-ONLY worktree and its own tests run one
   file at a time on Windows / Python 3.10. The integration branch used union merges on append-only files and must
   never be landed.

## What the day found

- Six cross-family reviews covered fifty unlanded cloud branches that had each passed two verifier tiers of one
  model family: seven came back landable as written, the rest carried file-and-line defects (fail-open gates, tests
  without power, Windows-only failures, success statuses without artifacts).
- Landable as reviewed and green on Windows: S594, S631, S666, S679, S688. S696 and S699 are clean by review but
  fail on Windows until the corrected S691 lands (the journal is written with CRLF and refused as not canonical).
- Qualification: the adapter compares a fresh ladder by exact equality with an older discovery quote and refuses
  the row; the refusals feed three of the four qualification failure reasons (row S720). The S720 counterfactual
  replay is an honest null on the assessable games: correcting provenance alone does not make them qualify.
- Night path: qualification hit its 900 s deadline on night 09-30 and left a zero-byte canonical file that later
  ticks accept; partial nights are terminal; unresolved nights age out; several steps exit zero while refused
  (rows S711-S716, `SILENT_FAILURE_AUDIT.md`, `TICK_BUG_HUNT.md`).
- Capture: a low-RAM launch refusal at resume started a cause-blind sixty-minute backoff; all three captures were
  down from 13:29Z to 14:56Z on 2026-10-02 (row S717).
- Execution: the paper fill record does not yet transfer to a real venue (zero submit and cancel latency in the
  fill-realism runs, fills inferred from book crossings, no completed weekly record): `EXECUTION_QUALITY_REVIEW.md`.
- Calibration: nightly estimands reset their population each night, so the thirty-game floors are not reached by
  accumulating nights; an additive pooled design is proposed, unsealed (row S721): `CALIBRATION_REVIEW.md`.

## Candidates (local branches on the recorder laptop, not landed)

- `cxf/<ID>-2026-10-02`: a corrected candidate cut from `private/cloud/<ID>-<date>`, with the review section it
  answers in `docs/evidence/harness/<ID>_codex_review_2026-10-02.md` and the fix memo beside it on that branch.
- `cxp/<ID>-2026-10-02`: a new spec + build for rows S673, S704, S706, S711-S724, S597 part 2, S558, S680.
- Every candidate went to an independent astra verifier that ran its tests; a REJECT went to a fix round and a
  re-verify, at most three rounds. A candidate is ready only when `STATUS_TABLE.md` (or a later regeneration) says
  verified ACCEPT; a builder's or fixer's own report never clears a row.
- `BUILDER_DISPATCH_LIST.md` lists fourteen collision-free specs prepared for later building. They were NOT
  dispatched: the master plan's first stop item is to hold new implementation branches while correction and
  landing capacity are saturated.

## Kept local-only on the recorder laptop

Under `.planning/codex_push_2026-10-02/out/` (never pushed): all ten topic plans, the eight wave-two critiques with
builder specs, the conflict and coverage report, eight web-research memos and their source re-checks, the
qualification root-cause tables, the ranked backlog, the red-team pre-mortem, two of the six branch reviews, and
every lane's raw output. The backlog, the pre-mortem and two reviews are verbatim records that the repository's
vocabulary scan flags on an ordinary rank or count, so they were not copied here rather than re-encoded.
