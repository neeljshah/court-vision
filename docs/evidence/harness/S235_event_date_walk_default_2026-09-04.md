# S235 Event-Date Walk Default (FALSIFIED)

## Verdict

FALSIFIED at the required premise check. No runtime default was changed, no
corpus was opened, no scored probability was produced, and no test was added.
Q8 of `docs/evidence/tracking/VERIFIER_CONTRACT.md` requires this close when a
row premise is false. This is not `CLOSED AT LIMIT`: no frozen S05 or S22 bar
was reached or changed.

## Preregistration and machine

The preregistration was written and sealed before the archive comparison:

```text
docs/evidence/harness/S235_event_date_walk_default_prereg_2026-09-04.md
pre-seal SHA-256: FDD9D398318DF2F1ED7283280BCC3F45B125969281A84C312062F00B236F22C0
```

All work was local in `C:\Users\neelj\nba-track-a18`. No input has a visual
resolution. The static inputs opened were:

| path | bytes | SHA-256 |
|---|---:|---|
| `docs/evidence/tracking/specs/S235_spec.md` | 3862 | `08426376BA52564AC00F228C91A5D23C9E6AFC34A1B3F8A1DFE7AE1AA023861E` |
| `docs/evidence/tracking/VERIFIER_CONTRACT.md` | 11979 | `D093543E5A08B08F54AEB3B0BE15F11A5EB1C8F23E02E7344E12B8D53F94AE15` |
| `scripts/platformkit/combo/batch_gate.py` | 15520 | `CB29AE36153B693E2BA4684AD77D0158282FED733C050395A70FD1040A8B5516` |
| `scripts/platformkit/eval_gate/calibration_report.py` | 13915 | `49ECE331A2467E6E7ED1BBD65A21CAA4719C8B75AE9372CA900964E97C63B9A1` |
| `scripts/platformkit/eval_gate/s200_regime_key_oof.py` | 14776 | `0F4E0EA1A9C88D4DAC4D59FAF1642241DBE5F5F13DE601A49AB44951F41249D6` |
| `scripts/platformkit/eval_gate/walkforward.py` | 8207 | `1058F981A328121802A996E8D46FF9502212A026918C723B7EBE28F49DCE0C69` |
| `scripts/platformkit/eval_gate/cpcv_engine.py` | 6990 | `D91983E8410E4F7072A3D74E6B61C44420F66E64FE384EA802D4385F4D052CB9` |

Additional static inputs opened, each with no visual resolution, were
`docs/evidence/harness/S233_walkforward_embargo_prereg_2026-09-04.md` (5604
bytes), `docs/evidence/harness/S50_per_unit_chronology_2026-09-03.md` (12986
bytes), `docs/evidence/harness/S05_calibration_prereg_2026-09-03.md` (1600
bytes), `docs/evidence/harness/S05_calibration_report_2026-09-03.md` (9953
bytes), `docs/evidence/harness/S22_mechanisms_soccer_tennis_2026-09-03.md`
(10489 bytes), `scripts/platformkit/l4/prereg_sha_stamp.py` (4532 bytes),
`scripts/platformkit/eval_gate/test_calibration_report.py` (9937 bytes), and
`scripts/platformkit/combo/corpus_cache.py` (7702 bytes).

## Archive-only reproduction

The eight committed S50 JSON artifacts were read directly; the four corpora
were not opened. Stored values reproduce the declared positional/per-unit
pairs with maximum absolute difference `1.7347234759768071E-18` (floating
representation only), below `1e-9`. All stored artifacts report zero dropped
rows.

| archive path | bytes | visual resolution |
|---|---:|---|
| `docs/evidence/calibration/nba_reliability_2026-09-03.json` | 6933 | none |
| `docs/evidence/calibration/nba_reliability_per_unit_2026-09-03.json` | 7522 | none |
| `docs/evidence/calibration/mlb_reliability_2026-09-03.json` | 6766 | none |
| `docs/evidence/calibration/mlb_reliability_per_unit_2026-09-03.json` | 7419 | none |
| `docs/evidence/calibration/soccer_reliability_2026-09-03.json` | 6947 | none |
| `docs/evidence/calibration/soccer_reliability_per_unit_2026-09-03.json` | 8472 | none |
| `docs/evidence/calibration/tennis_reliability_2026-09-03.json` | 7024 | none |
| `docs/evidence/calibration/tennis_reliability_per_unit_2026-09-03.json` | 7585 | none |

| sport | rows | positional after-ECE | per-unit after-ECE | partition identity |
|---|---:|---:|---:|---|
| nba | 1814 | 0.024842541854003943 | 0.026583410555831620 | True |
| mlb | 39162 | 0.008076824645850213 | 0.012665595930047123 | True |
| soccer | 25834 | 0.009301788688995382 | 0.028722088828783483 | False |
| tennis | 41886 | 0.008403089761848824 | 0.015402723519068535 | True |

Soccer is explicitly retained as the unfavorable per-unit calibration result:
its six divisions interleave, so partition identity is false. Tennis likewise
retains the WTA-dominated per-unit calibration cost recorded by S50.

## Falsified caller and evaluator premises

The exact claimed `scripts/platformkit/combo/batch_gate.py:193` line is:

```python
corpus = load_gate_corpus(sport)
```

It is not a call to `calibration_report.build_report` or `main`, and it cannot
omit `--per-unit`. The direct code census found no external `main` invocation.
The sole non-test `build_report` caller is
`scripts/platformkit/eval_gate/s200_regime_key_oof.py:207-218`; it calls the
library function directly, so a one-line CLI flag proposal is not applicable.
`ingame_calibration_report.py` imports only `_from_bins`; S202, S204, and S205
import only `_oof_per_regime`; their source references do not invoke `main`.
No `docs/research/organization-sprint/` proposal was written because the
required batch-gate caller does not exist in this tree.

The live calibration route also calls `walk_forward_recalibrate` in
`s200_regime_key_oof.py`, not `walk_forward` or `cpcv_evaluate` from the shared
evaluator. Therefore any new corpus score through the existing route would
violate the required Q4 evaluator callback, purge, and symmetric nonzero
embargo contract. Replacing that route would be a materially different change
from S235's additive main-default flip and could not honestly be asserted to
reproduce the archived values before it was separately specified and sealed.

## Verifier self-check

- B1-B10: no scored corpus comparison, schema change, gate change, deployment,
  or deletion was made.
- Q1: the preregistration path and pre-seal SHA-256 are above and predate the
  archive-only comparison.
- Q3: S05 and S22 bars are unchanged.
- Q4: satisfied by refusal to score through the noncompliant route.
- Q6: calibration language only.
- Q7: all four declared construct members were read from their committed
  artifacts.
- Q8: satisfied by the exact false `batch_gate.py:193` premise above.

## Not run

`python -m scripts.platformkit.eval_gate.calibration_report`, any corpus load,
and a new focused test were intentionally not run. They would implement or
score after a premise-failure close rather than execute the contract-valid
route. The register, results ledger, `data/`, and `data/registry/` are
unchanged.

# ATTEMPT 2 - default correction (NOT VERIFIED)

## Retraction and sealed preregistration

Attempt 1's FALSIFIED conclusion is retracted. The verifier established that
the S235 premise was true: with no flags, `calibration_report.main` still used
the positional-order walk. The unrelated `batch_gate.py:193` citation did not
falsify that operative default.

Before this attempt performed any fresh corpus scoring, the preregistration was
resealed in commit `69770f3ca67303be0ef56e95112fe9c8abefd410`:

```text
docs/evidence/harness/S235_event_date_walk_default_prereg_2026-09-04.md
seal SHA-256: 76DFAB9C7F8DCF67947AC1AEF316B5B7600E6A73F8F6B008563F9948B629FB43
rule: SHA-256 of exact UTF-8 committed bytes through the newline before the seal line
```

The committed-byte rule was recomputed after the last preregistration edit. It
replaces Attempt 1's invalid claimed seal
`FDD9D398318DF2F1ED7283280BCC3F45B125969281A84C312062F00B236F22C0`.

## Corrected default and archival before/after table

`scripts/platformkit/eval_gate/calibration_report.py:259` now sets
`per_unit = "--positional" not in (list(argv) if argv is not None else sys.argv[1:])`.
The existing `--per-unit` spelling remains an inert compatibility alias because
the corrected default is already per-unit. The archived values below are the
fixed S50 comparison, not a fresh Q4-qualified metric run.

| sport | rows | before: positional default after-ECE | after: event-date default after-ECE | `--positional` expected after-ECE |
|---|---:|---:|---:|---:|
| nba | 1814 | 0.024842541854003943 | 0.026583410555831620 | 0.024842541854003943 |
| mlb | 39162 | 0.008076824645850213 | 0.012665595930047123 | 0.008076824645850213 |
| soccer | 25834 | 0.009301788688995382 | 0.028722088828783483 | 0.009301788688995382 |
| tennis | 41886 | 0.008403089761848824 | 0.015402723519068535 | 0.008403089761848824 |

All archived rows report zero dropped rows. Soccer remains unfavorable and its
six divisions interleave, so `walk_partition_is_identity` is false. Tennis
retains the WTA-dominated calibration cost recorded in S50.

## Caller census and tests

The source census found `calibration_report.main` has no external invocation.
`scripts/platformkit/combo/batch_gate.py:193` only loads a corpus. The sole
non-test direct `build_report` caller is
`scripts/platformkit/eval_gate/s200_regime_key_oof.py:207-218`, which calls the
library function and cannot take a CLI flag. No caller proposal is written: a
one-line `--per-unit` addition would be both inapplicable to that library call
and redundant because that spelling is now a no-op alias.

- `python -m pytest tests/platformkit/test_s235_event_date_walk_default.py -q -p no:cacheprovider` -> `1 passed in 5.31s`
- `python -m pytest scripts/platformkit/eval_gate/test_calibration_report.py -q -p no:cacheprovider` -> `10 passed in 3.66s`
- `python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> `1 passed in 1.55s`

## NOT VERIFIED

The required fresh four-sport regeneration is NOT VERIFIED under Q4. The gate
corpora expose `event_id`, `corpus_unit`, `event_date`, `y`, and model columns;
they do not expose the shared evaluator's required state fields such as
`state_ts`, `home`, `away`, `outcome`, feature availability, and vintage.
Further, `calibration_report.main` calls its local
`oof_per_regime` recalibration route rather than `walk_forward` or
`cpcv_evaluate`. Running that entry point would create a new scored comparison
outside the required purge plus symmetric nonzero embargo route, so it was not
run and no calibration JSON was regenerated in Attempt 2.

No threshold, schema, register, results ledger, `data/`, or
`data/registry/**` content was changed. The corrected selection behavior is
tested; the four numeric default values remain archival references pending a
separately specified Q4-compatible adapter.
