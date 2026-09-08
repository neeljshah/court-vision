# G304 attempt 2 -- proposal generation + rater packets (BUILD MEMO)

Builder lane, worktree a11. GENERATED proposals and PREPARED rater packets; RATED NOTHING and
DISPATCHED NOTHING. Measures NO registration, NO calibration, NO tracking quality; states no
boundary claim. `domains/` imported, never edited. ENTIRELY LOCAL -- no pod, no GPU, no
`pod_run`, so there is no pod log to tail. cv2 4.11.0, Python 3.10.0. PREREGISTRATION
`g304_proposal_verify_prereg_2026-09-07.md` committed ALONE at `d625f272d` (seal
78f1a4f2b78245ec151bb4ba4e1b690a16efbbdd0aff02ab08d9af4c7bd41335); AMENDMENT 1 ALONE at
`7ca3a692a` (seal 3d60dcda526c14e78b1f1a98ca0c4d4e72c3f928f96fb426f0fac18b4a322696).

## GENERATED
63 ELIGIBLE frames (Gateway Center 29, Climate Pledge 34), native 1920x1080 renders read
read-only from worktree a4 (`a6fa18878`, `346b976a3`). 756 proposals = 63 x the cap of 12;
EVERY frame hit the cap. Crops: 756 JPEGs, 23.1 MB, quality 85, LOCAL ONLY under
`g304_proposal_crops/` (uncommitted; the numbers behind them are committed).
  by arena  Gateway Center 348 | Climate Pledge 408
  by source lsd_intersect 378 | shitomasi 378 | semantic 0 (Gateway 174/174, Climate 204/204)
VOCABULARY COVERAGE PER FRAME: median 8 distinct names (min 6, max 9); median 4 distinct marking
structures (min 3, max 4). 63/63 frames carry proposals across >= 3 structures, so the E1-ready
frame rule is REACHABLE on every frame -- whether it is REACHED is the raters' answer, not this
row's. 4 of 15 names were never proposed: CENTER_CIRCLE_TOP/BOTTOM (preregistered as
structurally unreachable) plus LANE_BASE_R and FT_LINE_R, reachable only via the semantic family.

## AMENDMENT 1 (made before any rating existed)
Pre-cap yields over the 63 frames: lsd_intersect 5772, shitomasi 5040, semantic 0. Under the
originally sealed rule the cap kept only 35 lsd_intersect against 721 shitomasi -- 0.6 percent of
the precise family -- because the families' scores are not on a comparable scale (shitomasi starts
at 0.99 by construction, lsd_intersect sits near 0.1-0.3). The rule now interleaves families
before names; re-sealed, run redone, split now exactly 378/378. NO PROPOSAL HAD BEEN RATED AND NO
RATER DISPATCHED when the amendment was made. Scores were NOT renormalised. THE SEMANTIC PROVIDER
ABSTAINED ON 63 OF 63 FRAMES -- consistent with the abstention G227 already measured, not a failure
of this row, but this attempt rests on TWO families, not three.

## TESTS
`python -m pytest tests/platformkit/tracking/test_g304_proposals.py -q` -> 5 passed, 1.51 s.
Synthetic four-line court (2 shallow x 2 steep = 4 known intersections): all 4 recovered within
3 px, max error 1.76 px measured. Also pinned: cap 12, dedupe 5 px, cross angle 25 deg, 15 names
over 6 structures, three `name_for` cells, per-family rotation, the Amendment 1 split (6/6 of a
12 cap). `g304_proposals.py` 263 LOC, under the 300 rail.

## NOT VERIFIED
- NO PROPOSAL IS A LANDMARK. Every name is a MACHINE HYPOTHESIS from a positional table; wrong
  names are expected. Nothing is validated until both raters decide and every difference is adjudicated.
- Arena identities are TRANSCRIBED from the a4 inventories, not re-confirmed by eye here.
- Eligibility is as classified by `gpt-5.6-sol` (a MODEL, not a human); not re-derived here.
- Both raters are MODELS, not humans. Agreement alone never establishes correctness, and
  unresolved labels mean INSTRUMENT NOT VALIDATED -- neither omitted frames nor abstentions.
- Proposal PRECISION is verified only on a synthetic drawn court, never on broadcast frames.
- The one crop inspected by eye (`wnba_01_01_p03`, FT_LINE_L) marks glare, not a line; n=1.

## DISPATCH LINES FOR THE ORCHESTRATOR (this lane dispatches neither)
  CODEX_BIN=$(ls -1dt /c/Users/neelj/AppData/Local/OpenAI/Codex/bin/*/codex.exe | head -1)
  PYW=/c/Users/neelj/AppData/Local/Programs/Python/Python310/pythonw.exe
  P="You are ONE of two independent raters for tracking row G304 attempt 2. Read C:/Users/neelj/nba-track-a11/docs/evidence/tracking/g304_rater_instructions_2026-09-07.md IN FULL and obey every rule in it. Rate all 756 rows of C:/Users/neelj/nba-track-a11/docs/evidence/tracking/g304_crop_manifest_2026-09-07.csv by opening each crop_path image. Binary ACCEPT/REJECT only, nudges <= 8 px with a reason_code, NO spatial prose, NO coordinates. Write the six-column CSV into YOUR worktree and commit it by explicit pathspec. Do not write into a11, do not push, never use --force."
RATER A (gpt-5.6-terra, worktree a3):
  "$PYW" /c/Users/neelj/bin/hidden_launch2.py --log /c/Users/neelj/AppData/Local/Temp/cx_g304_rateA.log --cwd /c/Users/neelj/nba-track-a3 --tag g304_rateA --env 'CODEX_HOME=C:\Users\neelj\.codex-a3' -- "$CODEX_BIN" exec --skip-git-repo-check --sandbox workspace-write --model gpt-5.6-terra -- "$P"
RATER B (gpt-5.6-sol, worktree a7):
  "$PYW" /c/Users/neelj/bin/hidden_launch2.py --log /c/Users/neelj/AppData/Local/Temp/cx_g304_rateB.log --cwd /c/Users/neelj/nba-track-a7 --tag g304_rateB --env 'CODEX_HOME=C:\Users\neelj\.codex-a7' -- "$CODEX_BIN" exec --skip-git-repo-check --sandbox workspace-write --model gpt-5.6-sol -- "$P"
