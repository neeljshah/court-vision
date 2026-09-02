GAP G68B | sport basketball | worktree a8 | log cx_g68b_paint_labels  (CHUNK of G68 -- label ONLY the clips named below)
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. PURE CENSUS. No detector runs. No solver is written.
WHY THIS ROW EXISTS: G47 established that the blocker for 4 of 8 sports is CALIBRATION, not tracking
quality -- 119 of 187 harness reports were rejected on coordinate_contract alone, before coverage,
oob or jump could say anything, and all of those rejections are LEGITIMATE (producers correctly
declare image_px, and image_px can never pass court_feet). The calibration strategy
(docs/evidence/tracking/CALIBRATION_STRATEGY_2026-09-02.md -- READ IT FIRST) ranks basketball SECOND
of four for tractability: the paint is a known APERIODIC rectangle, which is exactly what football's
periodic yard lines are not, and domains/basketball/tracking/line_calibration.py already carries the
4-line solver plus both rule-set tables (nba_wnba, ncaa_legacy). Three pieces are missing: line ROLE
assignment, an independent validation landmark, and the persisted per-frame homography sidecar the
rejection string names.
Before any of those is built, this row answers the question that decides whether they are worth
building: how much of a real broadcast actually shows a fittable paint.
METRIC: `paint_solvable_share` = frames where all four lane lines of ONE paint (baseline, free-throw
line, and both lane sides) are discernible with fittable extent, divided by ALL sampled decoded
frames.
  - Secondary labels per tile, mutually exclusive: PAINT_SOLVABLE / COURT_NO_PAINT (a live court
    view where the paint is not fittable -- pans, midcourt) / NON_COURT.
  - Report per clip AND per league (NCAA vs WNBA) AND pooled, each with a Wilson 95 pct interval.
    The league split matters because the lane width is CALLER-DECLARED (the two rule tables differ)
    and the two corpora may differ in camera style.
DENOMINATOR: ALL sampled decoded frames. Never "court frames only" and never "frames a detector
accepted" -- conditioning the denominator on the outcome is B1 and this program has already been
bitten by it (G40). The COURT_NO_PAINT share is itself the first honest measurement of the panning
problem G04 named, so report it as a result in its own right rather than as leftover.
ATTEMPT 2 -- the two NCAA clips of this chunk are ALREADY DONE and committed (tiUvyvWOCxo and zqBCKovJCQU, 150 rows each). Do NOT relabel them. YOUR REMAINING CLIPS ARE THE TWO WNBA ONES ONLY. YOUR CHUNK -- READ THIS FIRST. G68 is 1,650 tiles, which is too much visual review for one
session: two attempts ran out mid-way and the second LOST 300 completed tile labels because it held
them in context instead of writing them down. The census is therefore split by clip, and YOUR clips
are exactly these and no others:
     wnba__wnba_01, wnba__wnba_01_1080p
The contact sheets already exist at docs/evidence/tracking/g68_paint_census/contact_sheets/<clip>/
-- the dedupe and rendering are DONE (11 distinct-content clip sets, content-hash verified). Do NOT
re-render and do NOT re-dedupe. Note that names ending _1080p are NOT duplicates to be dropped: the
hash table already established these 11 as distinct content, so label them.
WRITE LABELS INCREMENTALLY, one file per clip, at
docs/evidence/tracking/g68_paint_census/labels/<clip>.csv, and write each clip's file BEFORE
starting the next clip. This is the single most important instruction in this spec: a label you
have not written down is a label that will be lost.
Report per clip and for your chunk. Do NOT compute a pooled figure across all 11 clips or state the
decision-rule verdict -- an aggregation lane does that once every chunk has landed.
SAMPLING (already done for you): the distinct-content basketball clips on the pod (6 NCAA + 5 WNBA per
docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md). **Dedupe resolution siblings by CONTENT HASH
first** -- that is the G28/G30 lesson, and counting the same match twice at two resolutions would
inflate n and correlate the tiles. Per clip stride = total_frames // 150, indices 0, s, 2s, ... for
150 tiles; about 1,650 tiles total. State total_frames and stride per clip, and state which clips
the dedupe removed and why.
EYE CHECK: every tile is viewed and labelled -- that IS the measurement. Then take a SEEDED random
20-tile subsample of PAINT_SOLVABLE and re-read those at full resolution to confirm the tile-scale
judgment. Record the seed and report how many calls the re-read flipped. A high flip rate is a
finding about the method and must be reported, not smoothed over. (Note the G65 precedent from
today: a lane reviewed whole frames at too low a zoom and returned 100 pct uncertain; zoom is not a
detail.)
DECISION RULE, pre-registered here BEFORE measuring so it cannot be moved afterwards: if pooled
`paint_solvable_share` is below about 0.10, OR if the solvable frames cluster into a handful of
static half-court stretches rather than spreading across the clip (the contact sheets make this
visible, so say which it is), then the per-frame paint route is a LIMIT result and the
role-assignment lane never gets written. A low number is a successful outcome for this row.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = paint_solvable_share per clip, per league and pooled, with Wilson 95 pct intervals
  before        = never measured
  bar           = THERE IS NO PASS BAR. Success is an exhaustive, viewed, reproducible census with
                  stated denominators. High and low are equally good answers.
  n             = about 1,650 tiles, none skipped; state per-clip counts and the post-dedupe clip list
  eye check     = all tiles plus the seeded 20-tile full-res re-read, with the flip count
  must not move = every harness threshold, the coordinate contract, and every existing verdict.
                  This row runs NO detector and writes NO solver.
DURABILITY (A7): contact sheets with BURNED-IN frame indices, the per-tile label file, the dedupe
hash table and the seed all go under docs/evidence/tracking/g68_paint_census/ BEFORE you report.
Never /tmp -- evidence there has already been destroyed twice (G54).
FOOTAGE: basketball footage is POD-ONLY. Run the census read-only on the pod.
EVIDENCE: docs/evidence/tracking/g68_paint_solvable_share_2026-09-0X.md with the per-clip, per-league
and pooled shares with intervals, the dedupe result, the stride and total_frames per clip, the
COURT_NO_PAINT share as its own finding, the re-read flip count, whether solvable frames cluster,
the decision-rule verdict stated explicitly, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
