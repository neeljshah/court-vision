# S285 event-proximity audit of the S265 static conformal band

## Result

This is a calibration-only, sample-scale stratification audit of the unchanged S265 STATIC band.
The source was `/workspace/nba-ai-system/data/cache/inplay_odds/nba_checkpoints_full.parquet`, 2829826 bytes, Parquet tabular data; pixel resolution is not applicable.
The sealed 79,919-tick/269-game sample had p50=13 and p90=136 for the strictly-prior score-change derivation.

| Nominal | Bin | Ticks | Games | Coverage (95 pct CI) | Mean half-width (95 pct CI) |
| ---: | --- | ---: | ---: | --- | --- |
| 0.90 | near_event | 32414 | 217 | 1.000000000 [0.920000000, 1.000000000] | 0.168602183 [0.163011615, 0.174019447] |
| 0.90 | settled | 6117 | 121 | 0.933333333 [0.846153846, 1.000000000] | 0.120114296 [0.103373216, 0.138123900] |
| 0.90 | pooled | 64169 | 217 | 1.000000000 [0.960000000, 1.000000000] | 0.149771680 [0.140896795, 0.158853827] |
| 0.90 | settled-minus-near coverage | - | - | -0.066666667 [-0.142857143, 0.060000000] | - |
| 0.90 | near-minus-settled half-width | - | - | - | 0.048487887 [0.032294004, 0.063200542] |
| 0.80 | near_event | 32414 | 217 | 1.000000000 [0.860000000, 1.000000000] | 0.124319017 [0.120293500, 0.128247579] |
| 0.80 | settled | 6117 | 121 | 0.933333333 [0.785714286, 1.000000000] | 0.035307979 [0.029663580, 0.044339845] |
| 0.80 | pooled | 64169 | 217 | 1.000000000 [0.920000000, 1.000000000] | 0.084881664 [0.080096474, 0.089829420] |
| 0.80 | settled-minus-near coverage | - | - | -0.066666667 [-0.180000000, 0.093437500] | - |
| 0.80 | near-minus-settled half-width | - | - | - | 0.089011037 [0.080324731, 0.094650302] |

## Reproduction and contract self-check

The scorer uses S265/S101 five-fold walk-forward scoring with game purge and a symmetric one-day embargo. One archived evaluator record exists for every scored tick, keyed by `game:source_row`; middle ticks are named exclusions.
The preregistration is `docs/evidence/harness/S285_preregistration_event_conformal_width_2026-09-04_v2.md` with committed LF-byte seal `b5accd1d3e1f80877e1d44a699838501363726958d6a68cb090d89f14d5a76c7`. It predates scoring.
The run executed in pod scratch /workspace/wt/a14. Its peak RSS was 311398400 bytes.
Q1 sealed preregistration; Q2 uncharged/no ledger; Q3 fixed bar; Q4 shared walk-forward purge and embargo; Q5 no AHEAD claim; Q6 calibration language only; Q7 each scored comparison has at least 30 game clusters; Q8 premise measured first; Q9 stores evaluator records only.

Artifacts: `docs/evidence/harness/S285_event_conformal_width_2026-09-04_retry3.json` and `docs/evidence/harness/S285_event_conformal_width_2026-09-04_retry3_paired_loss.csv`.
Focused test: `python -m pytest tests/platformkit/ingame/test_s285_event_conformal_width.py -q`.

## NOT VERIFIED

- Historical pod scratch isolation and the reported scorer peak RSS were not independently observed.
