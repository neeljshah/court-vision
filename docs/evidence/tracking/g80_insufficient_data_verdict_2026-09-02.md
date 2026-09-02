# G80: insufficient data is a verdict, not a PASS

## Result

ACCEPT WITH CORRECTIONS. G80 reverses the prior adjudication recorded by G50B:
when `n_frames < MIN_FRAMES_FOR_METRICS` (30), a report now has
`passed=false`, `verdict="INSUFFICIENT_DATA"`, and one explicit reason in
`failures`. The existing nulling of n-dependent normal-report metrics is
unchanged. `INSUFFICIENT_DATA` is distinct from `FAIL`: no quality bar was
measurable. No threshold or adequate-data verdict moved.

## Three-size reproduction

The single court-feet fixture has ten players per frame. Its first ten frames
are in bounds; frames 10--25 place six players out of bounds. At 40 frames it
therefore has `oob_pct=0.24`. All n-dependent metrics are already null below
30 frames.

| n_frames | Before passed / verdict / failures | After passed / verdict / failures | oob_pct after |
|---:|---|---|---:|
| 3 | `true` / `PASS` / `[]` | `false` / `INSUFFICIENT_DATA` / `['insufficient data: 3 frames < 30']` | `null` |
| 10 | `true` / `PASS` / `[]` | `false` / `INSUFFICIENT_DATA` / `['insufficient data: 10 frames < 30']` | `null` |
| 40 | `false` / `FAIL` / `['oob 0.24 > 0.05']` | unchanged | `0.24` |

This is the false-PASS category being corrected: a table that cannot measure
its quality cannot pass merely because its metrics were nulled.

## Historical replay and flip list

The read-only pod raw-table corpus at `data/tracking/*/tracking_data.csv`
contains 184 tables: two nonempty tables are below 30 distinct frames and
eight are empty. The empty tables already use the existing zero-frame failed
report path and do not set `insufficient_data`.

Ten existing raw tables were replayed with the pod's pre-G80 harness in its
audited legacy mode. The pod has not received this change; the after verdict
is the deterministic G80 adjudication of the replayed report. Eight adequate
reports remain `FAIL`; the WNBA source retains its pre-existing coordinate
contract `FAIL` before it can form a scorable report.

| Existing table | source n_frames | Before verdict | After verdict |
|---|---:|---|---|
| `tennis_07` | 4 | `FAIL` | `INSUFFICIENT_DATA` |
| `tennis_09` | 2 | `FAIL` | `INSUFFICIENT_DATA` |
| `football_Z8Ezd95NnjM` | 79 | `FAIL` | `FAIL` |
| `football_yahhMkUWd7c` | 268 | `FAIL` | `FAIL` |
| `kbo_08` | 1436 | `FAIL` | `FAIL` |
| `mlb_2026-08-30_2143de43` | 1763 | `FAIL` | `FAIL` |
| `npb_06` | 565 | `FAIL` | `FAIL` |
| `soccer_c1mzmBGHQr4` | 292 | `FAIL` | `FAIL` |
| `tennis_04` | 3789 | `FAIL` | `FAIL` |
| `wnba_kangps_g2` | 5987 | `FAIL` (coordinate contract) | `FAIL` |

**Flip count: 2.** `tennis_07` (4 frames) and `tennis_09` (2 frames) are the
complete nonempty thin population in the current 184-table corpus. They are
reclassified from `FAIL` to `INSUFFICIENT_DATA`; that is not an adequate-data
result being disturbed. The false PASS correction is independently reproduced
at 3 and 10 frames above. No adequate-data report changed verdict, so this is
not a REJECT.

The current pod `data/tracking_reports` directory contains only two
report-shaped JSON files, both zero-frame `FAIL`s, rather than G50B's prior
187-report snapshot. This is report-corpus drift, not evidence that the
current raw-table replay can be skipped.

## Implementation and reader audit

`_adjudicate_insufficient_data()` runs only when the existing
`insufficient_data` flag is true. It changes `passed`, `verdict`, and the
failure explanation. Normal reports are still masked through the existing
`_N_DEPENDENT_METRIC_FIELDS` loop before that adjudication. The metric-local
early-return path uses the same explicit insufficient-data verdict; it was
already non-passing but must not retain a PASS-prefixed verdict when too thin.

Every `tracking_harness` importer was enumerated. Consumers that read
`passed` (`adapter_run.py`, `footage_bridge.py`, `corpus_rescore.py`, and the
tracking corpus tools) now correctly treat insufficient data as non-passing.
The direct verdict presentation readers either preserve the string
(`tracking_brain.py`) or derive their own PASS/FAIL display from `passed`
(`basketball_relabel_image_px.py` and `tracking/tennis_sequential_plan.py`);
none throws on `INSUFFICIENT_DATA`. No field was renamed, removed, or given a
different type. The binary display readers are not changed in this verdict-only
row and therefore display this distinct non-pass state as FAIL in their own
two-state output.

## Verification

Exactly one new per-file test was added and run; no full test suite was run.

```text
python -m pytest scripts/platformkit/test_tracking_harness_g80_insufficient_data.py -q
1 passed in 0.51s
```

The test reproduces all three required sizes and also covers the metric-local
early return. It asserts the normal-path n-dependent fields remain null below
30, the failure reason is nonempty, and the 40-frame OOB `FAIL` is unchanged.
`git diff --check` passed. The threshold-diff check found no changed threshold
or frame floor.

## VERIFIER_CONTRACT self-check

- **A7:** Confirmed at memo time that this memo, the [G80 spec](specs/G80_spec.md), the [verifier contract](VERIFIER_CONTRACT.md), [tracking_harness.py](../../../scripts/platformkit/tracking_harness.py), [the new G80 test](../../../scripts/platformkit/test_tracking_harness_g80_insufficient_data.py), and [the updated G50B regression](../../../scripts/platformkit/test_tracking_harness_g50b.py) exist.
- **B1:** No report rows are excluded; normal metrics are computed before their existing insufficient-data mask.
- **B2:** No field is renamed, removed, or retyped. The one new verdict value was checked against all harness import readers above.
- **B3:** No absent-evidence gate or quarantine path changed.
- **B4:** No claim, queue, or retry path changed.
- **B5:** The pod was read only: no deployment, copy, restart, daemon action, or kill occurred.
- **B6:** No module moved or retired; the token-owned harness remains imported at its existing path.
- **B7:** This is an exhaustive constructed three-size verdict reproduction, not render or head-slice evidence.
- **B8:** No fit or self-fit metric is asserted.
- **B9:** Historical sizes are distinct-frame counts from the canonical raw-table glob; the three-size fixture includes every constructed row.
- **B10:** `MIN_FRAMES_FOR_METRICS` and all threshold maps are unchanged; the diff check found no movement.

## NOT VERIFIED

- The historical 187-report pod JSON snapshot cited by G50B is no longer present; only two zero-frame report JSONs remain. The raw-table corpus was replayed instead.
- No pod deployment occurred; the verifier owns landing this release on the pod.
- No full test suite or production reader run was performed; only the required new per-file test was run.
