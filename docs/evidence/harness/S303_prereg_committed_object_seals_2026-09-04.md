# S303 committed-object preregistration seals

## Verdict: ACCEPT

This local construct changes only its new focused test and dated evidence. It
does not score a model, read or write a ledger, write under `data/`, or change
a feature flag.

The preregistration is
`docs/evidence/harness/S303_prereg_committed_object_seals_2026-09-07.md`.
Its LF-normalized pre-seal SHA-256 is
`9d15650f1491bfcdebd9dee88c0b847483aa9e26745fecb697f6c894114770dc`.
The sandbox denies staging and commits, so this is the SHA-256 of the
LF-normalized bytes above its `SHA256_SEAL` line, not an index-object claim.

## Premise enumeration

The historical pre-audit checkout was remeasured at
`d9abb0bc2061b0b67f015d68961ae9f63c83a1ae`
(2026-09-04T14:10:59-05:00), without opening the unavailable local-only memo.
The 15 audit rows are five temporary-preregistration constructs, one
committed-spec pin, one already committed-object S261 primary reader, and the
following eight tracked-file seal test routes. The S303 target set is exactly
six explicit artifact paths, as declared in the S303 specification; it is not
called a set of ten.

| tracked test route | SHA-256 of unchanged route file | S303 anchor |
|---|---|---|
| `scripts/platformkit/test_s261_ingame_headline_rederive_v2_attempt2.py` | `29edef9baf35a625541c7df6c32b4a9a5b21e7ee86eb6c40bba039d0efc9221b` | S261 attempt-2 preregistration |
| `scripts/platformkit/ingame/test_s272_ingame_tail_recal.py` | `b1342a129ed6a3b2d0fa68019c5612329ff2ac319de80e051b2b432c185e2106` | separate runtime-held verification |
| `scripts/platformkit/ingame/test_s277_ingame_market_staleness.py` | `260cddca57df6e90baf0741cf270a1a14933193bbd7a438e668b6cfb8b883a7e` | separate runtime-held verification |
| `tests/platformkit/ingame/test_s265_incumbent_conformal_band_sample.py` | `76aadcf794bf0e9f195ad429802b7d8980dae47e5396c4c4f029d764043856e4` | S265 preregistration |
| `tests/platformkit/test_s268_distributional_evaluator_route.py` | `79c2c7a20f388ab9cad888c3db241278f4fcf4a9ad229de6e6f14d12646f7a2f` | S268 attempt-2 preregistration |
| `tests/platformkit/test_s270_ingame_power_feasibility.py` | `867bd9e97dedcbfdc11bb32eb274b018c7c5406e3bfacba1b3ffb525b65c3be5` | S270 v2 preregistration |
| `tests/platformkit/test_s273_mlb_ingame_latency_screen.py` | `ce62c564395ec32deafb25793c3e380bbf516434b2a46af604dbc7d4a86523b8` | S273 preregistration |
| `tests/platformkit/test_s274_mlb_distribution_evaluator_route.py` | `f07f288fcf11e314063e604823eef31671be7fab7ce5827d5a7e91bf09bb9371` | S274 preregistration |

## Six committed-object anchors

`tests/platformkit/test_prereg_committed_object_seals.py` reads each anchor
with `git show HEAD:<path>`. It preserves those committed bytes exactly, hashes
the bytes above the artifact's own seal line, and compares that digest to the
embedded seal. It invokes `git cat-file -e HEAD:<path>` only after `git show`
fails; a working-file fallback then normalizes CRLF to LF.

| path | bytes from `git show HEAD:<path>` | seal SHA-256 | match |
|---|---:|---|---|
| `docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md` | 3145 | `1dcb38b6cbb59694cd4a722aa843be9694905adc292b9a17ace9f95d29e984fb` | yes |
| `docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md` | 2405 | `17aa1f6cdee9207aa83fd8addcefb58931ade103fb464b72d5068a6a74f451f8` | yes |
| `docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md` | 3304 | `cfbeb06cb7678d45b892f9941fcab389b21039d8f8e592eed2ad256ea596eff3` | yes |
| `docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md` | 2491 | `561246d2d2bd4c6621cbdb96157c36df110a66e74a8295fca3521e357b56c32f` | yes |
| `docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md` | 2550 | `c00dc738ec7882ac50cec06eb8d82b448105dd721cb3948fb918cbce75e53da3` | yes |
| `docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md` | 3707 | `059b9f66161845a9582c99fab16c9fb3949e3f8c02f7d80940e5813fe91c3ed0` | yes |

No committed seal mismatch was found. The test never writes an existing seal.

## Dirty and fallback constructs

- Dirty-file case: a temporary git repository commits a sealed preregistration,
  then replaces its working file with different bytes. The selected bytes equal
  the committed object and differ from the dirty working file.
- Fallback case: a temporary repository contains an uncommitted CRLF
  preregistration. `git show` fails, `git cat-file -e` proves its absence, and
  the selected LF-normalized file bytes match the declared seal.

## Reproduction

`python -m pytest tests/platformkit/test_prereg_committed_object_seals.py -q -p no:cacheprovider`

Result: `8 passed in 1.08s`.

## Contract self-check

The result is a declared construct with six explicit paths, so no sample rail
applies. The bars and existing artifacts are unchanged. No deployment occurred.
No scored comparison, charge, ledger read, or register edit occurred. The
evidence is additive and uses calibration language only.

## NOT VERIFIED

- The orchestrator must commit the three S303 files before a verifier can
  reproduce the S303 preregistration through `git show HEAD:<path>`.
- The two runtime-held S272 and S277 checks are named in the eight-route audit
  table but are outside the six explicit artifact anchors declared by S303.
- A verifier must rerun the focused file from the committed landing and inspect
  at least one `git show HEAD:<path>` result by hand.
