# G190 detector determinism cause

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). This is a diagnosis-only
measurement. No `src/` file, threshold, `conf`, `imgsz`, detector backend
default, bar, verdict, daemon, or keeper was changed.

## Measurement verdict: ACCEPT - tuner-off alone is sufficient on this detector observation

The source of the observed raw-detector variance is the cuDNN benchmark tuner in
this environment. With the route-default FP16 call retained and no random seeds,
condition B (`cudnn.benchmark=False`) was bit-exact across three fresh processes.
The baseline condition A varied across all three. Seeding added no change to B,
and FP32 was also stable but is not needed to remove this variance.

This establishes the measured reason for the human-owned proposal: its
tuner-off component is sufficient for this isolated detector/frame/backend. It
does not apply that proposal and does not establish whole-route determinism.

## Fixed input and method

| Field | Value |
|---|---|
| Machine | Pod: NVIDIA GeForce RTX 3090, 24,576 MiB |
| Source | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Source metadata | 2,931,985,407 bytes; 1920x1080; 174,430 frames |
| Decoded source frame | 474 (0-based) |
| Route crop | `TOPCUT=60`, producing a 1920x1020 detector frame |
| Route-default detector backend selected | `yolov8n.pt` |
| Raw invocation retained | `classes=[0]`, `conf=0.22`, `imgsz=640`, `verbose=False`, `device=0` |
| Tensor columns | `[x1, y1, x2, y2, confidence, class]`, `float32` |
| Fresh-process definition | Each run was a distinct pod `python3 -` process launched through a separate SSH invocation. The additive harness was passed through standard input only; no repository file was copied to or deployed on the pod. |

The harness loads the route's `yolov8n` selection helper, applies only the
condition's named global controls before model load, performs the route's zero
image warmup, then makes the raw detector call above. It imports production code
but does not modify it.

## Four-condition result

Every condition has three fresh processes. Exactness includes tensor shape,
coordinates, confidence, and class. Deltas compare each run with run 1 in its
condition; all shapes were `[15, 6]`.

| Condition | `cudnn.benchmark` | Seeds | Half | Exact across runs | Largest coordinate abs delta | Largest confidence abs delta | Run tensor SHA-256 |
|---|---:|---:|---:|---|---:|---:|---|
| A baseline | true | no | true | no | 0.75 | 0.00146484375 | `4964dfea`, `97b41162`, `c856fe52` |
| B tuner off | false | no | true | yes | 0.0 | 0.0 | `24df8482`, `24df8482`, `24df8482` |
| C tuner off + seeded | false | yes | true | yes | 0.0 | 0.0 | `24df8482`, `24df8482`, `24df8482` |
| D tuner off + seeded + FP32 | false | yes | false | yes | 0.0 | 0.0 | `8d44bb74`, `8d44bb74`, `8d44bb74` |

The maximum baseline coordinate difference is 0.75 px and the maximum baseline
confidence difference is 0.00146484375. All conditions retained 15 boxes, so
the result would have been missed by a box-count-only comparison.

## Per-run full tensor records

[`g190_determinism_cause_records.json`](g190_determinism_cause_records.json)
is the machine-readable part of this evidence artifact. It holds every one of
the twelve runs as a separate object with its complete `[15, 6]` box tensor,
condition values, and SHA-256 of the tensor's float32 bytes. Repeated tensors
are deliberately repeated in the per-run records rather than replaced by a
shared reference. The result table above is recomputable from that file without
rerunning the detector.

The pod recomputation parsed the 12-record artifact, re-derived each tensor byte
hash, and invoked `condition_comparison`:

```text
A {"identical_across_runs": false, "largest_aligned_confidence_abs_delta": 0.00146484375, "largest_aligned_coordinate_abs_delta": 0.75, "reference_run": 1, "run_count": 3, "shape_mismatch": false}
B {"identical_across_runs": true, "largest_aligned_confidence_abs_delta": 0.0, "largest_aligned_coordinate_abs_delta": 0.0, "reference_run": 1, "run_count": 3, "shape_mismatch": false}
C {"identical_across_runs": true, "largest_aligned_confidence_abs_delta": 0.0, "largest_aligned_coordinate_abs_delta": 0.0, "reference_run": 1, "run_count": 3, "shape_mismatch": false}
D {"identical_across_runs": true, "largest_aligned_confidence_abs_delta": 0.0, "largest_aligned_coordinate_abs_delta": 0.0, "reference_run": 1, "run_count": 3, "shape_mismatch": false}
12 tensor hashes validate
```

## What the controls establish

- The tuner is the only named cause isolated as necessary here: A varies, and
  B changes only `cudnn.benchmark` from A while becoming bit-exact.
- Missing seeds are not required to explain this observation: B and C have the
  same bit-exact tensor, and B intentionally has no seeds.
- FP16 is not required to remove this observation: B retains FP16 and is
  bit-exact. D shows FP32 can also be stable after the tuner is off, but this
  design does not test FP32 while the tuner remains on, so it does not assign an
  independent causal effect to FP16.

## Focused test

The per-file test is
`scripts/platformkit/tracking/test_g190_determinism_cause.py`. It was run on the
pod from standard input alongside the harness, without writing either repository
file to the pod:

```text
2 passed
```

## VERIFIER_CONTRACT self-check

- **B1 CIRCULAR METRIC:** Clear. All tensors from every retained process are
  compared; no boxes, rows, or processes were excluded.
- **B2 NON-ADDITIVE SCHEMA:** Clear. The only additions are a standalone
  diagnostic harness, its test, and evidence artifacts; no schema or reader
  changed.
- **B3 FALL-THROUGH LOSS / B4 RE-CLAIM LOOP:** Clear. No gate, queue, claim,
  retry, or stateful route behavior changed.
- **B5 PRE-VERIFICATION DEPLOY:** Clear. No repository file was copied or
  deployed to the pod. The harness and focused test were executed only through
  standard input, and the pod daemon and keeper were not restarted.
- **B6 ORPHANS:** Clear. No module was moved or retired.
- **B7 HEAD-SLICE EVIDENCE:** Clear. This is a fixed numerical reproduction at
  G189's mandated diagnostic frame, not a quality sample.
- **B8 SELF-FIT AS INDEPENDENT / B9 DEGENERATE DENOMINATOR:** Clear. There is
  no fitted model or quality denominator; this is an existence comparison of
  all 12 explicitly enumerated detector tensors.
- **B10 MOVED BAR:** Clear. The four specified conditions and every detector
  invocation value were retained exactly. No pass bar exists.
- **Q1-Q6 / Q9:** Not applicable: this is not an OOS, calibration, or scored
  comparison and does not make an AHEAD claim. No ledger or preregistration is
  required for this construct diagnosis.
- **Q7:** Reproduction replaces eye check. `n=3` is the explicitly required
  fresh-process construct for each condition, and the JSON enumerates all 12.
- **Q8:** Reconfirmed before work: all source-code premises, G189's three
  differing 15-box calls, and the exact pod video metadata held.

## NOT VERIFIED

- Whole-route determinism after a human applies the proposed mode. This row
  isolates one detector call and intentionally does not run the tracker.
- Whether any other frame, video, GPU, driver, CUDA/cuDNN version, detector
  backend, or batch shape has the same sufficient control.
- FP16's independent behavior while `cudnn.benchmark=True`; this experiment
  proves only that FP16 need not be disabled when B is used.
- Throughput impact of disabling the tuner, tracking quality, player coverage,
  identities, coordinate accuracy, or any daemon/keeper outcome.

## Evidence-path check (A7)

At commit time this memo, its per-run tensor artifact, the harness, its focused
test, and the cited verifier contract exist in this worktree.

## Orchestrator verification at landing

**A1:** `test_g190_determinism_cause.py` 2 passed in master.

**A2, recomputed independently from `g190_determinism_cause_records.json` by
canonical-JSON hashing of each `box_tensor`, NOT by trusting the lane's own
`tensor_sha256`:** all 12 runs carry 15 boxes. Condition A yields **three distinct
tensors**; B, C and D each yield **one**. Two cross-checks the memo implies but
does not state outright, both confirmed here:

- **B and C are byte-identical to each other**, so seeding adds literally nothing
  once the tuner is off.
- **D differs from B**, so FP32 is not a free choice: it changes the values, i.e.
  it changes the system under measurement. It must not be adopted casually as a
  "safer" mode.

**Consequence, and it makes the human-gated change SMALLER.** The proposal in
`PROPOSED_determinism_mode_2026-09-03.md` bundled tuner-off, seeding and an FP32
option. Measured: **only `cudnn.benchmark = False` is required.** The proposal is
simplified accordingly -- one flag, one line, no seeding block, no precision
change.

**What this does NOT establish, and the lane says so itself:** whole-route
determinism. This is the DETECTOR in isolation on one frame. The tracker is
stateful and G189's 9 pct spread was measured over the full route; whether
tuner-off removes that too is unmeasured and is the next question, not an
inference to draw here.
