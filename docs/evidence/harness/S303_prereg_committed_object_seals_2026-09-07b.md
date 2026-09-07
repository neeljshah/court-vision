# S303 committed-object checker evidence

## Scope and preregistration

This local, additive S303 attempt implements the checker required by `docs/evidence/tracking/specs/S303_spec.md` VERSION 2026-09-07b. Its preregistration is `docs/evidence/harness/S303_prereg_committed_object_checker_2026-09-07b.md`. The SHA-256 of its LF-normalized 1451 pre-seal bytes is `04997d7e2b2e8e8731986ff99bc850fcbfbf2cadfca7554663035b7293f31b1d`.

The checker reads `git cat-file -p <revision>:<path>` after a successful `git cat-file -e`. It falls back only for Git's exact path-not-in-revision response, reports a missing working file as `ABSENT`, and returns a nonzero error for any other Git or object failure. The eight old readers and all existing preregistration artifacts were not edited.

## Eight behavioral mappings

Each focused case creates a temporary repository, commits the mapping's sealed path, writes different working-file bytes, and asserts selected content equals the committed bytes and differs from the working bytes. The final column is the live committed-object SHA-256 printed by the checker; the behavioral assertion is on fixture content equality, not this path or table row.

| Reader | Sealed path | Selection | Asserted committed-object SHA-256 |
| --- | --- | --- | --- |
| `scripts/platformkit/test_s261_ingame_headline_rederive_v2_attempt2.py` | `docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md` | committed | `53ee33196469425ad696a51bceb3216d9faa9277144330b4ca2b11660719be6e` |
| `scripts/platformkit/ingame/s272_ingame_tail_recal.py` | `docs/evidence/harness/S272_ingame_tail_recal_prereg_2026-09-04.md` | committed | `40781d73913b27e8d85fd9b016b6b1221bba40945a4c52a9587424f607fe7576` |
| `scripts/platformkit/ingame/s277_ingame_market_staleness.py` | `docs/evidence/harness/S277_ingame_market_staleness_prereg_2026-09-04_attempt2.md` | committed | `a13d81b90fe74a12ab7a0ad51359eb41e143dc9dae0d35fb0366dbd03d2b9e48` |
| `tests/platformkit/ingame/test_s265_incumbent_conformal_band_sample.py` | `docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md` | committed | `ea6017138a123d5bf8ffc5bf4fcfd485d621a167168b70e04a4fc4135550f3b2` |
| `tests/platformkit/test_s268_distributional_evaluator_route.py` | `docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md` | committed | `7bb9d50227faf331360d77e387cd6a25fe74dd4aec7f10de298e573758a7141e` |
| `tests/platformkit/test_s270_ingame_power_feasibility.py` | `docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md` | committed | `e7743fec398daf1027b79b868b4bfa8ba8b89939403e06706083a6479b2832ec` |
| `tests/platformkit/test_s273_mlb_ingame_latency_screen.py` | `docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md` | committed | `cb18ea1f28eb2242ebc29d7baf263f6e3d65fce47aea65c5a2df0ff328aea124` |
| `tests/platformkit/test_s274_mlb_distribution_evaluator_route.py` | `docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md` | committed | `ec46a5675fcf10dd938b17f6b08c3b28504b9fafff192ec3519bf06326388608` |

Result: 8/8 behavioral mappings selected committed fixture bytes under a dirty working file.

## Checker behavior

- DIRTY: all eight mappings selected committed bytes after their working files were changed.
- FALLBACK: a repository with a committed HEAD and an uncommitted `fallback.md` reported `FALLBACK` and returned its working bytes.
- ABSENT: a path missing from both HEAD and the working file reported `ABSENT`, not an error.
- ERROR: a non-repository root, a bad revision, and a deliberately unreadable temporary object each returned code 2 with `ERROR:` and the failing path. None was classified as absent.

## Retained anchor seals

| Path | Declared SHA-256 | Source | Match |
| --- | --- | --- | --- |
| `docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md` | `1dcb38b6cbb59694cd4a722aa843be9694905adc292b9a17ace9f95d29e984fb` | committed | yes |
| `docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md` | `17aa1f6cdee9207aa83fd8addcefb58931ade103fb464b72d5068a6a74f451f8` | committed | yes |
| `docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md` | `cfbeb06cb7678d45b892f9941fcab389b21039d8f8e592eed2ad256ea596eff3` | committed | yes |
| `docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md` | `561246d2d2bd4c6621cbdb96157c36df110a66e74a8295fca3521e357b56c32f` | committed | yes |
| `docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md` | `c00dc738ec7882ac50cec06eb8d82b448105dd721cb3948fb918cbce75e53da3` | committed | yes |
| `docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md` | `059b9f66161845a9582c99fab16c9fb3949e3f8c02f7d80940e5813fe91c3ed0` | committed | yes |

No committed seal mismatch was observed. The checker and tests never write a seal.

## Byte identity of old readers

The SHA-256 values below were recorded before the change and rechecked after it. Each is unchanged.

| Reader | SHA-256 before and after |
| --- | --- |
| `scripts/platformkit/test_s261_ingame_headline_rederive_v2_attempt2.py` | `29edef9baf35a625541c7df6c32b4a9a5b21e7ee86eb6c40bba039d0efc9221b` |
| `scripts/platformkit/ingame/s272_ingame_tail_recal.py` | `83f86f6a653a364c3e8047b58f5976128d69daeecc2a882dc82deffb78ca7c30` |
| `scripts/platformkit/ingame/s277_ingame_market_staleness.py` | `7f10fbec0d38d102decf4939b3fd150c77e5811dc73961e6d8d7627ad59c0ace` |
| `tests/platformkit/ingame/test_s265_incumbent_conformal_band_sample.py` | `76aadcf794bf0e9f195ad429802b7d8980dae47e5396c4c4f029d764043856e4` |
| `tests/platformkit/test_s268_distributional_evaluator_route.py` | `79c2c7a20f388ab9cad888c3db241278f4fcf4a9ad229de6e6f14d12646f7a2f` |
| `tests/platformkit/test_s270_ingame_power_feasibility.py` | `867bd9e97dedcbfdc11bb32eb274b018c7c5406e3bfacba1b3ffb525b65c3be5` |
| `tests/platformkit/test_s273_mlb_ingame_latency_screen.py` | `ce62c564395ec32deafb25793c3e380bbf516434b2a46af604dbc7d4a86523b8` |
| `tests/platformkit/test_s274_mlb_distribution_evaluator_route.py` | `f07f288fcf11e314063e604823eef31671be7fab7ce5827d5a7e91bf09bb9371` |

## Tests and local checks

- `python -m pytest tests/platformkit/test_prereg_committed_object_seals.py -q -p no:cacheprovider` -> 18 passed in 4.65s.
- `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed in 1.14s.
- `python -m scripts.platformkit.committed_object_checker` -> all eight live mappings reported `COMMITTED`.
- `scripts/platformkit/committed_object_checker.py` is 114 LOC, below the 300 LOC rail.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- No commit, archive landing, push, deployment, or pod action was performed in this sandbox.
- The eight old reader implementations retain their working-file behavior; only the additive checker selects committed objects.
- No register, ledger, data path, threshold, or feature flag was written.
