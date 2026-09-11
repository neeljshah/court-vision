# G384 preregistration amendment A1 -- whole-queue finisher sample

Date: 2026-09-10. This amendment is additive to sealed `g384_execution_prereg_2026-09-10.md` (seal `db343a7a1e87a052647b79a68d40aaabee48d2824a8edaae8cbf1f1a21f87184`) and is written before the A1 adjudications.

The prior 60 decisions at queue ordinals 1,6,...,296 are retained on disk as a superseded prefix-derived run and are not used for A8 supply inference. The A1 finisher sample is exactly the 60 queue ordinals `k*10+1` for `k=0..59`: 1,11,...,591, evenly spaced over all 596 reconciled keys. The 30 already-adjudicated keys that coincide with this A1 selection are reused unchanged by frame key. The 30 new A1 positions, ordinals 301,311,...,591, are adjudicated blind from their existing 1920x1080 native PC-side sheets under `docs/evidence/tracking/g373_ball_detector_v2_2026-09-10/sheets/` and existing `raters_v2` archives only. A selected key whose native sheet is absent is recorded `MISSING`; no source is re-fetched or re-rendered.

After all 60 A1 positions are accounted for, report each split's yield, Wilson interval, full-queue projection, and the A8 supply conclusion from this even sample. The inherited requirement remains 500 audited development boxes: if the 95 percent projection upper bound reaches 500, A8 is not CLOSED AT LIMIT on supply evidence.
SEAL sha256 93dddcc3bb02be740c91b8beaca8c2c1c6b7fbe5ab2a627474ccf678ac8dc842
