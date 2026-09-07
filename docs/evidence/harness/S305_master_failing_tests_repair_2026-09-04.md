# S305 master failing-tests repair

Verdict: CLOSED AT LIMIT under the S305 preregistration and
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q1-Q9.

## Preregistration

The preregistration is
`docs/evidence/harness/S305_master_failing_tests_repair_prereg_2026-09-07.md`.
Its embedded seal is
`2DD1F3E6C53A283A6E5CD3CE7DE8E0DD3A48BC1017F7D9E2BD42EC793E8E0C83`.
The seal was recomputed from the LF-normalized bytes above its seal line before
the premise test. It matches the embedded value.

## Inputs and code identity

| Path | Bytes | SHA-256 | Resolution |
| --- | ---: | --- | --- |
| `scripts/platformkit/eval_gate/calibration_report.py` | 15004 | `52522E49F668A0A89386C7A0565F90C5BA481B35FAC41FF7C1849A42B6A27BF5` | n/a (source) |
| `scripts/platformkit/answers/test_calibration_scoreboard_regex.py` | 2950 | `940E57C3B2D037A1AC108084AEDB5F171490367E4752C2DEAEFDB442510763DC` | n/a (source) |
| `docs/evidence/calibration/nba_reliability_2026-09-03.json` | 7774 | `167250677F777FD1E1D5528A19CECE3CC4D883ED591139387452ACF69A04FC78` | n/a (JSON) |
| `6226fb042^:scripts/platformkit/eval_gate/calibration_report.py` | 16644 | `349E3578279E0A600D2404FA68F8162BE7FB94B3D816563F2A95E111205450D7` | n/a (historical source) |

## Premise and replay

Before any candidate was retained, `python -m pytest
scripts/platformkit/eval_gate/test_calibration_report.py -q -p
no:cacheprovider` returned 9 passed and 1 failed. The failure was the named
`ece_after` assertion: `0.024842541854003943` versus frozen artifact value
`0.039002202208806645`.

The specified historical `_oof_per_regime` was replayed verbatim from
`6226fb042^` against the current NBA corpus. It returned
`ece_after = 0.024842541854003943` over 1814 scored rows. Direct comparison of
its per-row outputs with the S212 `oof_per_regime` route produced maximum
absolute difference `0.0`. Thus the specified change cannot restore the locked
S05 value, and retaining it would be a no-op candidate that still fails the
locked 10/10 bar. No source or test candidate is retained.

## Pod execution

One scratch-only pod job was launched in `/workspace/wt/a19`, with no write to
the deployed tree. `POD_RUN_DONE` was observed and its JSON was fetched. The
pod's `/usr/local/bin/python` did not have `pytest`, so the master-form answers
test and all repaired test invocations exited before collection. This is an
environment limitation, not a passing count. The one-job limit prevents a
second dispatch with the discovered `/workspace/wt/_pylib/bin/pytest` route.

## Contract self-check

- B1-B4, B6-B10: no retained production or schema change.
- B5: one compute-only scratch execution; deployed pod tree untouched.
- Q1: preregistration seal predates the local premise result and replay.
- Q2: no charged trial and no ledger write.
- Q3: locked pass-count and `ece_after` bars were not changed.
- Q4, Q5, Q9: this is a two-file construct check, not an OOS comparison or an
  AHEAD claim.
- Q6: calibration language only.
- Q7: `n = 2 (CONSTRUCT)` enumerates both named files.
- Q8: the live premise was remeasured; it is false because the named historical
  routine and S212 are byte-identical in output on the current corpus.

## NOT VERIFIED

- The repaired answers test count is not verified: the only permitted pod job
  lacked `pytest`.
- No 10/10 or 4/4 post-change count is claimed.
- No candidate source or test change is ready to land because the locked
  `ece_after` bar remains unmet by the specified historical route.
