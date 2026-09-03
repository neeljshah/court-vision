GAP S220 | sport mlb (in-game) | worktree aXX | log cx_s220_mlb_event_lead_time
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S96 measured the NBA in-play line UNDER-reacting to scoring events and drifting (slopes +0.23 / +0.30 / +0.48
  at k = 3/5/10) with a positive placebo on non-event ticks. The same quantity has never been measured for MLB, where
  the state feed is fastest (GUMBO sub-250 ms, poll floor 5 s) and the price tick is slow (p50 31.0 s / p90 82.0 s,
  INGAME_CAPABILITY). INGAME_GAP_MAP names this L7 and L10; both are unrun.
PREMISE (step 0): re-measure and print: the MLB tick p50 31.0 s / p90 82.0 s over 371 games / 79,441 ticks; the GUMBO
  poller's captured_at and ts stamping; and the GUMBO event rows on disk joining an MLB in-play tick within +/- 120 s,
  with their cluster count. gumbo_live held 1 file on 2026-09-04, so the stream may be too thin: if fewer than 30
  clusters join, report FALSIFIED and name S217 and Neel's S62 row 3 as the blockers.
LIMIT (step 1): the lead time is bounded below by our own tick cadence -- we cannot observe a line move faster than
  the p50 31.0 s at which we sample it. Print that observation floor beside every quantile; any lead time below it is
  unresolvable by this corpus rather than absent, and if fewer than 30 clusters join report CLOSED AT LIMIT.
CHANGE (step 2): smallest additive change -- one new read-only module under scripts/platformkit/ingame/ joining the
  GUMBO event rows to the tick stream and emitting the lead-time distribution per event class plus a matched placebo.
  No arm, no Brier, no prereg, no charge. Rails: additive only, nothing renamed; helper <= 300 lines (LOC rail
  test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/
  intel/ scripts/team_system/; one store at a time via metadata or one row group, never > 300 MB (the box RAM guard
  kills python over 800 MB); register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per event class (run scored, out recorded, pitching change) the lead time from the event ts to the
                  first line move beyond a FROZEN threshold, p50 / p90 / max seconds, with a matched non-event
                  placebo; denominator = the printed joined-event count per class
  before        = 0 -- no MLB event-to-price lead time exists on record; the nearest measurement is S96's NBA drift
                  slopes +0.23 / +0.30 / +0.48 at k = 3/5/10 with a positive placebo
  bar           = 3 of 3 event classes reported with n, lead-time p50 / p90 / max, the placebo beside each, and the
                  observation floor (tick p50) printed on every row; a placebo indistinguishable from its event class
                  is the expected valid NULL and is reported as such, never dropped
  n             = joined events per class and the game clusters they span (>= 30 clusters pooled)
  eye check     = n/a (S-row); reproduction = the verifier recomputes every quantile and every placebo from the
                  archived per-event lead-time CSV alone
  must not move = the frozen move threshold, once written, in the spec and the artifact byte for byte; the S96 and
                  INGAME_CAPABILITY artifacts; ingame_screen.BAR 0.004; backtest_fwer.jsonl untouched, K unread
NON-TAUTOLOGY: report the placebo for every class and report events whose line never moved in the window as a named
  right-censored count.
EVIDENCE: docs/evidence/harness/S220_mlb_event_lead_time_2026-09-04.md -- the per-class table with placebos, the
  censored counts, the observation floor, a NOT VERIFIED list, summary JSON and the lead-time CSV (Q9).
TEST: scripts/platformkit/ingame/test_s220_mlb_event_lead_time.py -- one new per-file test; run only that file.
REPORT: the per-class lead times with placebos, the censored counts, the LIMIT verdict, test line, SHA. Commit by
  pathspec, no push. NEVER PARK.
