# S261 Attempt 1b In-Game Headline Re-Derivation v2

## Status: NOT VALIDATED FOR A NEW FULL-SCALE RE-DERIVATION

This landing corrects S211's artifact schema and denominator reporting. The
pre-registered full CPCV scorer exceeded the 800 MB local-memory rule and was
stopped before producing a complete summary. The completed sample-scale CPCV
run is an implementation and archive check, not a replacement full-scale
measurement. A successor may run the full scorer only after ACCEPT.

## Contract and preregistration

- Spec: `docs/evidence/tracking/specs/S261_spec.md`.
- Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.
- Machine: local Windows worktree `C:\Users\neelj\nba-track-a13`; no pod copy or
  deployment occurred.
- Preregistration: `S261_ingame_headline_rederive_v2_prereg_2026-09-04.md`.
- LF Git-blob seal: `B18A747EA3E602AA56CA1DE23C4C5142874B8062D206104BEAFEA3E31C9C223A`.
  It was committed in `b8123b1f1` before scoring.
- No charged trial was opened. K was unread; no ledger or register was read or
  written.

The scoring callback uses `cpcv_evaluate` with eight timestamp groups, two
test groups, a one-day symmetric calendar embargo, 48-hour same-team purge,
three-day symmetric same-matchup protection, and strict redaction. It computes
static, score-only, and conditional values together for every scored state.

## Premise and public comparison

The S211 paired-loss CSVs were reopened before this work. Their full-scale
reference values reproduce NBA 0.21883250084408842 / 0.17235318274013006 /
0.16324678066236500 at n_eff 1313 and MLB 0.24897282410431543 /
0.12822834737953837 / 0.12799755953257377 at n_eff 23279, in
static / score-only / conditional order. This is a premise recheck, not a new
S261 full-scale result.

The frozen public values are NBA static 0.209 and conditional 0.159, and MLB
static 0.241 and conditional 0.126. The full-reference exact differences are:

| Sport | Static public-value difference | Conditional public-value difference | Full-reference status |
|---|---:|---:|---|
| NBA | 0.00983250084408843 | 0.00424678066236500 | NOT REPRODUCED at 1e-6 |
| MLB | 0.00797282410431543 | 0.00199755953257377 | NOT REPRODUCED at 1e-6 |

The reference full-scale metrics carry static-minus-conditional 0.05558572018172342,
score-only share 0.8361737142562157, and model-prior contribution
0.009106402077765058 for NBA; MLB carries 0.12097526457174165,
0.9980922724345213, and 0.00023078784696459187. Their game-clustered prior
share intervals are [0.11469448235798914, 0.226824389014025] for NBA and
[0.0005919733086871243, 0.0032629680717889283] for MLB. Neither full-reference
public comparison meets the frozen 1e-6 bar, so both statuses remain NOT
REPRODUCED.

## Denominators and additive schema

MLB source parsing identifies 2458 `invalid_inning` rows, where either innings
field cannot be parsed, and 2246 `tied_final_score` rows, where parsed final
inning totals are equal. These are named denominator exclusions before scoring;
they are not silently removed after a loss is known. NBA has zero rows for both
reasons.

The S261 sample archive preserves the S211 v1 fields as additive aliases:
`checkpoint_count` is raw unique scored checkpoints, `finite_resamples` is the
number of finite game-cluster bootstrap draws, and `reproduction_abs_diff` is
the absolute serialization/reaccumulation difference for each of static,
score-only, and conditional losses. `cpcv_path_evaluation_count` is a new,
separate field and never substitutes for `checkpoint_count`.

## Local sample-scale CPCV archive

The completed sample selects 120 evenly spaced game paths per sport across the
whole ordered corpus, retaining every checkpoint for each selected path. It is
not a head slice. The full route reached about 1203 MB private memory, above
the 800 MB rule; this sample route remained bounded and completed locally.

| Sport | Static Brier | Score-only Brier | Conditional Brier | Static minus conditional | Score-only share | Model-prior contribution | n_eff |
|---|---:|---:|---:|---:|---:|---:|---:|
| NBA sample | 0.196756994 | 0.158089801 | 0.140052569 | 0.056704425 | 0.681907850 | 0.018037232 | 120 |
| MLB sample | 0.254742416 | 0.407497842 | 0.405585840 | -0.150843424 | 1.012675411 | 0.001912002 | 120 |

The NBA sample game-clustered prior-share 95 percent interval is
[0.13591340391248075, 0.8487045040387996]. The MLB interval is
[-0.08579371323677933, 0.07232276184161612], which covers zero and is reported
as the honest sample result. Sample values are not compared to public values
or used to alter the full-reference NOT REPRODUCED status.

## Evidence and self-check

- Summary: `S261_ingame_headline_rederive_v2_sample_2026-09-04.json`.
- Paired state-loss series: `S261_sample_nba_per_state_losses_2026-09-04.csv`
  and `S261_sample_mlb_per_state_losses_2026-09-04.csv`.
- The CSVs preserve each state ID, game cluster ID, timestamp, split IDs, raw
  checkpoint count, CPCV path-evaluation count, and all three paired losses.
  The summary supplies inputs with exact paths and byte sizes, CPCV settings,
  aliases, exclusions, shares, and intervals.
- B1: exclusions are named before scoring. B2: v1 fields are additive aliases.
  B5: no pod copy occurred. B7-B9: the sample is evenly distributed and uses
  distinct game paths as clusters. Q1: the committed prereg seal predates the
  scorer. Q3: the 1e-6 public bar is unchanged. Q4: all sample scoring uses
  the shared purged and symmetrically embargoed CPCV evaluator. Q6: this memo
  uses calibration language only. Q7: each sample n_eff is at least 30. Q9:
  paired losses and reconstructible state inputs are archived.

No existing S211 schema or artifact was rewritten. Evidence files are below
50 MB. The full-scale result is deferred rather than inferred from the sample.
