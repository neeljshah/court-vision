# INEFFICIENCY -- Same-day freshness gap (P1-adjacent; the one UNMODELED accuracy lever)
_Per-pocket detection-recipe deep file. Cross-sport, deepest on NBA + MLB. The crack is the
information our HISTORICAL-box model cannot see at slate lock. Grounded in the sim's unfed
out_ids hook (src/sim/basketball_sim.py:95-103) + the missing lineup/pitcher feeds (deep-dives
08, 05, 12). ASCII only. No $-edge claims._

## MECHANISM (why the crack exists)
Our predictors are parameterized on SEASON / recency BOX rates. The closing line prices things
those rates cannot see at lock time: confirmed starting lineups, late scratches / load
management, the actual starting pitcher and bullpen state, projected minutes. This is the
deepest project finding (cut-list KEEP/PUSH; deep-dive 08 sec 7): PTS/REB are at the historical-
data ceiling -- the remaining accuracy lever is NOT more chain mechanics, it is SAME-DAY
FRESHNESS. The crack is two-sided:
- vs OUR MODEL: a stale recency average is simply wrong about minutes/usage for 1-2 games after
  an availability change -> our own prediction is improvable.
- vs the SOFT LINE: the EDGE only exists where the soft/DFS book ALSO lags the same news (a slow
  prop board that has not re-pulled after a 5pm scratch). Where the book is fresh and we are
  stale, the gap is OUR error, not an edge. The pocket is the INTERSECTION: news is out, we
  ingest it, the soft line has not moved yet.

The decisive mechanism in NBA: when a high-usage starter is OUT, the scoring pie re-routes.
The starter's own props collapse to ~0; teammates absorb usage and minutes. A possession sim
captures this CORRECTLY by construction if it is told who is out -- which is exactly the unfed
hook below. In MLB the analogue is the confirmed starting pitcher + bullpen availability (the
single largest same-day driver of totals and Ks); in soccer it is the confirmed XI; in tennis it
is withdrawals / fitness news.

## CONCRETE DETECTION RECIPE (exact data + query + threshold)
THE HOOK (NBA, exists, currently UNFED): `TeamModel.from_cache(tri, ..., out_ids=...)`
(basketball_sim.py:95). Per the docstring (l.96-98): out_ids = same-day-unavailable player ids;
they are dropped from the rotation, "lineups re-filtered, minutes/usage/rest re-normalized, the
anchor re-pins the survivors." Default `out_ids=None` -> BYTE-IDENTICAL (no behavior unless fed).
So the freshness lever is BUILT but the same-day feed that should populate it is the missing
piece (08:212: "Injuries/availability only enter via the manual out_ids list").

Recipe (NBA):
1. At slate lock, ingest tonight's confirmed-OUT list (timestamped < tip) -> `out_ids`.
2. Build TWO priced runs from one sim path: STALE = `from_cache(tri)` (out_ids=None) and FRESH =
   `from_cache(tri, out_ids=tonight_out)`. Both -> `simulate_game_fast(...)`.
3. The freshness signal per player = `fresh_pred - stale_pred`. Largest, most reliable moves:
   (a) a scratched starter's own props -> ~0 (trivially correct), and (b) the USAGE-BUMP on his
   teammates (the pie re-routes). Flag a teammate where `|fresh_pred - book_line| >= TAU` while
   `|stale_pred - book_line| < TAU` -- i.e. ONLY freshness opens the gap. Start TAU at the
   model's own per-stat noise band (do not tune on outcomes -- proof-standards SELECTION trap).
4. Cross-check the book is actually STALE: the prop line's `as_of` (PropLine schema) predates the
   scratch news timestamp. If the book already moved, there is no edge -- it is just our catch-up.

Existing partial implementations to reuse / not duplicate:
- `scripts/apply_teammate_out.py` -- a POST-prediction redistribution pass (the model has no
  teammate_out feature) using series-average MPG as redistribution weights; reads
  `data/injuries_<date>.json`. This is the crude analogue of the out_ids re-route; the sim hook
  does it coherently instead.
- `scripts/analysis_opener_freshness_pts_reb.py` -- a READ-ONLY leak-free analysis already asking
  the exact proof question: is model-vs-OPENER positive for PTS/REB, and does applying the FRESH
  availability vac-bump (src.prediction.live_adjustment.adjust_projection, gated on
  vac_min_share + vac_stats) before grading move it? It grades opener-only games too and reports
  ROI@opener, ROI@close, CLV (line-points + beat_close%) with a bootstrap CI. This is the
  template for the proof below.

MLB recipe (analogue): the same-day feed is the CONFIRMED starting pitcher + lineup. The crack
is a soft total/K-prop posted off a probable that changed. Detection: diff the confirmed starter
vs the probable our model assumed; re-price with the confirmed starter's rates; flag where only
the confirmation opens a gap and the book `as_of` predates the confirmation. (deep-dive 05/12.)

## PROOF METHOD (which leak-free check + which metric)
- LEAK-FREE WALK-FORWARD vs the CLOSE (not vs prior model). The OUT/lineup feed MUST be
  snapshotted with timestamp < tip and STORED PER-DATE, so a backtest sees exactly what was
  knowable at lock. Then score the freshness-adjusted prediction's P(over) calibration vs the
  devigged prop close (Brier / BSS). BSS>0 vs the close on the freshness-affected subset =
  CALIBRATION-PROVEN. The discipline: the gap must be vs the CLOSE, because beating our own
  stale model is trivial and not an edge (analysis_opener_freshness asks precisely model-vs-
  OPENER and model-vs-CLOSE separately for this reason).
- TRAIN/INFERENCE PARITY IS MANDATORY (proof-standards rule 1; the most expensive bug class).
  If freshness enters at inference (out_ids) it must also be reconstructable as-of in the
  training/backtest builder, or the feature silently reads its default and the lift is fake.
- CLV: log freshness-driven takes via prop_line_history and accrue forward CLV vs the prop close.
  Real money gated on positive forward CLV at a meaningful sample (small-N is noise).
- Restrict scoring to the FRESHNESS-AFFECTED subset (games with a confirmed availability change);
  diluting into all games hides the signal and risks a selection wash.

## MAGNITUDE (honest)
The largest, most certain piece is mechanical (a scratched player's own line -> ~0) and is
likely ALREADY priced by any half-awake book -> little edge there. The real, uncertain magnitude
is the TEAMMATE usage re-route in the 1-2 game window before recency catches up -- documented as
a real accuracy lever (recency WF cut playoff over-prediction +0.98 -> +0.11, 08:142) but its
edge-vs-CLOSE is UNMEASURED. Honest statement: this is the HIGHEST-VALUE lever by hypothesis
(it is the one thing the close sees that our static model does not), but it is entirely
HYPOTHESIS until the as-of feed exists and the WF-vs-close runs.

## HONEST CAVEAT / FAILURE MODES
- BLOCKED ON THE FEED. The out_ids hook is built but the timestamped, stored-per-date same-day
  availability feed is the missing dependency (08:212; nba inefficiency-catalog N2 "blocked on
  the missing same-day feed"). Without per-date snapshots, any backtest is unverifiable / leaky.
- THE BOOK IS OFTEN FRESH TOO. Soft books increasingly auto-pull injury news; the edge survives
  only in the shrinking window where WE ingest faster than THEY reprice. The `as_of`-predates-
  news gate is what separates edge from our own catch-up; without it, do not claim a gap.
- LEAK RISK IS ACUTE HERE. Using the FINAL confirmed-OUT list to grade a game whose line you
  pulled BEFORE confirmation is a classic future-leak. Snapshot timestamps are not optional.
- TINY, BURSTY SAMPLE. Confirmed availability changes are infrequent per slate; N accrues slowly
  -> long horizon to CLV-PROVEN; resist promoting on a handful of dramatic-scratch nights.
- NOT A STANDING TEAM-MARKET EDGE. cut-list CUT-1/2: pregame team strength matches the close.
  Freshness is a PROP / usage-routing lever, not a license to bet team mainlines.

## TIER
HYPOTHESIS (highest-value). The mechanism is sound and the sim hook + crude redistribution +
the leak-free analysis harness all EXIST; what is missing is the stored, timestamped same-day
feed and the WF-vs-close run on the freshness-affected subset with train/inference parity. First
milestone: stand up the per-date OUT/lineup/pitcher snapshot -> wire out_ids in BOTH builders ->
run the analysis_opener_freshness-style WF vs the CLOSE -> CALIBRATION-PROVEN only if BSS>0 vs
the close on the affected subset; then forward CLV for the real-money tier.
