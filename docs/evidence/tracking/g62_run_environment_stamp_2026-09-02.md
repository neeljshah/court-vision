# G62 run-environment stamp

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including A7 and
section B. This is an additive provenance row: it records facts beside a new
artifact and does not alter a threshold, metric, verdict, or historical file.

## Step 0: reproduced premise

`docs/evidence/tracking/tennis_player_select_limit_2026-09-04/report.json`
parses with exactly these top-level keys: `bounds`, `matches`. It has no host,
timestamp, library versions, device state, seed, or revision. The different
local outcomes therefore cannot be attributed after the fact to code or to an
execution environment. This historical artifact is deliberately unchanged;
its stamp cannot be reconstructed honestly.

## Change and writer scope

New helper: `scripts/platformkit/tracking/run_environment.py`.

Changed writers:

- `scripts/platformkit/adapter_run.py`: each newly written
  `data/tracking_reports/<sport>/<game_id>.json` now gets `run_environment`.
  The seed is explicitly null with the reason that this entry point has no
  explicit seed configuration. Its source hashes name the entry point, the
  selected sport adapter, `tracking_harness.py`, and `tracking_schema.py`:
  these modules create, normalize, and score that report.
- `scripts/platformkit/tracking/tennis_sequential_plan.py`: each newly written
  `sequential_plan.json` now gets `run_environment`, with seed `20260901`.
  Its hashes name the entry point, tennis adapter, camera lock, court
  diagnostics, court lines, harness, and tracking schema: these modules select
  or process the range and determine the reported result.

Deliberately skipped:

- `scripts/platformkit/tracking_harness.py` is a shared module under active
  work by G50B. It is not edited; it serializes a report but does not own the
  evidence-file write.
- Historical evidence artifacts, including the G26 `report.json`, are not
  retrofitted. No provenance field is invented.
- One-off archived G52 driver output is not retrofitted; it is historical
  measurement evidence, not a current writer.

The helper records UTC timestamp, hostname, platform, Python/cv2/numpy/torch
versions, CUDA availability when torch imports, seed and reason, revision and
dirty state, and SHA-256 hashes. Git failures produce explicit null fields with
reasons; an empty `git status --porcelain` is correctly recorded as clean, not
as a failed revision lookup. It never hashes the whole repository.

## Printed example stamp

Captured locally from the sequential-plan module set:

```json
{"cuda_available": true, "cv2_version": "4.11.0", "git_revision": "4223c5f4c2497148c4f7cb755e3a2552731616c8", "git_revision_reason": null, "git_tree_dirty": true, "git_tree_dirty_reason": null, "hostname": "DESKTOP-VUIITL8", "numpy_version": "1.26.4", "platform": "Windows-10-10.0.26200-SP0", "python_version": "3.10.0", "seed": 20260901, "seed_reason": null, "source_hashes_sha256": {"domains/tennis/tracking/adapter.py": "d17beee681e6fad5fb44deef79bbe65f93e8d56d6a19ff6260ed47c3c3e19cd8", "domains/tennis/tracking/camera_lock.py": "6e4f8951e8dd91fd3c90ab6567c6a2d9003b14e3211b5e3fc0ccc73d4b5b61eb", "domains/tennis/tracking/court_diagnostics.py": "dbb07f027cb58f3d0500598c8b4c1762c52ed9d2a9baca671271b7ae6c26809a", "domains/tennis/tracking/court_lines.py": "0f0f3fa393c8a58320fe352d43ddb673fab515200b7cd8a4dd8fa5ec2f51bbe0", "scripts/platformkit/tracking/tennis_sequential_plan.py": "eff36baf4911e3294ed1f4a0b6fb478753e68e3e31b44ce3c0b96773ce24a6a4", "scripts/platformkit/tracking_harness.py": "7dcd1f3776139633fcf867969886a1655d11c5e5b3fb589a3eb1c669f1840644", "scripts/platformkit/tracking_schema.py": "f3321eecfe105afaf4ffbf4e5153b8d08856bed143d88e378c87ab21137c1dc1"}, "timestamp_utc": "2026-09-02T18:49:15.449740Z", "torch_version": "2.2.0+cu121"}
```

## Verification

Focused test command and result:

```text
python -m pytest scripts/platformkit/tracking/test_run_environment.py -q
1 passed
```

The one test constructs three additive artifacts: torch/CUDA available, torch
unavailable, and dirty tree. It asserts a complete field set and source hash in
each. It also verifies that the existing `tracking_feature_bridge._iter_reports`
reader parses a stampless artifact and that every historical key is unchanged
after stamping a copy. Newly written artifacts from both changed writers carry
a complete stamp: 2/2 writers, 1.0.

## Section B self-check

- B1/B7/B8/B9: no scored or sampled metric was added.
- B2: only a new top-level `run_environment` field is added; the existing
  reader parses an artifact without it.
- B3/B4: no gate or claim path changed.
- B5: no pod action occurred.
- B6: no module moved or retired.
- B10: no threshold or verdict changed.

## NOT VERIFIED

- No pre-existing artifact has a reconstructed stamp.
- No pod artifact was written, copied, or deployed.
- This local example is not a claim about another host's environment.
