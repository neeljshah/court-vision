# S276 full-source incumbent conformal band, pod scratch

## Result

REJECT. The full source stream census and the loaded full source are both
465249 ticks / 1593 games, but the paired-loss archive contains only 461947
ticks / 1582 game clusters. The unchanged five-fold S86/S101 walk-forward
route reports 384862 held-out ticks / 1337 held-out games per nominal because
its initial expanding-window block is training-only. It therefore does not
meet the full-source scored denominator and does not support an every-row claim.

The sealed preregistration is
`docs/evidence/harness/S276_preregistration_incumbent_conformal_band_full_pod_2026-09-04.md`.
Its LF-byte SHA-256 seal is
`47ba0dfcf075c7800c38485eed71e4eb572046b82ef94bbf19fd0fee23495bf0`.

## STATIC grouped coverage and mean half-width

All cells meet the fixed 400-tick grouped-cell requirement. No cell is
ABSENT_BECAUSE.

| Nominal | Cell | Held-out ticks | Groups | Coverage | Mean half-width |
| ---: | --- | ---: | ---: | ---: | ---: |
| 0.90 | P1 | 37398 | 50 | 0.960000000 | 0.129207886 |
| 0.90 | P2 | 58009 | 50 | 1.000000000 | 0.109102791 |
| 0.90 | P3 | 44277 | 50 | 1.000000000 | 0.080957686 |
| 0.90 | P4 | 233016 | 50 | 0.980000000 | 0.017548654 |
| 0.90 | OT | 12162 | 30 | 0.933333333 | 0.069385101 |
| 0.90 | ALL | 384862 | 50 | 1.000000000 | 0.051131666 |
| 0.80 | P1 | 37398 | 50 | 0.940000000 | 0.110539975 |
| 0.80 | P2 | 58009 | 50 | 0.980000000 | 0.084881086 |
| 0.80 | P3 | 44277 | 50 | 0.960000000 | 0.068313666 |
| 0.80 | P4 | 233016 | 50 | 0.860000000 | 0.005754795 |
| 0.80 | OT | 12162 | 30 | 0.700000000 | 0.032240124 |
| 0.80 | ALL | 384862 | 50 | 1.000000000 | 0.035897666 |

The worst full-source grouped coverage is OT at nominal 0.80, 0.700000000.
The widest full-source mean half-width is P1 at nominal 0.90, 0.129207886.
For the accepted S265 sample, the worst cells were OT at 0.833333333 for both
nominals and the widest mean half-width was P2 at nominal 0.90, 0.207218181.
Thus the full-source result is not a restatement of the sample: it has a lower
worst grouped coverage at nominal 0.80 and a narrower widest mean half-width.

## Reproduction inputs and artifacts

- Full source: `data/cache/inplay_odds/nba_checkpoints_full.parquet`,
  2829826 bytes, Parquet tabular input; pixel resolution is not applicable.
- S101 summary: `data/cache/eval_gate/s101_aci_coverage_2026-09-03.json`,
  30939 bytes, JSON tabular summary; pixel resolution is not applicable.
- S101 retained screen: `data/cache/eval_gate/s101_aci_coverage_2026-09-03_ticks.csv.gz`,
  18426107 bytes, compressed CSV tabular input; pixel resolution is not
  applicable. Its scratch copy SHA-256 was
  `0d77ca38319d9784e970ff886353a0f8d0876bb2df3a3bbd9556bfe4629f0e00`.
- Summary: `docs/evidence/harness/S276_incumbent_conformal_band_full_pod_2026-09-04.json`,
  15717 bytes.
- Differential archive: `docs/evidence/harness/S276_incumbent_conformal_band_full_pod_paired_loss_2026-09-04.csv`,
  1788791 bytes, SHA-256
  `6572195a0e0b8f8ce252ff27c98c733bc69c9e9e2dc77bcd0acc904e2c66dd3e`.

The S101 replay covered all 24 market/model, nominal, and grouped cells with
`max_abs_coverage_diff=0.0`, within the fixed `1e-9` tolerance. The pod peak
RSS was 779907072 bytes.

## Pod rule and contract self-check

The calculation ran only in `/workspace/wt/a17` through `pod_run`: its dd
write probe passed before scratch writes, its compute process used nohup and a
unique log, and the deployed `/workspace/nba-ai-system` tree was never written.
No pod process was stopped or restarted. No backtest_fwer.jsonl,
hypotheses*.sqlite, or data/registry path was shipped. JSON and CSV were copied
back only after the returned source counts, all cell lines, S101 line, and RSS
line met this preregistration.

The scratch route hashes equal the committed archive hashes: S276
`addd1c6e74fd3d37d999e58adc0199a713176586acd4973832521ebd2de1d25d`, S265
`f245bd258e830faf4459d0380bb1ca5a6ed87a23521928c243fb73db178aa074`, S86
`5ee345fa337f7a458ab4180ebcf8b7234adcf8a1d1d6cbcddddb2cc63f68c7ad`, S101
`f80d94c783aeebffd2e56c9e0fa34dbddab93b5d683846ba7c170c1b4b665dbb`, S123
`ba91cf85e1e5b3f1822b1b5fb551c52a1c2b5095cc12fa9298c053a6c2049f50`, and
aci_online `b37877d34ef13dd9b62bbc8b6b68dffd038a58de56f9ca4031ad91effe56c2cf`.

Q1 is satisfied by preregistration commit `db3041e31`; Q2 is uncharged with no
ledger or register write; Q3 retains every specified bar; Q4 uses S265/S101
shared callbacks with game purge and a symmetric one-day embargo; Q5 has no
comparative status; Q6 uses calibration language only; and Q9 retains both
per-game paired losses and grouped coverage units. The focused archive-only
test passed:

`python -m pytest tests/platformkit/ingame/test_s276_incumbent_conformal_band_full.py -q`
