# S347 prereg DRAFT -- orchestrator review before sealing (2026-09-21)

Status: the draft `S347_PREREG_DRAFT_2026-09-21.md` stays UNSEALED. Nothing has been scored. This note lists what must be
settled BEFORE the seal; it contains no calibration number. Vocabulary follows contract Q6; automated scan required.

## Must change before sealing

1. **"Missing mandatory fields ... stop the run" cannot survive contact with the real corpus.** Measured by the S346 reviewer
   (counts only): 52,646 of 78,986 `mlb_clean` rows carry a stated game state; the rest are state-less rows, and `soccer_intl`
   has 696 partial rows (7.7 pct). As drafted the scorer would halt on the first real file. Replace with an ELIGIBILITY rule:
   a tick is eligible only if it has market_prob, model_prob, outcome and EVERY declared state feature for its sport; an
   ineligible tick is excluded from ALL FOUR arms identically (so the comparison stays paired) and is COUNTED by reason per
   file and per game. "Stop the run" remains for integrity failures only: hash mismatch, unparseable JSON, inconsistent outcome
   within a game, duplicate stable tick keys, unknown corpus name. The scorer code (`baseline_four_arm.py`) must be changed
   to match in a small follow-up row BEFORE the seal, and re-reviewed.
2. **Pre-seal eligibility census (counts only, no loss, no outcome statistic):** on the revision-3 corpus report, per sport,
   files / games / ticks eligible and excluded by reason, state-transition ticks, games per first-tick date, and how many folds
   are warmup under the 3-day embargo. The seal records these counts so the denominators cannot move afterwards. If a sport
   has fewer than 30 eligible games it is declared UNDERPOWERED in the prereg itself.
3. **Carry-over from the independent code review (binding for the scoring step):** (a) a corpus directory outside the gate
   DATA_ROOT makes the reused loader return an EMPTY frame -- add a hard error; (b) assert per key that the output outcome
   equals the evaluator record; (c) rows carry no home/away, so the shared same-team purge is degenerate and the temporal
   settlement embargo is the binding leak guard -- report train-set size per fold.
4. **Corpus definition depends on S346**, which is still in a fix lane (its third amendment corrected an orchestrator rule the
   corpus falsified). The prereg names the revision-3 manifest hash; no seal before S346 lands and the corpus is regenerated.

5. **Duplicate tick keys are everywhere in the real corpora** (measured, counts only: mlb_clean 1,588 keys of which 88 conflict;
   mlb_segmented 50, all conflicting; soccer_intl 203 of which 3 conflict). "Duplicate stable tick key stops the run" is replaced
   in the scorer (row S355 AMENDMENT 1): identical repeats collapse with a count; a conflicting key is excluded from all four arms
   and counted. The sealed text must state this rule and the census counts.

6. **The declared MLB features did not exist in the data.** Running the candidate's eligibility step over the real corpora (counts
   only) gave ZERO eligible MLB ticks: the scorer looked for base1 / base2 / base3, while the real state text carries one field
   base=0..7. Row S355 AMENDMENT 2 redeclares the MLB features (score_diff, inning, half, outs, base as a one-hot over its eight
   values, no bit order assumed). Expected eligible MLB population: the 51,233 rows that carry all five fields, before duplicates.
7. **Soccer is UNDERPOWERED on the data on disk**: 29 eligible games in soccer_intl and 27 in soccer_intl_segmented, with 5 warmup
   folds on top -- below the 30-game bar. The sealed text must say so and report soccer descriptively only. MLB is then the single
   powered corpus, so no AHEAD conclusion is possible from this baseline (two corpora are required); its purpose is the corrected
   MLB baseline. A second powered corpus exists in principle: the NBA checkpoint corpus (1,593 games with state joined) needs a
   converter to the joined JSONL shape with an as-of model probability -- a separate row.

## Keep as drafted

- Sign convention: delta = candidate loss minus arm A loss; negative = lower loss; the inherited verdict code maps lo > 0 to
  BEHIND. State it once more in the sealed text next to every table header.
- Fixed ridge 1e-3, no tuning search; training-only scaling and constant-column removal; D equals C when model_prob is constant.
- One fold per first-tick date, all ticks of a held-out game out of training, symmetric 3-day embargo, warmup folds excluded
  from every arm equally.
- All-tick and state-transition populations reported separately; tick and equal-game weighting both reported.
- Inherited bars byte-identical (EPS, N_BOOT, SEED, N_MIN_GAMES, ECE_BINS, verdict rule); the new single-game concentration
  rule (share <= 0.5) labelled as new; SINGLE-WINDOW labelling; at most two attempts; no outcome-selected retries.
- The Q2 trial charge and K are recorded by the orchestrator before launch.

## NOT VERIFIED

- Whether model_prob provenance in each corpus is strictly as-of the tick (the draft asks for this review; not done).
- Eligibility counts on the revision-3 corpus (the corpus does not exist yet).
- Whether the MLB state-less rows are concentrated in particular games or phases (would bias the eligible population).
