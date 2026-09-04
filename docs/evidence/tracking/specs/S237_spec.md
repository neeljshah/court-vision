GAP S237 | sport nba | worktree a16 | log cx_s237_max_loser_wp_tick_diagnostic
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: JP (memory jp_calibration_feedback_2026_08_31): the diagnostic is "per game, the MAX WP assigned to the
eventual LOSER" and "always check reliability plots", not just a summary Brier. MODEL_QUALITY_PROGRAM_2026-09-04.md
section 2 states it "is degenerate on the pregame corpora (one row per event_id) and has never been run on a tick
stream, which is its correct input". Measured 2026-09-04: this is only PARTLY true. `wp_diagnostics.max_loser_wp`
IS imported and called on the S86 per-tick NBA series (`s86_nba_every_tick.py:31,192,198,283-284`, printing
n_loser_paths / quantile-90 / above_0_8 to its own ascii render) -- but the archived output
(`data/cache/eval_gate/s86_nba_every_tick_2026-09-03.json`) has NO `max_loser_wp` key, and the memo
(S86_nba_every_tick_2026-09-03.md) never quotes it: the code runs the diagnostic, nobody published it. A separate,
DIFFERENT number is on record -- S58 trial B: model > 0.8 on the eventual loser in 11.4 pct of lost games vs the
market's 5.6 pct -- but that is not JP's bin-level reliability-of-the-diagnostic breakdown either.
PREMISE ADDENDUM (S207): docs/evidence/calibration/nba_ingame_baseline_2026-09-03.json already has max-loser-WP+Murphy
PREMISE (step 0): reproduce that `s86_nba_every_tick.py` calls `max_loser_wp` and that neither its archived JSON
nor its memo carries the result; rerun `wp_diagnostics.max_loser_wp` + `wp_diagnostics.reliability` on the SAME
S86 per-tick series and print the quantiles/above_0_8/above_0_9 alongside a NEW reliability table binned on the
per-game peak WP value itself (not on `model_prob`), which is what JP's ask requires and nothing on disk provides.
LIMIT (step 1): if per-game peak-WP values are too few per bin to form a reliability table (< 30 games per bin
at the frozen S05 bin edges), report CLOSED AT LIMIT and publish the quantile/above-threshold summary alone.
CHANGE (step 2): additive-only script `scripts/platformkit/ingame/max_loser_wp_report.py` (<=300 LOC) that loads
the S86 archived per-tick CSV, calls `wp_diagnostics.max_loser_wp` + `reliability`, and writes the missing
reliability-of-the-diagnostic table (peak-WP bin -> realized loser share, n games) plus the existing
quantile/above_0_8/above_0_9 summary to one memo. No edit to `wp_diagnostics.py` or `s86_nba_every_tick.py`.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per-phase max-loser-WP quantiles (50/75/90/95) + above_0_8/above_0_9 counts, plus the new
                  peak-WP reliability table, on the S86 per-tick NBA series
  before        = no archived JSON or memo carries max_loser_wp for NBA; the only published tail number is S58
                  trial B's 11.4 pct (a different construction, not this diagnostic)
  bar           = the report reproduces the SAME per-game max_loser_wp values `s86_nba_every_tick.py` computes
                  in-process to <= 1e-12 (a byte-for-byte re-derivation check); the reliability table covers
                  every game with 0 games dropped; each bin printed with n or labelled UNDERPOWERED at n < 30
  n             = the S86 game count (>= 30 game clusters; exact n printed, not assumed)
  eye check     = n/a (S-row); reproduction = verifier reruns the script and diffs every quantile and bin value
  must not move = the S86 archived per-tick CSV; the S58 trial B 11.4 pct / 5.6 pct figures (kept as context only)
NON-TAUTOLOGY: the table covers every settled game in the S86 series, not only the games where the loser's peak
WP was already known to be high; an UNDERPOWERED bin is printed as such, not dropped.
EVIDENCE: docs/evidence/harness/S237_max_loser_wp_tick_2026-09-04.md + the reliability-table JSON. ASCII only.
Calibration language only (no dollar, ROI or edge words).
TEST: one new per-file test (byte-for-byte re-derivation check vs a fixture series), run only that file.
REPORT: quantile table, peak-WP reliability table, re-derivation diff, test line, SHA. Commit by pathspec, no
push. NEVER PARK.
