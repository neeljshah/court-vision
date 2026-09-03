# G188 player-selection defect: Q8 premise falsified

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), especially Q8 and
section B. This is diagnosis only. No production source, selection rule,
detector setting, coordinate contract, gate, threshold, daemon, or keeper was
changed.

## Result: STOPPED before the requested two-sport delta

Q8 requires reproducing G187 frames 474 and 1377 before any broader
measurement, and requires stopping if the box set differs from the committed
renders. That prerequisite is not reproducible in this worktree.

The G187 memo names `data/footage_corpus/wnba__wnba_01.mp4`, describes a
2,931,985,407-byte source, and its committed renders are 1920x1080. The source
available to this worktree is instead the retained
`data/footage_corpus/g130_recensus/wnba__wnba_01.mp4`, decoded at 1280x720;
the direct source named by G187 is absent here (also recorded in G181). It is
therefore not a coordinate-identical input.

As a second, semantic check, the existing basketball survivor path was invoked
read-only on derivative frame 474 after its normal `TOPCUT=60` crop. Its fresh
`AdvancedFeetDetector` call retained six on-court player boxes. The committed
G187 frame-474 render has three survivor boxes, including a foreground
spectator and sideline/bench figures. These are different survivor box sets.

This falsifies the premise for this worktree; it does **not** establish that
the committed G187 run itself was wrong. A bounded full-pipeline reproduction
was also attempted against the derivative, but its own preflight stalled before
writing a CSV and was stopped as the isolated measurement process. The daemon
and keeper were not queried, stopped, restarted, or deployed.

## Q8 observations (not the requested 20-frame metric)

The raw stage used `scripts.platformkit.detection.shim.get_detector` with its
default `CV_DETECTOR=ultralytics` backend and `yolov8n.pt`; only detections
whose class name was `person` are listed. These are diagnostic observations on
the different derivative, not comparable per-frame raw-versus-survivor evidence
for G187.

| Source frame | Available-input size | Shim raw person count | Fresh local survivor count | Comparison with committed G187 survivor set |
|---:|---:|---:|---:|---|
| 474 | 1280x720 | 11 | 6 | DIFFERENT: local survivors are on-court players; committed render has 3 non-court survivors. |
| 1377 | 1280x720 | 14 | not run after the frame-474 STOP condition | Not attempted as a survivor reproduction. |

The frame-474 raw boxes (crop-relative image pixels) retained by the shim were:

```text
(182.3,460.2,289.4,650.8,0.850) (264.3,335.0,329.0,503.1,0.720)
(513.7,386.2,577.3,553.5,0.719) (581.9,205.4,639.3,319.7,0.645)
(49.1,233.0,121.4,364.7,0.625) (383.3,330.7,471.3,485.7,0.609)
(843.2,235.6,1027.1,472.5,0.570) (347.1,330.0,471.5,488.3,0.544)
(723.6,475.4,798.0,586.3,0.483) (1113.5,576.6,1205.4,648.0,0.464)
(1236.9,601.3,1279.6,649.5,0.268)
```

No human on-court counts, dual-colour renders, 20-frame table, or tennis
sample are presented: producing them after the required Q8 STOP would falsely
suggest they were a valid measurement of the G187 selection defect.

## Cause verdict

**Cannot separate on valid evidence in this worktree.** The requested evidence
cannot determine whether G187's detector missed players or its selection logic
discarded them, because its input/output premise did not reproduce. No fix is
proposed.

## Focused harness test

The additive evidence helper is
`scripts/platformkit/tracking/g188_player_selection_defect.py`. It implements
inclusive even-frame selection, shim person-box retention, and distinct raw
(red) and survivor (green) drawing without mutating either collection.

```text
python -m pytest scripts/platformkit/tracking/test_g188_player_selection_defect.py -q
2 passed in 2.19s
```

## VERIFIER_CONTRACT self-check

- **A2/Q8:** Re-measured the named prerequisite before broader scoring. It
  failed: no same-resolution named G187 source exists locally and the first
  survivor box set differs. The investigation stopped.
- **A3/B7:** No sampled headline or render claim is made. The required 20-frame
  sequence was deliberately not started after Q8 failed, so this is not a
  head-slice measurement disguised as an even sample.
- **A4/B9:** No aggregate metric is claimed; the requested eligible denominator
  was never constructed on a reproducible input.
- **A5/B2/B6:** The only code addition is an additive, uncalled evidence helper
  and its focused test. No production schema, reader, module, or import changed.
- **B1:** Clear. No exclusions or rate/recall/precision calculation is claimed.
- **B3/B4:** Clear. No gate, claim, queue, or fallback behaviour changed.
- **B5:** Clear. No repository file was deployed to the pod.
- **B8:** Clear. No fit or residual is claimed.
- **B10:** Clear. No threshold, constant, backend default, coordinate contract,
  bar, or production verdict changed.

## NOT VERIFIED

- The requested 20-frame evenly spaced raw-versus-survivor records for WNBA.
- The five WNBA dual-colour renders and per-frame human on-court counts.
- Any tennis clip, tennis dual-colour renders, or cross-sport comparison.
- Whether G187's original detector found on-court players, selection discarded
  them, or both; this worktree cannot distinguish the causes on valid evidence.
- Full-pipeline behavior on the local derivative: its isolated rerun stalled in
  preflight before producing an output table.

## Landing note from the orchestrator

**This lane was terminated by the orchestrator, not by its own logic.** It had
already written this memo and its harness when a peer session's RAM guard fired
twice on its local jobs (pid 20136 at 95 pct box RAM, pid 22592 at 96 pct), and
the local box is 16 GB with other lanes live on it. I stopped it to protect the
concurrent work. **The Q8 STOP recorded above is the lane's own correct
judgement and predates the termination** -- it is not an artefact of being killed.

The cause was my spec: G188 said not to wait on the pod daemon but never said
where to RUN. Its sibling G187, written an hour earlier, did mandate the pod.
Spec corrected at 70c3bff1a.

Verified at landing: `test_g188_player_selection_defect.py` 2 passed in master.

**The frame-474 observation is kept because it materially qualifies G187**, and
is carried into that memo as a correction. It is NOT evidence that G187's run was
wrong, exactly as this memo says.
