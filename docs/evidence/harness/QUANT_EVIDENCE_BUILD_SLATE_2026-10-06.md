# External-reviewer evidence build slate (2026-10-06)

PAPER ONLY. Calibration and execution-quality language only. No row here makes, implies or needs a
claim that any forecaster is sharper than the market; a TRAILS or INSUFFICIENT result is recorded with
the same discipline as any other.

Purpose: an external quantitative reviewer (pricing desk, prediction-market desk, sports-analytics
group) should be able to verify the project's central measurements in about five minutes on a public
clone, and should see a record that grows with time and carries independent timestamps. Today neither
holds. The rows below close that gap. S ids are NOT allocated here: every row reads "S-id: to
allocate"; the dispatcher allocates from the register's NEXT_GAP_ID.

Rails for every row: build only under scripts/platformkit/** and docs/**; never edit src/, kernel/,
api/, intel/, scripts/team_system/; never write data/registry/; never flip a flag ON; never touch a
seal-pinned paper-desk file (DESK_STATE.md section 2 list); <= 300 LOC per file; per-file tests only;
ASCII only; supersede by ADDING, never delete an evidence line; every published per-game price must
come from a source the licence ledger marks OK.

## 0. Measured state this slate starts from (with the file that shows it)

- Pregame vs the devigged close (game-clustered DM): NBA moneyline indistinguishable from the close at
  n=372 (MDE 0.0152); MLB moneyline and soccer O/U 2.5 trail by +0.0039 and +0.0076 Brier with intervals
  above zero. Source: docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md.
- Three tracked pages still describe MLB and soccer as matching the close within noise:
  docs/JOB_EVIDENCE_PACKET.md line 94 and line 244, docs/CALIBRATION_RECORD.md line 9. README.md line 19
  and EVIDENCE.md line 36 carry the corrected reading. No check compares figures across pages.
- No per-game pregame-vs-close file is public. The NBA close is ESPN-sourced (LICENCE_LEDGER row 1,
  DECIDE); MLB odds come from an archive marked UNREAD (row 13); soccer (row 7, football-data.co.uk) and
  ATP (row 8, tennis-data.co.uk) are marked OK, but their per-game rows were never exported.
- No prospective pregame forecast log exists (docs/evidence/pregame/ holds retrospective memos only).
- In-game paper desk to 2026-10-04: 10 nights with any receipt, 2 COMPLETE, 0 qualified games in any
  sport, ~136 TTL-30 credited paper fills on unqualified tape, every pooled cell INSUFFICIENT.
  Source: docs/evidence/forward/cumulative/2026-10-04.md; docs/evidence/forward/WEEKLY_RECORD.md shows
  0 completed weeks.
- Latency ledger exists for 8 nights (receipt minus play clock p50 18.5-24.0 s; share of plays where
  the book moved first 0.29-0.62). Source: cumulative/2026-10-04.md, docs/evidence/forward/latency/.
- No reader-facing methods page defines devig, close-relative scoring, CLV-as-price-improvement and
  maker markout in one place (no docs/CLV_AND_MARKOUT.md, no docs/KALSHI_NOTE.md).
- Model cards: none (existing row S674, open).

## 1. Ranked rows

### R1. Canonical figures file + cross-surface consistency gate
- S-id: to allocate. Platform: PORTABLE. Effort: S (about 5 h). Builder: codex (gate), Claude (figures file).
- Before-condition (measured): the three lines named in section 0 disagree with the DM recompute; no
  automated check exists.
- Artifact: docs/evidence/CANONICAL_FIGURES.json (one entry per public figure: key, value, interval, n,
  verdict word, source artifact path, as-of date); scripts/platformkit/eval_gate/claim_consistency.py
  (reads the JSON and a list of surfaces, finds each figure's sentence by key-specific patterns, reports
  DISAGREE / MISSING / OK per surface line; accepts extra surface paths on the command line so an
  out-of-repo text file can be checked); superseding notes ADDED beside the three stale lines (the
  original text stays).
- Verifier contract. Tier 1 (contract): every JSON value matches its source artifact to the printed
  precision; the gate fails on the pre-note tree naming exactly the three lines and passes after the
  notes; no line was deleted (diff shows additions only on the three pages). Tier 2 (adversarial):
  plant a fourth surface with a changed interval bound and a changed verdict word; both are caught; a
  sentence that cites a retracted figure inside retraction framing is not flagged.
- Tests: scripts/platformkit/eval_gate/test_claim_consistency.py.

### R2. Public per-game pregame-vs-close files (soccer O/U 2.5, ATP) + scorer
- S-id: to allocate. Platform: PORTABLE (scorer, test) / WINDOWS (one export step from local corpora).
  Effort: M (about 6 h). Builder: codex (scorer), laptop lane (export).
- Before-condition: the published soccer row (n=7,558, model 0.2465, close 0.2390, CI [+0.0059,
  +0.0092]) and ATP row (n=7,374, 0.2177 vs 0.2028) can be reproduced only from the private tree.
- Artifact: docs/evidence/pregame_vs_close/soccer_ou25_holdout.csv and atp_holdout.csv (columns:
  date_utc, match_id, p_model, p_close_devig, devig_method, y; devigged probabilities only, no raw
  prices), a data card per file (source, licence row, devig method, exclusions, sha256 of the private
  source file), scripts/platformkit/eval_gate/score_vs_close.py (numpy only; imports the public dm_test;
  prints n, both Brier scores, gap, game-clustered 95% CI, DM p, MDE, 10 reliability bins per forecaster).
  The export is a call into the existing harness functions, not a reimplementation (pattern:
  eval_gate/dm_recompute_pregame.py).
- Verifier contract. Tier 1: the scorer on the soccer CSV reproduces the DM memo row to four decimals;
  the ATP figures reproduce the published row; the data card's licence row reads OK. Tier 2: a planted
  row with p_model equal to y is flagged as a leak signature; shuffling y destroys the result; a CSV
  with a duplicated match_id refuses.
- Tests: scripts/platformkit/eval_gate/test_score_vs_close.py.
- Out of scope: NBA and MLB per-game rows stay private until their licence rows change.

### R3. Prospective pregame forecast log with an independent timestamp witness
- S-id: to allocate. Platform: MIXED (code PORTABLE; daily write on the recorder). Effort: L (about 14 h).
  Builder: Claude (spec + prereg), codex (code).
- Before-condition: zero prospective pregame forecasts on record; NBA regular season opens 2026-10-20.
- Artifact: a PREREG sealed before 2026-10-20 (model and version hash, scoring rule, comparator, the
  interval method from R2's scorer, the reporting cadence, the floor below which a week reads
  INSUFFICIENT); docs/evidence/forward/pregame_log/<date>.jsonl written before each slate (game id,
  model id, model version hash, p_home, written_utc, scheduled_start_utc); a next-morning witness step
  that records the public remote's server-side push time for the commit carrying each row (commit dates
  are author-settable, so the witness is the remote's record, fetched read-only); a weekly scorer writing
  docs/evidence/forward/pregame_log/WEEKLY.md: n, Brier and log loss against the outcome and against the
  last pre-start venue mid (aggregate scores only; per-game venue prices stay private until LICENCE_LEDGER
  row 11 is read), game-clustered CI, MDE, projected date at which the MDE reaches 0.01.
- Source model: the existing walk-forward NBA pregame forecaster in scripts/platformkit/proof_nba/
  (read-only reuse); soccer and NFL may join under the same prereg by amendment before their first row.
- Verifier contract. Tier 1: every row's witness time precedes its scheduled start, else the row is
  marked LATE and excluded and counted; the weekly scorer is byte-identical on re-run; a week under the
  floor prints INSUFFICIENT. Tier 2: a back-dated commit (author date before start, push after) is
  caught as LATE; a row edited after its witness time fails the hash chain; the model version hash
  matches the artifact actually used.
- Tests: scripts/platformkit/forward/test_pregame_log.py, scripts/platformkit/forward/test_pregame_witness.py,
  scripts/platformkit/forward/test_pregame_weekly.py (directory name is a suggestion; reuse an existing
  forward-evidence package if one fits).
- Dependencies: R2 (scorer reused); must not edit any seal-pinned tick or paper-night file; the daily
  write runs as its own step beside the existing evidence push.

### R4. Methods pages: docs/CLV_AND_MARKOUT.md and docs/KALSHI_NOTE.md
- S-id: to allocate. Platform: PORTABLE. Effort: S (about 3 h). Builder: Claude.
- Before-condition: no single page defines the measurement vocabulary a desk reviewer uses.
- Artifact: CLV_AND_MARKOUT.md (Shin and proportional devig, Brier and log loss against the close,
  game-clustered DM, MDE, CLV defined as price improvement against the devigged close, maker markout at
  fixed horizons, fee netting; for each, what is measured today with its file, or "not yet measured");
  KALSHI_NOTE.md (fee formula and rounding cited to the venue's documentation with fetch dates, maker vs
  taker, the in-game Gate A-0 result stated as measured, why the paper desk is maker-side and paper only).
- Verifier contract. Tier 1: every definition cites a code path that exists; every figure matches
  CANONICAL_FIGURES.json (R1 gate passes with both pages added as surfaces); vocabulary preflight passes.
  Tier 2: an independent reader finds no sentence implying the forecaster is sharper than the market.
- Tests: covered by test_claim_consistency.py (pages added to its surface list).

### R5. Execution-quality summary (paper, descriptive)
- S-id: to allocate. Platform: PORTABLE (code) / WINDOWS (real run). Effort: M (about 6 h). Builder: codex.
- Before-condition: fills are reported as counts only (cumulative/2026-10-04.md); exec_quality/*.json
  carry engine statistics with INSUFFICIENT; no per-fill markout table with intervals is published.
- Artifact: docs/evidence/forward/exec_quality/MARKOUT_SUMMARY.md + .json: per-fill markout at +5, +30,
  +300 s and to settlement in contract-cents, fee columns separate, game-clustered intervals, fill share
  of quoting opportunities, each cell labelled UNQUALIFIED_TAPE and INSUFFICIENT under 30 games; reuses
  scripts/platformkit/execution/markout.py and fill_realism_markout.py (no new fill model).
- Verifier contract. Tier 1: fill counts reconcile to fill_realism/*.json per night; re-run is
  byte-identical; no currency-denominated key appears. Tier 2: a fixture with one game carrying the mean
  shows the leave-one-game-out range; a night with a missing receipt is counted as missing, never zero.
- Tests: scripts/platformkit/execution/test_markout_summary.py.

### R6. Write-up 1: pregame pricing from public data against the devigged close
- S-id: to allocate. Platform: PORTABLE. Effort: M (about 10 h). Builder: Claude draft + independent
  honesty-gate pass.
- Before-condition: results exist only as internal memos (DM_RECOMPUTE, POWER_PAGE, MULTIPLICITY_MEMO,
  retraction record); no self-contained paper.
- Artifact: docs/papers/PREGAME_VS_CLOSE_2026.md, 6-10 pages: data, devig, walk-forward, clustered DM,
  power, the rejected-signal catalogue as a result, the retractions, limitations.
- Verifier contract. Tier 1: R1 gate passes with the paper as a surface; every table reproduces from R2's
  CSVs or a tracked memo. Tier 2: an adversarial reader checks that no number appears without its
  interval and that NBA is described as underpowered, not as parity.
- Tests: surface added to test_claim_consistency.py.

### R7. Write-up 2: in-play venue book versus the official feed (latency ledger)
- S-id: to allocate. Platform: PORTABLE. Effort: M (about 8 h). Builder: Claude + honesty gate.
- Before-condition: 8 nights of latency ledger; no reader-facing analysis.
- Artifact: docs/papers/INPLAY_LATENCY_2026.md: per-night and pooled receipt-minus-event quantiles,
  book-moved-first share with game-clustered intervals, clock-offset caveat, and the Gate A-0 comparison
  of the in-game model with the live mid; starts only when >= 10 nights exist.
- Verifier contract. Tier 1: every table reproduces from docs/evidence/forward/latency/ files; nights
  under the ledger's own floor are labelled. Tier 2: the reader confirms the paper does not convert a
  latency share into any statement about achievable results.
- Tests: surface added to test_claim_consistency.py.

### R8. Five-minute verification path on a clean public clone
- S-id: to allocate. Platform: PORTABLE (cloud routine). Effort: S (about 2 h). Builder: Claude.
- Before-condition: QUANT_BRIEF section 5 points to pages; it gives no command a reviewer can run
  without the private tree.
- Artifact: a "Verify in five minutes" block in docs/QUANT_BRIEF.md (added section, prior text kept)
  listing five commands: the eval_gate per-file tests, the R1 gate, the R2 scorer on the soccer CSV, the
  R3 witness check on the latest log day, the R5 summary re-run.
- Verifier contract. Tier 1: a cloud routine on a fresh export of the public allowlist runs all five and
  records output in a tracked receipt. Tier 2: the receipt is compared line by line with the brief's
  printed expectations.
- Tests: the five commands themselves; no new test file.

## 2. Existing register rows that serve the same reviewer (no new id)

- S674 (model cards + inventory): R3 cites a model version hash; the card makes it readable.
- S661 (venue socket live verification + paired night): moves the capture evidence from REST polling to
  the venue's streaming API; owner key required.

## 3. Dispatch order

R1 -> R2 -> R4 -> R3 (prereg sealed before 2026-10-20) -> R8 -> R6 -> R5 -> R7. R1, R2 (scorer), R4 and
R8 are cloud-portable now; R2's export and R3's daily write need the laptop or recorder. Respect the
focus-hour quiet rule (DESK_STATE.md section 1b) for every laptop step.
