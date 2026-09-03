# S138 NBA grammar extension - FALSIFIED

## Contract

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including sections B and Q. S138 was an uncharged SCREEN proposal; no scoring, seal, K read, trial-record access, or corpus write occurred.

## Required premise measurement

Command:

```text
python -m scripts.platformkit.foundry.ingame_grammar_nba
```

Output established the frozen grammar as 16 bases x 6 transforms x 6 conditionings = 576 semantic-hash-deduplicated hypotheses. The three named unavailable tick-grain transforms remain `rank_in_league`, `z_vs_league`, and `ratio_to_opponent`, because no league or opponent tables are supplied at tick grain.

The required grep for `interaction|product|ratio` found the grammar's explicit description of "margin x time-remaining interactions" and `pace_ratio_p1` / `ratio_to_opponent`. More materially, `build_state` already builds the base `margin_x_rem = margin * rem`; its six transforms and six conditionings enumerate 36 frozen interaction hypotheses. `margin_over_sqrt_rem` is a second pre-existing combined-state base.

Therefore the premise that the grammar has no interaction hypothesis is false. Per S138 step 0, execution stops here. No new family, pin update, screen, differential archive, or test is appropriate.

## Required outcome

| item | result |
|---|---|
| premise | FALSIFIED |
| old pin / new pin | unchanged / unchanged |
| screened count clearing +0.004 | not run |
| n / n_informative / n_eff | not applicable |
| eye check | n/a (S-row); reproduction is the command and source inspection above |

## Verifier self-check

- B1-B10: no scored metric, schema change, gate change, deployment, module move, sampling artifact, or bar change.
- Q1-Q2: no scoring, preregistration, K read, or trial-record access.
- Q3: the 0.004 bar and S86 partition are unchanged.
- Q4-Q5/Q9: no OOS comparison or differential was created; no AHEAD result is asserted.
- Q6: calibration language only; none of the prohibited financial terms or retracted figures appears here.
- Q7: no sampled or scored metric was run.
- Q8: the premise was re-measured before any change and is falsified.

## NOT VERIFIED

The proposed pairwise extension was intentionally not implemented or screened because the step-0 stop condition bound first.
