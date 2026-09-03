# G179: evaluated-frame coverage denominator, with max_frames semantics pinned

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) A5, A7, B1-B10,
Q3, Q7, and Q8. This is an additive implementation and reproduction. No pod
file, daemon process, bar, eligibility rule, coordinate contract, or historical
ledger value was changed.

## Premise re-measured from quoted pod code (Q8)

`scripts/platformkit/adapter_run.py` on the pod declares and passes the default:

```python
81:    parser.add_argument("--max-frames", type=int, default=30000)
100:    plan = sampling_plan(metadata.get("frame_rate"))
101:    options = {"max_frames": args.max_frames, "stride": plan.stride}
```

The cap is on evaluated samples, not raw source reads and not emitted rows. The
baseball adapter, which produced the MLB/KBO/NPB rows in the reproduction,
states:

```python
198:            while max_frames is None or processed < max_frames:
199:                ok, frame = capture.read()
202:                if source_frame % stride == 0:
251:                    processed += 1
252:                source_frame += 1
```

The same control flow is present in all adapter routes: soccer lines 101/104/130,
tennis lines 215/223/240, and football lines 93/96/120. `capture.read()` and
`source_frame += 1` run for every source frame; `processed += 1` runs only on a
stride-selected frame. Therefore `max_frames` limits `processed`, which is the
number of evaluated frames.

`decoded_frames` is not truncated by that cap. Completion calls
`decoded_frame_count`, whose quoted implementation runs
`ffprobe -count_frames -select_streams v:0 -show_entries stream=nb_read_frames`
against the video and rejects an ambiguous result. It counts the entire decoded
source stream after tracking and before source retention; it does not read a CSV
or adapter counter.

## Formula and implementation

For decoded source-frame count `D`, source fps `f`, and adapter maximum `M`:

```text
s = max(1, round(0.1 * f))
N = ceil(D / s)
E = min(N, M)
evaluated source indices = 0, s, 2s, ..., (E - 1)s
```

The last index is below `D` because `E <= ceil(D/s)`. The implementation pads
only those `E` source indices before invoking the frozen harness. If source fps
is absent, it keeps the old decoded-frame padding and persists neither a stride
nor an evaluated count; absence is not treated as a failure or guessed into a
sampling plan.

Three strictly additive fields are now persisted on new sidecars and ledger
rows: `harness_coverage_pct` (the frozen harness quantity that decides
`passed`), `evaluated_frames`, and `stride`. The pre-existing ledger
`coverage_pct` remains the decode-manifest completeness value and is neither
renamed nor repurposed. Old sidecars remain readable because the required
legacy-key set was not tightened.

## Manifest compatibility cross-check

There remains exactly one `frame_manifest.csv` on the pod, at
`g172_cv2_environment_gap_20260903_a5`; it is not used by this landing. Its
28,773 data rows run from source frame 0 through 28,772, and every row declares
`evaluated=True`. It has no ledger row or persisted source fps. Its declared
stride is consequently 1, so the formula gives
`min(ceil(28773 / 1), 30000) = 28773`, agreeing exactly with its 28,773 actual
evaluated rows. This is a read-only compatibility check, not a retry of G178's
unavailable manifest route.

## Exhaustive pod reproduction (Q7)

One read-only batched pod pass found 21 directories with `tracking_data.csv`.
Eighteen have a reachable daemon ledger row carrying both `decoded_frames` and
`source_fps`, so all eighteen are in the table. The three excluded directories
are named below; none is silently omitted.

`ledger coverage` is the pre-existing `coverage_pct`, reproduced only to show
that it is unchanged. `gate coverage` is the frozen harness coverage used by
`passed`: before pads all `D` source frames; after pads the formula's evaluated
set. Every after value is in [0, 1], without clamping. `F -> F` means the
verdict remains fail.

| game | D | s | E | ledger coverage | gate coverage before -> after | verdict |
|---|---:|---:|---:|---:|---:|---|
| kbo_01 | 69,170 | 6 | 11,529 | 0.1573 | 0.0000 -> 0.0000 | F -> F |
| kbo_02 | 48,506 | 6 | 8,085 | 0.1561 | 0.0000 -> 0.0000 | F -> F |
| kbo_03 | 46,976 | 6 | 7,830 | 0.1499 | 0.0000 -> 0.0000 | F -> F |
| kbo_04 | 71,710 | 6 | 11,952 | 0.1571 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_03d78bee | 37,862 | 6 | 6,311 | 0.1597 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_08b16ce9 | 49,346 | 6 | 8,225 | 0.1583 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_0f36e8cc | 49,079 | 6 | 8,180 | 0.1607 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_10893dca | 39,035 | 6 | 6,506 | 0.1565 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_1c6706c6 | 40,216 | 6 | 6,703 | 0.1575 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_2143de43 | 43,564 | 6 | 7,261 | 0.1593 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_2b814fad | 40,179 | 6 | 6,697 | 0.1586 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_3a02d9b3 | 36,925 | 6 | 6,155 | 0.1563 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_7e8080e5 | 41,029 | 6 | 6,839 | 0.1567 | 0.0000 -> 0.0000 | F -> F |
| mlb_2026-08-30_f8812b72 | 59,754 | 6 | 9,959 | 0.1587 | 0.0000 -> 0.0000 | F -> F |
| npb_01 | 426,072 | 3 | 30,000 | 0.0656 | 0.0000 -> 0.0000 | F -> F |
| soccer_c1mzmBGHQr4 | 181,050 | 3 | 30,000 | 0.0808 | 0.0000 -> 0.0000 | F -> F |
| soccer_kSgNjoaqCpI | 182,100 | 3 | 30,000 | 0.0806 | 0.0000 -> 0.0000 | F -> F |
| tennis_ref01 | 28,773 | 3 | 9,591 | 0.0252 | 0.0248 -> 0.0745 | F -> F |

The 14 baseball-family rows remain failed at `coordinate_contract` before
coverage is a quality decision; this is not a baseball rescue. The two soccer
rows fail the same contract. Tennis remains below the unchanged 0.90 coverage
bar and has additional failure heads. No row flips fail to pass.

Excluded, named rows: `football_wHZt1eY3A9s` has a CSV and source fps but no
ledger row or decoded count; `g172_cv2_environment_gap_20260903_a5` has no
ledger row or source fps; `tennis_smoke` has no ledger row, decoded count, or
source fps. They cannot support the formula and were not assigned an estimate.

## Checks

- A5: searched readers of `harness_coverage_pct`, `evaluated_frames`, and
  `stride`. The new fields have only their producer, ledger persistence, and
  focused tests; no existing reader depends on a renamed field.
- A7: this memo exists at its named evidence path before commit.
- B1/B9: the reproduction names all 18 reachable rows and all 3 exclusions;
  evaluated counts derive from source timing and remain nonconstant.
- B2/B3/B4/B6: fields are additive, old sidecars remain readable, absent fps
  preserves the old denominator rather than quarantining, and no module moved.
- B5: the pod work was read-only and batched; no code or artifact was copied,
  no daemon was killed, restarted, or deployed.
- B7/B8: Q7 reproduction replaces an eye check; no sampled slice or fitted
  quantity is claimed.
- B10/Q3: `git diff --exit-code -- scripts/platformkit/tracking_harness.py`
  returned clean. The implementation diff contains no `coverage_min`,
  `min_players`, eligibility, coordinate-contract, or verdict-bar edit. The
  pre-existing dirty G179 spec was preserved and not staged.

## Tests

```text
python -m pytest scripts/platformkit/test_track_daemon_done.py -q
6 passed in 8.89s

python -m pytest scripts/platformkit/test_track_daemon.py -q
29 passed in 7.08s

python -m pytest scripts/platformkit/test_track_daemon_ledger_denominator.py -q
1 passed in 8.05s
```

## NOT VERIFIED

- The new additive fields have not yet been written by a natural post-accept
  daemon completion. Deploying or restarting the daemon is explicitly out of
  scope.
- The sole retained manifest lacks its own source-fps and ledger provenance, so
  it verifies the declared stride-1 count but not an adapter-run fps lookup.
- Rows without both a persisted decoded count and source fps remain
  unreconstructible and are named above rather than inferred.
