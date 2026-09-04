# S226 In-Game Clutch Foul Rotation

Verdict: CLOSED AT LIMIT. The fixed 80-percent-power MDE is 0.094496128575,
above the unchanged 0.004 bar. No candidate hypothesis was evaluated after that
required limit check. This is a calibration measurement only; no serving route,
feature flag, register, or FWER ledger was changed.

## Contract, preregistration, and machine

This ran locally in `C:\Users\neelj\nba-track-a13` on branch `track-a13`.
Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Preregistration:
`docs/evidence/harness/S226_ingame_clutch_foul_rotation_prereg_2026-09-04.md`.
Its pre-seal SHA-256 is
`4DB9F6F9E92440C9949B39AC8BC0327F651693F9D09764841DC218A98A01FB82`.
The seal was written before the first metric computation.

## Inputs and premise reproduction

Each source was opened read-only and one at a time. No source has a raster
resolution.

| Source | Bytes | SHA-256 |
|---|---:|---|
| `C:\Users\neelj\nba-ai-system\data\cache\inplay_odds\nba_checkpoints_full.parquet` | 2,829,826 | `5EA6498D88BF7548395C700C7239641DCBD1D641BDADDB5A6B63FCF0EA8909E5` |
| `C:\Users\neelj\nba-ai-system\data\cache\inplay_foul_state.parquet` | 39,429 | `CD3C5CC4714BE7655A9BAF05845C8B32F089090F87594630999A8F606118D5D9` |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\possession_states_2024_25.parquet` | 249,491 | `3AFF433FD0D9EB1979B6355A4C5B93DB6F8646F7556E84C3FBD07E8867FB82E0` |
| `C:\Users\neelj\nba-ai-system\data\cache\ingame\possession_states_2025_26.parquet` | 247,926 | `4E86FFE9978C6DA92097FB559D58185CC23F3239CC516A11C201CFDA1D492625` |

The fixed predicate is `period == 4`, `abs(margin) <= 5`, and
`game_clock_s <= 300`. It reproduces the stated denominator exactly:

| Population | Ticks | Games |
|---|---:|---:|
| Period 4 | 284,586 | 1,593 |
| Clutch cell | 62,465 | 702 |

Of the 1,593 period-4 games, 891 provide no clutch tick. They remain in that
population count; no game was excluded. The clutch cell has zero null market
probabilities and zero null outcomes.

Foul-state coverage uses `(str(game_id), period)`. The 5,010 foul rows have
5,010 unique keys and zero duplicate key rows, but match 0 / 62,465 clutch
ticks (0.0000000000 percent). The stored foul game ids begin with the older
`00222` form, while the checkpoint ids are the `401...` form. This is named
missing foul state, not a reason to remove a clutch tick.

Possession-state coverage uses the causal as-of key
`(str(game_id), min(seconds_remaining >= game_clock_s))`. The two stores total
60,582 rows with zero duplicate `(game_id, seconds_remaining)` rows. This
attaches state to 58,981 / 62,465 clutch ticks (94.4224765869 percent), across
664 games; 3,484 ticks have no available possession state. The as-of direction
never uses a state with fewer seconds remaining than the tick. Atlas foul and
rotation stores were not joined because they are SNAPSHOT-ONLY at as_of
2026-05-31: BLOCKED-ON-S223.

## Limit check before any candidate arm

The market and S123 default incumbent were each produced by the callback of
`scripts/platformkit/eval_gate/cpcv_engine.py::cpcv_evaluate`, with 4 groups,
1 test group, and a nonzero 1-day symmetric embargo. The shared engine also
applies its 48-hour same-team purge and symmetric matchup purge. A state was
timestamped one second after its observed checkpoint and carried that checkpoint
as its strictly earlier feature availability. Strict test-view redaction was
enabled. Thus every printed probability came from the shared evaluator callback.

| Arm | Brier | ECE | n | Game clusters | n_eff |
|---|---:|---:|---:|---:|---:|
| Market | 0.024561402553 | 0.003328567998 | 62,465 | 702 | 2007.019658874244 |
| S123 default incumbent | 0.024561402553 | 0.003328567998 | 62,465 | 702 | 2007.019658874244 |

The two callback series are byte-identical in `game_id`, timestamp,
probability, and outcome because S123's default incumbent is the market line.
Using the shared 80-percent-power MDE calculation with
`n_eff = int(2007.019658874244)` and the sealed family size `K = 72` gives
0.094496128575. It exceeds the immutable 0.004 bar, so the specification
requires CLOSED AT LIMIT. No candidate probability, per-hypothesis Brier value,
DM p, confidence interval, or BH p was computed. All 62,465 baseline ticks were
scored; candidate arms were not started, not silently row-filtered.

## Archived differential and deterministic family

The scored callback output is archived at
`docs/evidence/harness/S226_ingame_clutch_foul_rotation_baseline_paired_losses_2026-09-04.csv`.
It has 62,465 rows and records game cluster, timestamp, outcome, market and
S123 probabilities, both squared losses, and preregistration identity. This
allows the reported baseline Brier values and identity to be recomputed without
live model state.

The required additive sibling is
`scripts/platformkit/foundry/ingame_grammar_nba_clutch_foul_rotation.py`. It
imports `BAR` rather than assigning it, keeps the original
`foundry/ingame_grammar_nba.py` untouched, and deterministically enumerates 72
foul-state and possession-state hypotheses. Its reproducible enumeration is at
`docs/evidence/harness/S226_ingame_clutch_foul_rotation_hypotheses_2026-09-04.csv`;
run:

```text
python -m scripts.platformkit.foundry.ingame_grammar_nba_clutch_foul_rotation --output docs/evidence/harness/S226_ingame_clutch_foul_rotation_hypotheses_2026-09-04.csv
```

Route SHA-256 values at measurement time:

```text
scripts/platformkit/foundry/ingame_grammar_nba.py 1A631144AE8BA110CA90F0A8C300567E273CDB1DD6312446A2FE257CEE0A0A16
scripts/platformkit/foundry/ingame_grammar_nba_clutch_foul_rotation.py E98C113619F7DD41EE212A1E70B48E7E10FC3A4722A4F4235F241E41615D4718
scripts/platformkit/eval_gate/cpcv_engine.py 6F622DC107B432DF0BDC1F4700E44D900DE5C5ADAAD9657E15A22C579269C6E6
scripts/platformkit/eval_gate/walkforward.py 1058F981A328121802A996E8D46FF9502212A026918C723B7EBE28F49DCE0C69
scripts/platformkit/foundry/ingame_incumbent_nba.py 476ED9FDFB714B93C5B722F8E99FB1266CDB5987A729495F12E84D2B62EA08ED
```

## Test and verifier self-check

Test run:

```text
python -m pytest tests/platformkit/foundry/test_ingame_grammar_nba_clutch_foul_rotation.py -q -p no:cacheprovider
1 passed in 1.01s
```

- B1-B10: the denominator is stated before coverage; all new schema is additive;
  no existing reader, deployment, route, threshold, or original grammar changed.
- Q1: the named preregistration seal predates the first score.
- Q2: this is SCREEN-only; no FWER ledger or register was read, charged, or written.
- Q3: the imported bar remains 0.004 and the limit verdict does not move it.
- Q4: every scored probability came from the shared CPCV evaluator with purge,
  symmetric nonzero embargo, strict redaction, and as-of availability.
- Q5: no AHEAD finding is made.
- Q6: calibration language only.
- Q7-Q9: the scored population has 62,465 ticks and 702 game clusters; the
  premise is measured first; the paired callback loss series is archived above.
