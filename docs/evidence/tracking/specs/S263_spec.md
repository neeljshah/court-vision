GAP S263 | sport nba | worktree a14 | log cx_s263_s88_preburn_companion
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: docs/evidence/harness/S88_phase_recal_2026-09-04.md:52 states "n_burn_in_dates=3, n_eval_ticks=33,920
  of 47,104, n_informative_ticks=11,087 (32.7 pct)". The published paired-loss CSV
  docs/evidence/harness/s88_phase_recal_2026-09-04.csv (memo:123-125) carries only the 33,920 post-burn-in
  rows; 47,104 - 33,920 = 13,184 pre-burn-in ticks are omitted entirely, with no companion artifact.
PREMISE (step 0, INFORMATIONAL): re-run s88_phase_recal and confirm the CSV row count is 33,920, the
  S06-blessed corpus denominator is 47,104 ticks / 158 games (memo:30-31), and n_burn_in_dates=3; confirm
  47,104 - 33,920 = 13,184 pre-burn rows are absent from the CSV and from every other docs/evidence/ artifact
  (grep first).
CHANGE (step 1): additive companion CSV (new filename, e.g. s88_phase_recal_preburn_2026-09-04.csv) carrying
  the 13,184 omitted pre-burn-in rows with the same schema as the published CSV plus one new burn_in flag
  column; the published CSV's rows keep burn_in=False for the union check. No column renamed or removed on the
  existing file. Never write data/ or docs/research/; no src/ kernel/ api/ intel/ edits; one store at a time.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = row-count union (published + companion = full corpus) and the published per-phase Brier
                  table recomputed with burn_in rows excluded vs included
  before        = 33,920 of 47,104 ticks published; 13,184 pre-burn ticks have no artifact anywhere
  bar           = companion + published CSV row counts = 47,104 exactly, 0 overlap, 0 gap; the S88 POOLED and
                  per-phase Brier numbers (pooled incumbent 0.174603, recal 0.176080, market 0.170853; late|
                  leading_big +0.031643; mid|trailing -0.011964) reproduce unchanged at max abs diff <= 1e-9
                  with burn_in rows excluded; the with-burn-in numbers are reported beside them as a sensitivity
  n             = 47,104 ticks total (33,920 published + 13,184 companion), exceeds the 30 rail
  eye check     = n/a (S-row); reproduction = verifier sums both CSVs' row counts and recomputes both tables
  must not move = the published s88_phase_recal_2026-09-04.csv (byte-identical); the 0.174603/0.176080/
                  0.170853 pooled bar; n_burn_in_dates=3
NON-TAUTOLOGY: the with-burn-in sensitivity table is reported even if it looks worse; it never replaces or
  rounds the published post-burn numbers.
EVIDENCE: docs/evidence/harness/S263_s88_preburn_companion_2026-09-04.md plus the companion CSV. ASCII only;
  calibration language only; evidence files under 50 MB.
TEST: one new per-file test (companion + published row counts sum to 47,104; published Brier table unchanged
  when burn_in rows filtered out), run only that file.
REPORT: row-count union, before/after Brier tables (excl/incl burn-in), test line, SHA. Commit by pathspec, no
  push. NEVER PARK.
