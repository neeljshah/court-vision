# S273 MLB in-game latency screen (2026-09-04)

## Premise

S213 reports MLB GUMBO captured_at minus ts p50 41.0 s and p90 102.0 s.
S254 committed denominator is 47104 evaluated ticks, 14611 informative ticks, and 158 informative game clusters.
The resolved local input store was readable before scoring.

## Seal, route, and inputs

Preregistration: `docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md`; seal SHA-256 `c00dc738ec7882ac50cec06eb8d82b448105dd721cb3948fb918cbce75e53da3`.
S254 route SHA-256: `bac7a7e6da8e290646c219729db6f17f822056464b0617cc3d0b976ae0edf142`; S273 runner SHA-256: `68e8f04bc689b7a3636c22115b9c3a399b84d350651a74c9a607cc731ad9b063`.
CPCV used the inherited purge and symmetric 1-day embargo in every arm. No flags, registry, ledger, or serving artifact changed.
Inputs:

- `docs/evidence/harness/S213_ingame_latency_summary_2026-09-04.json` (42725 bytes; structured JSON latency summary).
- `docs/evidence/harness/S254_mlb_phase_recal_fwer_sealed_2026-09-04_summary_attempt2.json` (88758 bytes; structured JSON CPCV summary).
- `data/cache/ingame_grade_joined` (73485324 bytes; structured JSONL tick store).

## Three-arm results

### none (delay 0.0 s)

| bucket | delta | CI95 | raw p | BH p | BH survivor | clusters |
|---|---:|---|---:|---:|---|---:|
| early\|leading | +0.006505 | [-0.009304, +0.022207] | 0.420529 | 0.700882 | false | 103 |
| early\|leading_big | -0.002373 | [-0.019724, +0.017578] | 0.805009 | 0.907362 | false | 33 |
| early\|tied | -0.000692 | [-0.012424, +0.010924] | 0.907362 | 0.907362 | false | 157 |
| early\|trailing | -0.011605 | [-0.023353, -0.000076] | 0.059005 | 0.311641 | false | 101 |
| early\|trailing_big | -0.003020 | [-0.012361, +0.005721] | 0.517886 | 0.706209 | false | 42 |
| late\|leading | +0.007877 | [-0.013330, +0.030053] | 0.473326 | 0.706209 | false | 67 |
| late\|leading_big | +0.015260 | [+0.000861, +0.031782] | 0.062328 | 0.311641 | false | 59 |
| late\|tied | -0.021503 | [-0.047436, +0.004828] | 0.114012 | 0.325866 | false | 49 |
| late\|trailing | -0.012657 | [-0.024002, -0.002865] | 0.030280 | 0.311641 | false | 63 |
| late\|trailing_big | -0.003000 | [-0.011118, +0.002486] | 0.386273 | 0.700882 | false | 61 |
| mid\|leading | +0.005632 | [-0.006915, +0.017876] | 0.368791 | 0.700882 | false | 93 |
| mid\|leading_big | +0.000696 | [-0.006765, +0.008608] | 0.860043 | 0.907362 | false | 54 |
| mid\|tied | -0.003599 | [-0.016376, +0.009027] | 0.576773 | 0.720966 | false | 85 |
| mid\|trailing | -0.006301 | [-0.013997, +0.001320] | 0.114619 | 0.325866 | false | 76 |
| mid\|trailing_big | -0.004999 | [-0.011486, +0.001026] | 0.130346 | 0.325866 | false | 53 |

### p50 (delay 41.0 s)

| bucket | delta | CI95 | raw p | BH p | BH survivor | clusters |
|---|---:|---|---:|---:|---|---:|
| early\|leading | +0.006506 | [-0.009303, +0.022211] | 0.420541 | 0.700901 | false | 103 |
| early\|leading_big | -0.002379 | [-0.019726, +0.017569] | 0.804573 | 0.906869 | false | 33 |
| early\|tied | -0.000696 | [-0.012429, +0.010921] | 0.906869 | 0.906869 | false | 157 |
| early\|trailing | -0.011615 | [-0.023365, -0.000083] | 0.058891 | 0.311641 | false | 101 |
| early\|trailing_big | -0.003026 | [-0.012371, +0.005736] | 0.517331 | 0.705452 | false | 42 |
| late\|leading | +0.007877 | [-0.013330, +0.030053] | 0.473326 | 0.705452 | false | 67 |
| late\|leading_big | +0.015260 | [+0.000861, +0.031782] | 0.062328 | 0.311641 | false | 59 |
| late\|tied | -0.021503 | [-0.047436, +0.004828] | 0.114012 | 0.325835 | false | 49 |
| late\|trailing | -0.012657 | [-0.024002, -0.002865] | 0.030280 | 0.311641 | false | 63 |
| late\|trailing_big | -0.003000 | [-0.011118, +0.002486] | 0.386273 | 0.700901 | false | 61 |
| mid\|leading | +0.005632 | [-0.006915, +0.017877] | 0.368735 | 0.700901 | false | 93 |
| mid\|leading_big | +0.000697 | [-0.006765, +0.008608] | 0.860029 | 0.906869 | false | 54 |
| mid\|tied | -0.003597 | [-0.016375, +0.009030] | 0.576976 | 0.721220 | false | 85 |
| mid\|trailing | -0.006300 | [-0.013995, +0.001322] | 0.114666 | 0.325835 | false | 76 |
| mid\|trailing_big | -0.004999 | [-0.011487, +0.001025] | 0.130334 | 0.325835 | false | 53 |

### p90 (delay 102.0 s)

| bucket | delta | CI95 | raw p | BH p | BH survivor | clusters |
|---|---:|---|---:|---:|---|---:|
| early\|leading | +0.006507 | [-0.009305, +0.022226] | 0.420558 | 0.700930 | false | 103 |
| early\|leading_big | -0.002399 | [-0.019755, +0.017547] | 0.802944 | 0.906816 | false | 33 |
| early\|tied | -0.000697 | [-0.012432, +0.010923] | 0.906816 | 0.906816 | false | 157 |
| early\|trailing | -0.011624 | [-0.023369, -0.000081] | 0.058711 | 0.311641 | false | 101 |
| early\|trailing_big | -0.003011 | [-0.012296, +0.005746] | 0.518396 | 0.706904 | false | 42 |
| late\|leading | +0.007877 | [-0.013330, +0.030053] | 0.473326 | 0.706904 | false | 67 |
| late\|leading_big | +0.015260 | [+0.000861, +0.031782] | 0.062328 | 0.311641 | false | 59 |
| late\|tied | -0.021503 | [-0.047436, +0.004828] | 0.114012 | 0.325727 | false | 49 |
| late\|trailing | -0.012657 | [-0.024002, -0.002865] | 0.030280 | 0.311641 | false | 63 |
| late\|trailing_big | -0.003000 | [-0.011118, +0.002486] | 0.386273 | 0.700930 | false | 61 |
| mid\|leading | +0.005634 | [-0.006914, +0.017877] | 0.368523 | 0.700930 | false | 93 |
| mid\|leading_big | +0.000698 | [-0.006763, +0.008609] | 0.859745 | 0.906816 | false | 54 |
| mid\|tied | -0.003593 | [-0.016371, +0.009030] | 0.577396 | 0.721746 | false | 85 |
| mid\|trailing | -0.006299 | [-0.013994, +0.001324] | 0.114701 | 0.325727 | false | 76 |
| mid\|trailing_big | -0.005000 | [-0.011488, +0.001025] | 0.130291 | 0.325727 | false | 53 |

## Largest-delta comparison

| arm | delay s | BH survivors | largest bucket | largest delta | CI95 | informative game clusters |
|---|---:|---:|---|---:|---|---:|
| none | 0.0 | 0 | late\|leading_big | +0.015260 | [+0.000861, +0.031782] | 158 |
| p50 | 41.0 | 0 | late\|leading_big | +0.015260 | [+0.000861, +0.031782] | 158 |
| p90 | 102.0 | 0 | late\|leading_big | +0.015260 | [+0.000861, +0.031782] | 158 |

The comparison is a calibration measurement only. The per-arm paired-loss CSV archives game id, source ts, shifted state_ts, both losses, and arm delay for recomputation.

## Self-check

- Q1: preregistration was committed and its LF staged-byte seal was verified from HEAD before the first score.
- Q4: all three arms use cpcv_evaluate with the inherited purge and symmetric nonzero embargo.
- Q9: each arm archives its paired-loss series and its shifted state timestamp.
