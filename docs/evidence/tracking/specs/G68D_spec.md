GAP G68D | sport basketball | worktree a4 | log cx_g68d_paint_census_aggregate
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. AGGREGATION ONLY. Label nothing new.
WHY THIS ROW EXISTS: the G68 basketball paint census is 1,650 tiles across 11 distinct-content
clips -- too much visual review for one session. Two whole-census attempts ran out, and the second
LOST 300 completed labels by holding them in context. The census was therefore split into chunks
(G68A, G68B, G68C), each writing one labels file per clip to
docs/evidence/tracking/g68_paint_census/labels/<clip>.csv, and each explicitly FORBIDDEN from
computing a pooled figure so that no chunk reports a partial denominator as if it were the census.
This row is the aggregation those chunks were told to leave alone.
PRECONDITION (check it first, and stop if it fails): all 11 clips must have a labels file, each
with 150 rows. Enumerate what you actually find and state it. **If any clip is missing, STOP and
report which** -- do not aggregate a partial census, and do not silently reduce the denominator.
That is the whole discipline this split was designed to protect.
The 11 distinct-content clips (content-hash deduped; names ending _1080p are NOT duplicates, the
hash table established them as distinct content):
  ncaa_basketball__ncaa_basketball_IB-_u4gW3ds, ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p,
  ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss, ncaa_basketball__ncaa_basketball_sRtHQbywiTE,
  ncaa_basketball__ncaa_basketball_tiUvyvWOCxo, ncaa_basketball__ncaa_basketball_zqBCKovJCQU,
  wnba__wnba_01, wnba__wnba_01_1080p, wnba__wnba_02, wnba__wnba_04, wnba__wnba_05
COMPUTE:
  (a) `paint_solvable_share` = PAINT_SOLVABLE / ALL sampled decoded frames, per clip, PER LEAGUE
      (NCAA vs WNBA) and pooled, each with a Wilson 95 pct interval. The denominator is every
      sampled tile, never "court frames only" -- conditioning it on the outcome is B1.
  (b) The COURT_NO_PAINT share, per league and pooled, reported as a RESULT IN ITS OWN RIGHT. It is
      the first honest measurement of the panning problem G04 named, not leftover.
  (c) Whether the PAINT_SOLVABLE tiles CLUSTER into a few static half-court stretches or spread
      across each clip. Use the frame indices in the labels files and say which it is, per clip.
      This matters as much as the headline: a solver that only works during a handful of dead-ball
      stretches is not a per-frame calibration route.
  (d) The seeded 20-tile full-resolution re-read of PAINT_SOLVABLE tiles, with the seed recorded
      and the FLIP COUNT reported. If a chunk already did this for its clips, aggregate the flips
      and say so rather than redoing it.
THE PRE-REGISTERED DECISION RULE, set before any tile was labelled and NOT to be moved now: if
pooled `paint_solvable_share` is below about 0.10, OR if the solvable frames cluster into a handful
of static stretches, the per-frame paint route is a LIMIT result and the role-assignment lane never
gets written. State the verdict explicitly in one sentence at the top of the memo.
CONTEXT you must state for the reader, because it is the comparison that matters: soccer's
equivalent census (G67) came in at **72/1,500 = 0.0480** [0.0383, 0.0600] and CLOSED AT LIMIT, and
soccer was ranked the MOST tractable of the four uncalibrated sports. If basketball comes in far
higher, that reverses the strategy's ranking and is the single most important tracking finding of
the week -- so report it precisely, with the interval, and resist rounding it up.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = paint_solvable_share per clip, per league, pooled, with Wilson intervals
  before        = an interim 162/300 on 2 of 11 clips, both NCAA -- explicitly NOT the census and
                  not to be quoted as it
  bar           = THERE IS NO PASS BAR. Success is the complete aggregation over all 11 clips with
                  stated denominators and the decision-rule verdict. High and low are equally good.
  n             = 1,650 tiles, 11 clips; state the per-clip counts you actually read
  eye check     = already done by the chunks; do not relabel. Any NEW claim about what a tile shows
                  needs you to look at it.
  must not move = every harness threshold, the coordinate contract, the pre-registered 0.10 rule,
                  and every chunk's labels. You aggregate; you do not re-judge a chunk's calls.
DURABILITY (A7): commit the aggregate table and the per-clip breakdown under
docs/evidence/tracking/g68_paint_census/ BEFORE reporting.
EVIDENCE: docs/evidence/tracking/g68_paint_solvable_share_2026-09-0X.md with the precondition
check, the per-clip / per-league / pooled shares with intervals, the COURT_NO_PAINT finding, the
clustering answer, the re-read flip count, the explicit decision-rule verdict, the comparison
against soccer's 0.0480, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only if at all. No scp, no deploy, never kill anything -- another session has live
processes there.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a4,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
