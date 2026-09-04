GAP S307 | sport nba (in-game) | worktree a16 | log cx_s307_conformal_band_sharpening
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: two independent lanes today measured the S123 incumbent's STATIC conformal band as far too wide: S294
  (a17 candidate 9975d7499, full source 465,249 / 1,593, six S86 blocks) reports ALL-cell empirical coverage
  1.000000000 at BOTH nominals 0.90 and 0.80 (half-widths 0.031114796 / 0.019952038; worst cell OT 0.80 =
  0.777777778), and S285 (a14 fe43ebd9e, S265 sample) reports pooled coverage 1.000 at both nominals. A band that
  covers 100 pct at a 90 pct nominal is calibrated in the trivial direction only; its SHARPNESS is the gap.
PREMISE (step 0, INFORMATIONAL): reproduce the S294 ALL-cell coverage/half-width pair at both nominals from its
  archived per-tick paired CSV (fetched artifact in docs/evidence/harness/S294_*), and the S285 pooled 1.000.
CHANGE (step 1): additive sibling under scripts/platformkit/eval_gate/ (<= 300 lines) that re-fits the conformal
  quantile per STATIC cell on TRAIN folds only (the same six S86 blocks, purge + symmetric embargo, callback
  producing every interval) targeting the nominal coverage, then scores held-out empirical coverage and mean
  half-width per cell; the S265/S294 band stays byte-identical as the baseline arm. Seal a prereg FIRST as its
  own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show :<path>, verified with git
  show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above the seal line). Print RSS;
  the full-source scorer runs via ~/bin/pod_run <aN> --fetch <outputs> -- env S294_S101_TICKS=/workspace/wt/<aN>/
  inputs/s101_aci_coverage_2026-09-03_ticks.csv.gz <command> (scp that single file to pod scratch first; never
  --ship a data/ path). Never write data/ or docs/research/; never rewrite an existing artifact.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per cell and ALL, both nominals: held-out empirical coverage and mean half-width, baseline
                  band vs re-fit band; game-clustered 95 pct CI on the half-width reduction
  before        = S294: ALL coverage 1.000000000 at 0.90 and 0.80, half-widths 0.031114796 / 0.019952038
  bar           = re-fit band coverage within [nominal - 0.02, nominal + 0.05] on ALL and on every cell with
                  >= 400 ticks (else ABSENT_BECAUSE) AND half-width reduction CI above 0; a re-fit that reaches
                  nominal coverage only by undercovering some cell is reported as the trade-off, not a win
  sign          = sharpness gain = baseline half-width minus re-fit half-width; positive = re-fit sharper
  n             = 465,249 ticks / 1,593 games (full source on the pod); >= 30 game clusters per reported cell
  eye check     = n/a (S-row); reproduction = verifier recomputes coverage/half-width per cell and the CI from
                  the archived per-tick CSV and refits one cell from the archived train fold
  must not move = S265/S294 modules and artifacts; COVERAGE_MIN_GROUP; the S86 block design; the S101 JSON
NON-TAUTOLOGY: report every cell including the ones the re-fit undercovers; never tune the target coverage to
  the held-out folds; the baseline arm is scored on identical rows.
EVIDENCE: docs/evidence/harness/S307_conformal_band_sharpening_2026-09-04.md + summary JSON + per-tick CSV (gzip
  under 50 MB) + the pod log tail.
TEST: one per-file test refitting one cell's quantile on a fixture and recomputing one archived cell's
  coverage/half-width; run only that file.
REPORT: cell table (coverage, half-width, both arms, CIs), pod RSS, md5 parity, test line, SHA. No push. NEVER PARK.
