# S261 Attempt 2 In-Game Headline Re-Derivation v2

## Status: FULL CPCV ARCHIVE COMPLETE; PUBLIC VALUES NOT REPRODUCED

This local calibration re-derivation uses every admitted game path, does not sample, changes no corpus or public page, and writes neither the register nor the ledger.

## Sealed protocol and machine

- Spec: `docs/evidence/tracking/specs/S261_spec.md`.
- Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.
- Machine: local Windows worktree `C:\Users\neelj\nba-track-a13`.
- Preregistration: `S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md`.
- LF Git-blob seal: `1DCB38B6CBB59694CD4A722AA843BE9694905ADC292B9A17ACE9F95D29E984FB`.
- The preregistration was committed in `280035c56` before scoring. `git show HEAD:<path>` verifies zero CRLF bytes and this SHA-256 over bytes above its seal line.
- No charged trial was opened. K was unread. No pod copy or deployment occurred.

The fresh process scored all three arms inside `cpcv_evaluate` with eight timestamp groups, two test groups, a one-day symmetric calendar embargo, 48-hour same-team purge, three-day symmetric same-matchup protection, and strict test-view redaction. RSS remained below the 700 MB limit: NBA before 143.402 MB and after 169.711 MB; MLB before 170.035 MB and after 168.367 MB. The highest printed during-run RSS was 366.262 MB. No `MEMORY LIMIT` status occurred.

## Premise and denominators

Before scoring, the S211 paired-loss archives re-accumulated to NBA 0.21883250084408842 / 0.17235318274013006 / 0.16324678066236500 at n_eff 1313 and MLB 0.24897282410431543 / 0.12822834737953837 / 0.12799755953257377 at n_eff 23279, in static / score-only / conditional order.

MLB source parsing counted 2458 `invalid_inning` rows, where either innings field cannot be parsed, and 2246 `tied_final_score` rows, where parsed final totals are equal. These named exclusions occur before CPCV scoring and are not selected after loss evaluation. NBA has zero exclusions for either reason.

## Full CPCV metric table

| Sport | Static Brier | Score-only Brier | Conditional Brier | Total calibration change | Score-only share | Model-prior contribution | n_eff |
|---|---:|---:|---:|---:|---:|---:|---:|
| NBA | 0.21883250084408853 | 0.17235318274013145 | 0.16324678066236556 | 0.055585720181722975 | 0.8361737142561995 | 0.00910640207776589 | 1313 |
| MLB | 0.24897282410431879 | 0.1282283473795321 | 0.1279975595325734 | 0.12097526457174537 | 0.9980922724345702 | 0.00023078784695867993 | 23279 |

The game-clustered model-prior-share interval is [0.11469448235798907, 0.2268243890140245] for NBA and [0.0005919733087687374, 0.0032629680718753136] for MLB. The MLB interval does not cover zero; it is reported without changing any public-value status.

## Public-value comparison

The frozen public values are NBA static/conditional 0.209/0.159 and MLB static/conditional 0.241/0.126. The unchanged bar is max absolute difference <= 1e-6.

| Sport | Static difference | Conditional difference | Status |
|---|---:|---:|---|
| NBA | 0.00983250084408843 | 0.00424678066236500 | NOT REPRODUCED |
| MLB | 0.00797282410431543 | 0.00199755953257377 | NOT REPRODUCED |

## Additive schema and archive

The JSON retains every v1 field and meaning: `checkpoint_count` is raw scored checkpoints, `finite_resamples` is the finite game-cluster bootstrap draw count, and `reproduction_abs_diff` is the absolute serialization/reaccumulation difference for static, score-only, and conditional losses. `shares.total_calibration_change` is an additive alias equal to `shares.static_minus_conditional`; score-only share and model-prior contribution are retained. All reproduction differences are zero.

- Summary: `S261_ingame_headline_rederive_v2_attempt2_2026-09-04.json`.
- NBA paired state-loss archive: `S261_nba_per_state_losses_attempt2_2026-09-04.csv`.
- MLB paired state-loss archive: `S261_mlb_per_state_losses_attempt2_2026-09-04.csv`.

Each CSV records state id, game-cluster id, timestamp, raw checkpoint count, CPCV path-evaluation count, split ids, and static, score-only, and conditional paired losses. The summary records reconstructible input paths and byte sizes, CPCV settings, route hashes, aliases, exclusions, interval settings, n_eff, and exact public-value difference strings. The largest evidence file is 9,289,682 bytes, below 50 MB.

## NOT VERIFIED

- NBA static public-value comparison at the unchanged 1e-6 bar: NOT REPRODUCED.
- NBA conditional public-value comparison at the unchanged 1e-6 bar: NOT REPRODUCED.
- MLB static public-value comparison at the unchanged 1e-6 bar: NOT REPRODUCED.
- MLB conditional public-value comparison at the unchanged 1e-6 bar: NOT REPRODUCED.
- No claim is made outside the archived calibration re-derivation.
