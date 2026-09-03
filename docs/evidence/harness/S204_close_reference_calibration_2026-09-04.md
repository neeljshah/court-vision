# S204 Close-Reference Calibration

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q9.
Spec: `docs/evidence/tracking/specs/S204_spec.md`.

Machine: local `C:/Users/neelj/nba-track-a18` on Windows. The bounded source
corpora are local-only, so the reporter ran locally and opened each parquet
sequentially; no store above 300 MB was opened. No data, register, ledger,
flag, calibrator default, fold, bin rule, or threshold was changed.

## Preregistration and premise

Preregistration: `docs/evidence/harness/S204_close_reference_calibration_prereg_2026-09-04.md`.
Its seal is `150DFC16B37055B741F65F4D332C3625FA41B6EE4CDA140B4E5D39A7D31C5178`.
The seal predates the S204 paired comparison.

Step 0 reproduces the S05 after-ECE facts directly from each published ten-bin
table: NBA 0.024843 (1,814), MLB 0.008077 (39,162), soccer 0.009302
(25,834), and tennis 0.008403 (41,886). Every S05 count has zero dropped rows
and a FLATTENED label. The S05 statement that no gate corpus carries a close is
therefore false: verified pregame close pairs exist below.

The model side is the existing S05 per-regime expanding out-of-fold
recalibration route, computed on the full sport corpus before any close pairing.
The ten-bin rule is unchanged: `np.linspace(0, 1, 11)`, `[lo, hi)` except the
last `[lo, hi]`. Delta is `Brier(close) - Brier(model)`.

## Input provenance

| sport | full input path | bytes | SHA-256 |
|---|---|---:|---|
| NBA | `C:/Users/neelj/nba-track-a18/data/cache/combo/gate_corpus_nba_close.parquet` | 217,484 | `1862bb4c53da0741705dde007d9f735d0932e7f7aafa5acd6e32d4814d313316` |
| MLB | `C:/Users/neelj/nba-track-a18/data/cache/combo/gate_corpus_mlb_close.parquet` | 1,656,711 | `f175da11bff36fe322d2b3cd312f4a6b19033758abdd257b660e4cc95385767f` |
| soccer | `C:/Users/neelj/nba-track-a18/data/cache/combo/gate_corpus_soccer.parquet` | 6,053,712 | `e0d2f13e7a53b3ed578e81e38db82f14bb6d3a71e31a9c7cb636d5b4c7e92bc6` |
| soccer | `C:/Users/neelj/nba-track-a18/data/domains/soccer/odds.parquet` | 590,961 | `dbaf592c89ecb3c4b7298d6b71c66c4abcc5618dc7c763e2199ffa8341320655` |
| tennis | `C:/Users/neelj/nba-track-a18/data/cache/combo/gate_corpus_tennis.parquet` | 2,745,405 | `22d006f2b4f7a7186876e133508e1e9ddf14af3570f1d20a73d73d1d3669d700` |
| tennis | `C:/Users/neelj/nba-track-a18/data/domains/tennis/odds.parquet` | 1,487,365 | `a268ba8f5c0888a21b20f808ba9585466fe03c9c8a3965d64b2510a411f40ff1` |

Route identity: `scripts/platformkit/eval_gate/s204_close_reference.py` SHA-256
`0296b2e50693fd5ccbbf52913ec83008c3f898ab8cf1c8220bcde7f0fdf31b2a`, 9,572 bytes;
`scripts/platformkit/eval_gate/calibration_report.py` SHA-256
`05f02708ac72f241c083c4f3b6a7f0efde8e47ef37d4bc282b826f567cc56aab`, 17,002 bytes.

## Paired results

| sport | paired rows | model ECE / Brier / log loss | close ECE / Brier / log loss | delta | clustered 95 pct CI | n_eff | label |
|---|---:|---|---|---:|---|---:|---|
| NBA | 220 | 0.055150 / 0.196607 / 0.574129 | 0.052280 / 0.180987 / 0.536582 | -0.015620 | [-0.077820, 0.046580] | 2 | NOT SCORABLE |
| MLB | 910 | 0.026988 / 0.248613 / 0.690418 | 0.022252 / 0.245056 / 0.682751 | -0.003557 | not computable | 1 | NOT SCORABLE |
| soccer | 16,322 | 0.003796 / 0.247006 / 0.695168 | 0.008641 / 0.239460 / 0.671612 | -0.007546 | [-0.010577, -0.004516] | 6 | NOT SCORABLE |
| tennis | 0 | n/a | n/a | n/a | n/a | n/a | NOT SCORABLE |

The status rail is unchanged: a MATCH or BEHIND label needs at least 30
`corpus_unit` clusters. The NBA, MLB, and soccer metrics are printed on the
complete paired denominators but cannot receive a match label under that rail.
Tennis has no verified pregame close because S03 records its close vintage as
SYNTHETIC.

## Reliability tables

Each cell is `n / mean probability / observed frequency`; `-` is an empty bin.

### NBA

| bin | model | close |
|---|---|---|
| 0.0-0.1 | 4 / 0.060546 / 0.000000 | 4 / 0.075000 / 0.000000 |
| 0.1-0.2 | 8 / 0.150673 / 0.125000 | 12 / 0.156250 / 0.083333 |
| 0.2-0.3 | 7 / 0.269519 / 0.285714 | 24 / 0.259208 / 0.166667 |
| 0.3-0.4 | 44 / 0.367049 / 0.363636 | 23 / 0.343022 / 0.347826 |
| 0.4-0.5 | 18 / 0.423374 / 0.277778 | 37 / 0.455270 / 0.540541 |
| 0.5-0.6 | 38 / 0.560355 / 0.631579 | 29 / 0.560862 / 0.586207 |
| 0.6-0.7 | 51 / 0.637085 / 0.607843 | 33 / 0.648939 / 0.666667 |
| 0.7-0.8 | 26 / 0.737164 / 0.846154 | 26 / 0.753462 / 0.807692 |
| 0.8-0.9 | 22 / 0.832702 / 0.909091 | 23 / 0.853696 / 0.913043 |
| 0.9-1.0 | 2 / 0.955425 / 1.000000 | 9 / 0.917222 / 1.000000 |

### MLB

| bin | model | close |
|---|---|---|
| 0.0-0.1 | - | 1 / 0.010000 / 0.000000 |
| 0.1-0.2 | - | - |
| 0.2-0.3 | - | 2 / 0.273619 / 0.500000 |
| 0.3-0.4 | 4 / 0.332836 / 0.250000 | 40 / 0.371633 / 0.300000 |
| 0.4-0.5 | 272 / 0.459050 / 0.477941 | 256 / 0.458901 / 0.441406 |
| 0.5-0.6 | 484 / 0.545486 / 0.522727 | 485 / 0.545476 / 0.556701 |
| 0.6-0.7 | 142 / 0.624807 / 0.570423 | 109 / 0.636316 / 0.577982 |
| 0.7-0.8 | 8 / 0.706035 / 0.750000 | 16 / 0.726843 / 0.687500 |
| 0.8-0.9 | - | - |
| 0.9-1.0 | - | 1 / 0.990000 / 1.000000 |

### soccer

| bin | model | close |
|---|---|---|
| 0.0-0.1 | 4 / 0.005322 / 0.750000 | - |
| 0.1-0.2 | 21 / 0.143399 / 0.285714 | - |
| 0.2-0.3 | 19 / 0.261499 / 0.315789 | 68 / 0.279671 / 0.264706 |
| 0.3-0.4 | 124 / 0.383944 / 0.467742 | 1,618 / 0.367770 / 0.381335 |
| 0.4-0.5 | 6,742 / 0.469017 / 0.469149 | 6,060 / 0.452737 / 0.447195 |
| 0.5-0.6 | 6,816 / 0.524660 / 0.528756 | 5,555 / 0.545153 / 0.553015 |
| 0.6-0.7 | 2,580 / 0.624234 / 0.619767 | 2,421 / 0.639534 / 0.655514 |
| 0.7-0.8 | 14 / 0.731941 / 0.571429 | 557 / 0.728200 / 0.730700 |
| 0.8-0.9 | - | 43 / 0.820273 / 0.837209 |
| 0.9-1.0 | 2 / 1.000000 / 0.000000 | - |

## Exclusions and archived differential

No paired row was dropped after pairing. Each excluded event ID and reason is
in the corresponding exclusion series:

| sport | excluded rows by reason |
|---|---|
| NBA | 343 `inplay_close_source`; 1,251 `null_price` |
| MLB | 38,252 `null_price` |
| soccer | 9,512 `null_price` |
| tennis | 8,201 `null_price`; 33,685 `synthetic_vintage_no_pregame_proof` |

Summary: `docs/evidence/harness/S204_close_reference_calibration_2026-09-04.json`.
Paired series: `S204_nba_paired_2026-09-04.csv`, `S204_mlb_paired_2026-09-04.csv`,
`S204_soccer_paired_2026-09-04.csv`, and `S204_tennis_paired_2026-09-04.csv` in
`docs/evidence/harness/`. Each carries event ID, corpus unit, event date, y,
both probabilities, both squared losses, and the per-row Brier delta.
Exclusion series with every event ID and its reason are stored beside them.

## Reproduction and contract self-check

`python -m pytest scripts/platformkit/eval_gate/test_s204_close_reference.py -q`
returns `3 passed`. Independent recomputation from the paired series reproduced
every paired-row count, unique event-ID count, ECE, Brier, log loss, delta,
n_eff, and every available clustered interval to less than 1e-12.

- B1: pairing and exclusions are fixed before metrics; every excluded event ID
  is archived with its reason.
- B2-B6: additive reporter and evidence only; no schema, deployment, caller,
  register, ledger, or gate change.
- B7-B9: full paired denominators, no sampled rows, no self-fit comparison, and
  corpus-unit cluster counts are named.
- B10/Q3: no threshold or bar moved.
- Q1: sealed preregistration is named above. Q2: this is an uncharged
  calibration reporter; no ledger was read or written. Q5: no AHEAD label.
- Q6: calibration language only. Q7: reproduction applies. Q9: the summary
  and per-row losses permit independent recomputation; source and route hashes
  identify the reconstructible model state.

## NOT VERIFIED

- The S05 recalibration route is positional because the base corpora do not
  establish chronological ordering. This comparison does not claim a new
  purged or embargoed out-of-sample result.
- The 30-cluster rail prevents MATCH or BEHIND labels for NBA, MLB, and soccer.
- Tennis historical prices remain SYNTHETIC-vintage and are not verified as
  pregame closes.
- No independent verifier has yet rerun the committed artifact in master.
