# Model card: in-game win-probability conditioning forecasters (NBA, MLB, soccer, tennis)

Register row S674. Every number is transcribed from the source named beside it; unknown facts
read "not recorded".

- Name: the in-game repricers that fuse a pregame rating prior with the realized game state:
  NBA via `winprob_dispatch('nba')` over `predict_matchup.py` (benchmark receipt), and the proof
  harnesses `proof_nba/ingame_accuracy.py`, `proof_mlb/ingame_accuracy.py`,
  `proof_soccer/ingame_ht_accuracy.py`, `proof_tennis/ingame_accuracy.py` (`docs/PROOFS.md`).
- Version: not recorded; the harness sha256 values under Receipts pin the code read on 2026-10-20.

## Intended use and non-use

- Use: a calibrated live win probability given the score state at a checkpoint (NBA end of
  quarter, MLB end of inning, soccer minute, tennis set). Calibration and sharpness measurement only.
- Non-use: paper only. Not a wagering signal and not a sizing input; no return figure is computed
  or implied.
- Non-use: not a claim against the live market; on paired ticks the market reference is closer
  or the comparison is underpowered (Evaluation).

## Inputs and data

- Sources: the pregame walk-forward rating (snapshot before update) plus the state observed at the
  checkpoint (score, period / inning / minute / set); the label is the final result
  (`docs/PROOFS.md`, harness tables).
- NBA benchmark: 1,593 games, Polymarket in-play price fused in `nba_checkpoints_full.parquet`, a
  single capture window (receipt). Data card C1 (`nba_checkpoints_r1`).
- Gate A-0 Kalshi corpora: MLB 227 games, soccer 51 games (data cards C2 to C4,
  `docs/evidence/CORPUS_DATA_CARDS_2026-09-22.md`). Date spans: see the data cards; harness training
  windows: not recorded.
- As-of: Gate A-0 measured 2026-09-14, re-derived 2026-09-29 (S541); benchmark receipt dates: not recorded.

## Method

- Later periods are never seen; recalibrators are fit on TRAIN games only (`docs/PROOFS.md`).
- NBA benchmark: the checkpoint is the last observed tick at or before each elapsed-minute anchor,
  never a later one (receipt `honest_note`).
- Truncation invariance for streaming features: `tests/test_ingame_leak_free.py` (packet section
  2C); excerpt: [TRUNCATION_INVARIANCE.md](../method/TRUNCATION_INVARIANCE.md).
- Paired ticks, model vs market reference on the same tick, game-clustered bootstrap 95 percent
  intervals; verdict labels per receipt (`EVIDENCE.md` section B;
  `docs/evidence/ingame/GATE_A0_2026-09-14.md`).
- Static-prior comparison: the same outcomes scored by the pregame prior alone vs the conditioned model.
- Corpora: single capture window per sport, so the two-corpus rule of
  [MULTICORPUS_ACCEPTANCE.md](../method/MULTICORPUS_ACCEPTANCE.md) is not met.

## Evaluation

| As of | Comparison | Numbers | Verdict | Source |
|---|---|---|---|---|
| not recorded | NBA end of Q1 vs market, Brier | 0.2006 vs 0.1922, delta -0.0084 [-0.0161, -0.0008], n=1,592 | MARKET_SHARPER_PROVISIONAL (single corpus; provisional) | `EVIDENCE.md` section B |
| not recorded | NBA halftime / end Q3 / Q4 under 5:00 vs market | deltas -0.0040 / +0.0011 / +0.0019, all CIs include 0, n=1,593 | UNDERPOWERED (cannot tell) | `EVIDENCE.md` section B |
| not recorded | MLB total runs, end of innings 6 / 7 / 8, CRPS | deltas 0.6392 / 0.7327 / 1.4201, CIs exclude 0, n=49-55 | MODEL_SHARPER_PROVISIONAL (small-sample retrospective diagnostic) | `EVIDENCE.md` section B; `RECEIPTS.md` |
| not recorded | Soccer home win, minute 60 / 75, Brier | deltas -0.0931 / -0.1075 (market closer), n=22 / 17 | UNDERPOWERED (receipt label on sample size, n at most 48 source games) | `last_run_ingame_soccer.json` |
| 2026-09-14 | Gate A-0 MLB vs Kalshi in-play, Brier | 0.2377 vs 0.2067, delta +0.0310 [0.0170, 0.0454], 227 games | BEHIND (vs the Kalshi in-play mid) | `CANONICAL_FIGURES.json` mlb_ingame_vs_kalshi_mid |
| 2026-09-14 | Gate A-0 soccer vs Kalshi in-play, Brier | 0.2279 vs 0.1427, delta +0.0852 [0.0488, 0.127], 51 games | BEHIND (vs the Kalshi in-play mid; corpus failed join-integrity, descriptive only per data card C4) | `CANONICAL_FIGURES.json` soccer_ingame_vs_kalshi_mid |
| not recorded | vs a STATIC pregame prior (not the market) | NBA Brier 0.209 to 0.159; MLB 0.241 to 0.126; tennis after set 1 0.219 to 0.151 | no packet verdict: sharper than a static prior, not a market comparison | `EVIDENCE.md` section B; `docs/PROOFS.md` |

- Sign convention follows each source: in the NBA, MLB and soccer benchmark rows a negative delta
  means the market is closer; in the Gate A-0 rows a positive delta means the market is closer.
- MDE: not recorded per row on these sources (see `docs/evidence/POWER_PAGE_2026-09-22.md`).
- Calibration: in-game ECE with leak-free TRAIN/EVAL recalibrators (`proof_tennis/ingame_calib.py`,
  `docs/PROOFS.md`); per-checkpoint log loss in the NBA receipt. Reliability curves: not recorded.

## Known limitations

- Against the contemporaneous market price the models are behind or underpowered everywhere
  except the MLB total-runs diagnostic, which is small-sample and retrospective.
- Gate A-0 corpora later failed the join-integrity check; the per-game segmented revisions (MLB 178
  games, soccer 27 of 51 files kept) keep the verdicts (`docs/QUANT_BRIEF.md` section 1).
- NBA post-final rows were 52 percent of ticks (defect D12, mitigated by rule); NBA model
  probabilities of exactly 0 or 1 on 116,459 ticks (D13, refused).
- The v2/v3 NBA in-play heads blend an input that is polarity-inverted at the source
  (`sim_win_prob`, `docs/KNOWN_LIMITATIONS.md`), unpatched as of the 2026-05-27 audit.
- Single capture-window NBA corpus: verdicts are provisional until an independent corpus replicates.

## Retractions and corrections

- Retracted (retractions page, the end-of-Q3 in-play Brier row;
  [retractions](https://neeljshah.github.io/court-vision/evidence/retractions/)): a
  "Pinnacle-class" end-of-Q3 Brier was leak-inflated by two Q4-derived features
  (`halftime_pace_shift`, `trailing_team_q4_usg_hhi`); the leak-free walk-forward value is about
  0.141 (packet section 3; `docs/KNOWN_LIMITATIONS.md`).
- Retracted (retractions page, the in-play L5-proxy row): an in-play return figure on 55,073 rows
  was settled against an L5 rolling-average line proxy, not real closes; it is a proxy ceiling
  only and is not quoted (`docs/KNOWN_LIMITATIONS.md`).
- Retracted: the NBA late-tail reading, as a post-final-buzzer artifact
  (INGAME_MODEL_2_PLAN_2026-09-29.md A1, lines 159-169); P4 ticks at clock 0 can score as late
  (S146), which bears on the Q4-under-5:00 row.
- Corrected 2026-09-29: Gate A-0 re-derived under S541 hygiene; MLB cleaned 177 games, Brier delta
  0.01696 [0.00834, 0.02542], still BEHIND; the cleaned soccer cell (11 games) is UNDERPOWERED and
  not quotable (`docs/evidence/harness/S541_gate_a0_rederive_2026-09-29.md`).

## Reproduce

- Private corpus; not reproducible from the public tree. The benchmark receipts and the Gate A-0
  memo are recorded artifacts (`RECEIPTS.md` rows; `EVIDENCE.md` sections B and C).

## Receipts

| Path | Bytes | sha256 | As of | Note |
|---|---|---|---|---|
| `scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json` | 2448 | ceef48992bd68ac86b74e6b3633f9c1fd91c1af315df7ea495de60cf15d17b8f | 2026-10-20 | NBA receipt |
| `scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json` | 5911 | 7e9dd1c5243630c3b4d0f3da85030ed068109751ad62a522e42210215c895a47 | 2026-10-20 | MLB total-runs receipt |
| `scripts/platformkit/benchmarks/crps_market/last_run_ingame_soccer.json` | 1617 | 60c1fcecefe986483b73b583d448521819fe7ff9fc728ee764c591f8154038e6 | 2026-10-20 | soccer receipt |
| `docs/evidence/ingame/GATE_A0_2026-09-14.md` | 2672 | d64ad35513316f9b51689bdfb941bbfe732d86aad4bf8650a8c0e0b9f518de87 | 2026-09-14 | Gate A-0 memo |
| `scripts/platformkit/proof_nba/ingame_accuracy.py` | 15415 | a668daf18c47251eba553a42b443e985ed40b75868f6fa7c2ed8b2497d5950e6 | 2026-10-20 | harness |
| `scripts/platformkit/proof_mlb/ingame_accuracy.py` | 15196 | 8bc2baf1588cb5adb19e5ba01f2079e0dff8ee266c7f5d5c7d202b1c852caae6 | 2026-10-20 | harness |

Owner: Neel Shah (repository owner). Card drafted by an agent under register row S674.
Last verified: 2026-10-20
