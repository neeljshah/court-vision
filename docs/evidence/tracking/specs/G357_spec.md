GAP G357 | sport basketball | worktree a2 | log cx_g357_ball_ownership_px_attempt2

**ATTEMPT-2 ROW FOR G349 ON THE DEPLOYED G354 PIXEL FIELDS. Codex PREPARES, a finisher MEASURES once enough
post-deploy clips exist.** `src/`, `kernel/`, `api/` and `intel/` are READ and IMPORT only. Build in
`scripts/platformkit/tracking/` on the landed G339 join (`ball_join.py`), the landed G344 state machine
(`ball_shadow_possession.py`, thresholds sealed) and the landed G349 survival table (`g349_ball_survival.py`).
NEVER write `data/registry/`, never flip a flag, never loosen the sealed 60 px ownership radius or any G344
threshold, never touch `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.

**WHERE THIS ROW RUNS:** LOCAL (conda `basketball_ai`; per-window batched reads; check free RAM first) on
tracking tables fetched READ-ONLY from the pod (`scp` of `tracking_data.csv` + `ball_tracking.csv` per clip
into local scratch outside the repo; never write on the pod; never touch the daemon or guards; the corpus
rotates: a vanished clip is ABSENT).

**WHY THIS ROW EXISTS.** G349 located where the ball evidence dies (player_within_radius: 8 of 1,560 frames)
and G351 explained it (ball table in court-map units, players in raw pixels on 214 of 356 clips). G354
(2026-09-08T21:51:26Z) deployed ADDITIVE `ball_x2d_px` / `ball_y2d_px` at the producer; on 4 fresh clips the
60 px re-join rose from 211/764, 2/483, 178/306, 0/631 to 345/975, 153/796, 221/373, 8/937. G349's resealed
evaluation was NOT VALIDATED (list assembled in the result commit; 6 of 100 eligible pairs). This row runs
G349's step 3 properly: a list SEALED BEFORE the result on post-epoch clips only, joined on the px fields.

**PREMISE (step 0, BINDING before-condition):** count pod ledger clips whose tracking STARTED after epoch
1788904286 (the G354 deploy; `finished_at` is NOT the key) and whose ball table header carries both px
fields; print n clips, n games, n competitions (NBA / WNBA / other). **If fewer than 30 windows from >= 3
games including 2 basketball competitions are available, the codex lane still prepares; the FINISHER waits
(polling the ledger every 15 min for up to 6 h) and reports PARTIAL with the counts if the sealed minimum is
not reached in that window.**

METHOD:
  1. **SEALED LIST (finisher, Q1):** the first >= 30 eligible 2 s windows (the G344 window rule) from >= 3
     games and 2 competitions in ledger order, each by full path + sha256 + byte size, committed as its own
     commit BEFORE any state machine runs; the sealed list must reach >= 100 eligible observed-ball motion
     pairs overall (report the count; if short, PARTIAL).
  2. **JOIN ON PX (`g357_px_join.py`, <= 200 lines, additive):** the G339 join with the ball point taken from
     `ball_x2d_px` / `ball_y2d_px` when present (`join_source=px`), never from the court-map columns; rows
     without the px fields are excluded with a counted reason; the G351 ratio rule per clip as a sanity
     print (ratio <= 1.5 both axes).
  3. **SURVIVAL + STATE MACHINE:** the G349 survival table per stage (frames F; any ball row; detected ball;
     player rows; player within the sealed 60 px radius; motion pairs with 3-frame history; motion
     agreement; accepted ownership) per window and pooled; then the landed G344 state machine UNCHANGED and
     the +/- 1 s shuffle control; full-frame AND eligible-pair denominators together; observed vs inferred
     ball rows ablated.
  4. **BEFORE / AFTER:** the same windows scored through the OLD join (court-map columns) for the survival
     table only (the unit defect made visible on the same frames).
  5. CHANGE NOTHING ELSE. No consumer wiring; no threshold moves.

**HONEST LIMITATIONS to state, not discover:** coverage and shuffle response establish sensitivity, not
ownership correctness; nearest player is not the handler; post-epoch clips are whatever the feeder shipped
(not a designed sample); if support stays sparse the deliverable is missingness / age indicators.

ACCEPTANCE RULE:
  metric        = the sealed list (n windows, n games, n competitions, n eligible pairs); the survival
                  table per stage with n (px join vs old join); ownership share of F and of eligible pairs;
                  motion agreement; shuffle delta vs the sealed 20 pp bar
  before        = G344: owner 1/1,560, shuffle flat; G349: in-radius 8/1,560; G354: re-join 8 to 345 per
                  window on 4 clips
  bar           = list sealed before the result (commit order); >= 30 windows / >= 3 games / 2
                  competitions / >= 100 motion pairs (met or PARTIAL); every stage has n; both denominators;
                  the shuffle bar applied as sealed (met or not); 0 threshold moves; 0 src edits
  n             = >= 30 windows; every frame; every motion pair
  eye check     = NONE. Say that.
  must not move = `src/`, `data/`, `data/registry/`, every G344 threshold, the 60 px radius, every flag,
                  every landed artifact, `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`
  verdict       = **DONE** with the located result if the bar holds; **PARTIAL** naming what could not run
                  (including "fewer than 30 post-epoch windows by <UTC>").
EVIDENCE: `docs/evidence/tracking/g357_ball_ownership_px_attempt2_2026-09-08.md` (<= 60 lines; VERDICT line 1;
tables; NOT VERIFIED; wall time; SHA-256s) + `.../g357_ball_ownership_px_attempt2_2026-09-08/sealed_windows.csv`,
`survival.csv`, `states.csv` (integer cells zero-padded; shares as ADDITIVE per-mille columns; never rename or
remove a column). **ADD ONE RESULTS_LEDGER.md ROW IN THE SAME COMMIT** (append only). **Do NOT edit
`docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md`.**
TEST: `tests/platformkit/test_g357_px_join.py` plus `tests/platformkit/test_g349_ball_survival.py` and
`tests/platformkit/test_g344_ball_shadow_possession.py`, each alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the epoch rule, the window rule, the px
join rule, the denominators, the shuffle bar), the px join module, the tests and the memo skeleton, and exits
with the line `agent: PREPARED FOR FINISHER` plus the exact fetch and run commands in `python -m` form; it
must NOT fetch or run real windows (Q1). Absent `data/registry` in the worktree is reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
