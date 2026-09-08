VERDICT DONE -- premise HOLDS: 24 of n=259 committed evidence artifact directories carry any environment record and only 6 of n=259 carry both a python and a numpy version; the additive sidecar, three hooked runners with an opt-out, and the local and pod captures are landed.

Prereg `docs/evidence/tracking/g62_prereg_2026-09-08.md`, SEAL sha256 1e9e4e25c68a30fb68e24e4712416480d053394989b9dee7922ab3806a7a52f2, committed alone at 1095cda5a before the first census cell existed. Scope, reading and detection rules are its section 1 and were not re-decided. EYE CHECK: NONE -- this is a schema and capture row with no rendered decision; reproduction is the printed stamp below.

## Premise census (exhaustive; `census.csv`, 261 lines = header + 259 directory rows + 1 loose-file row)

| class | n | with any environment record | with python AND numpy |
|---|---|---|---|
| artifact directories, both roots | 000259 | 000024 | 000006 |
| ... under docs/evidence/tracking | 000244 | 000023 | 000005 |
| ... under docs/evidence/harness | 000015 | 000001 | 000001 |
| loose files sitting directly in the two roots (own class, not a directory) | 001401 | one class, has a record | n/a |

The stop condition was "more than half carry both": 6 of 259 is 2.3 per cent, so the premise HOLDS. The row's own allocation artifact, `tennis_player_select_limit_2026-09-04/`, is census row 256 and carries none. Prior art the census found: `g58_renders/` and `g64_segment_bisect/` already record `python_version`, `numpy_version`, `torch_version`, `cv2_version`, `platform` and `hostname` -- two one-off dicts, not a shared helper, which is exactly the hole this row closes. Reconciliation of a pre-seal count: 250 directories hold a tracked file directly at depth four; 9 more hold tracked files only deeper (g194_which_M1_2026-09-03, g213_footage_visual_census_2026-09-03, g220c_amateur_footage_working_rung_2026-09-04_frames, g222_direct_to_seed_propagation_artifact, g233c_seed_gate_artifact, g241_seed_horizon_to_failure_artifact, g241b_seed_horizon_to_failure_artifact, g266_multiframe_constraint_accumulation_artifact, soccer_stream_packet_2026-09-02); 250 + 9 = 259. Re-run after the two captures landed, the census reproduces byte-identical (sha256 c28fbe55...) because the prereg excludes this row's own output directory by name.

## The sidecar, its hooks and what was skipped

`scripts/platformkit/env_sidecar.py` (150 lines): `capture()`, `write()`, `read()`. Fourteen top-level keys, `sort_keys=True`, ASCII, no environment variable read beyond `OMP_NUM_THREADS` and `MKL_NUM_THREADS`, no secret or token. `capture()` never raises: an unimportable library, an unreadable git revision or cgroup file and a missing named module each become an explicit null carrying its reason (the pod capture below is that path firing for real). Module hashes name only the files that fix each artifact, following the G52 driver -- the repo is never hashed whole; library identity is already carried by `libraries`, and model weights are data, not modules.

HOOKED (3, each additive, each with `--no-env-sidecar` that restores master's bytes exactly): `scripts/platformkit/tracking/census_recomputable.py` (193 -> 205 lines), `.../g330_run_attempt2.py` (240 -> 250), `.../g310_instance_key.py` (202 -> 211). The diff is 31 inserted lines and 0 deleted, so under B2 no key is renamed or removed and every reader of those outputs parses them unchanged; the sidecar is a NEW file with a new name.
SKIPPED: 24 candidates, every one named, none picked by the prereg's selection rule (it lacks an existing per-file test, or has under 40 lines of headroom under the 300-line rail, or is not among the three most recently committed that pass both clauses) -- footage_census, g214_learned_corner_probe_pod, g220_amateur_footage, g220c_amateur_footage, g247_projected_quad_validity, g248_projected_line_image_agreement, g252_projection_accuracy_in_pixels, g254_projection_refinement_and_basin, g255_amateur_gate_independent_check, g257_eye_gate_discrimination, g258_synthetic_truth_validity, g260_paired_displacement_sensitivity, g290_footpoint_offset_axis_decomposition, g294_gap_conditioned_implausibility, g296a_extract_frames, g296b_located_players, g302_source_identity, g304_proposals, g312_readjudicate_coverage, g321_semantic_gate, g327_detector_batch_stability, g331_evaluated_frames_sidecar, tennis_calib_eval, test_g242_seed_reacquisition_whole_game. The two nearest misses are g327_detector_batch_stability.py (275 lines) and g331_evaluated_frames_sidecar.py (291), both excluded by the headroom clause. Every other file in `scripts/platformkit/tracking/` writes no artifact directory and was never a candidate. `~/bin/pod_run` is OUTSIDE the repo and was NOT edited -- the one-line call the orchestrator may add at the top of a job, after the output directory exists, is `python3 -c "import sys;sys.path.insert(0,REPO);from scripts.platformkit.env_sidecar import write;write(OUTDIR)"`. `lane_commit.py` does not exist in this repo (`git ls-files` returns nothing for it) and so cannot be hooked. NO landed artifact was given a sidecar retroactively, and none should ever be: an invented stamp would be worse than the gap.

## Printed example stamp (the pod capture, verbatim machine output)

`{"captured_utc": "2026-09-08T13:05:32Z", "cgroup_cpu_quota": "/sys/fs/cgroup/cpu/cpu.cfs_quota_us=2720000", "cpu_count": 256, "git": {"dirty": null, "head_sha": null, "unavailable_reason": "git rev-parse exit 128: fatal: not a git repository (or any of the parent directories): .git"}, "host": {"hostname": "771c926940a2", "role": "pod", "role_rule": "role is 'pod' when /workspace/nba-ai-system exists, else 'local'"}, "libraries": {"cv2": "4.14.0", "numpy": "2.1.2", "pandas": "2.3.3", "scipy": "1.18.1", "sklearn": "1.9.0", "torch": "2.8.0+cu128", "ultralytics": "8.4.143"}, "modules": [], "platform": "Linux-6.8.0-110-generic-x86_64-with-glibc2.39", "python_version": "3.12.3", "schema": "g62_environment_sidecar_v1", "seed": null, "seed_reason": "no seeded randomness on this route", "threads": {"MKL_NUM_THREADS": null, "OMP_NUM_THREADS": null, "torch_num_threads": 128}, "torch_build": {"cuda_available": true, "cuda_version": "12.8", "cudnn_version": 91002, "unavailable_reason": null}}`

## Pod versus local: every key that differs (n=20 differing of 29 leaf keys)

| key | local | pod |
|---|---|---|
| captured_utc | 2026-09-08T13:05:26Z | 2026-09-08T13:05:32Z |
| cgroup_cpu_quota | null | /sys/fs/cgroup/cpu/cpu.cfs_quota_us=2720000 |
| cpu_count | 12 | 256 |
| git.head_sha / git.dirty / git.unavailable_reason | 1095cda5ac4c88969bb65489abda4b4066bcc665 / true / null | null / null / git rev-parse exit 128: fatal: not a git repository ... |
| host.hostname / host.role | DESKTOP-VUIITL8 / local | 771c926940a2 / pod |
| libraries.cv2 / numpy / pandas / scipy / sklearn / torch / ultralytics | 4.11.0 / 2.2.6 / 2.2.3 / 1.15.1 / 1.6.1 / 2.2.0+cu121 / 8.3.64 | 4.14.0 / 2.1.2 / 2.3.3 / 1.18.1 / 1.9.0 / 2.8.0+cu128 / 8.4.143 |
| platform | Windows-10-10.0.26200-SP0 | Linux-6.8.0-110-generic-x86_64-with-glibc2.39 |
| python_version | 3.10.0 | 3.12.3 |
| threads.torch_num_threads | 6 | 128 |
| torch_build.cuda_version / torch_build.cudnn_version | 12.1 / 8801 | 12.8 / 91002 |

Identical on both (9 leaf keys): `modules` (empty on both), `schema`, `seed`, `seed_reason`, `threads.MKL_NUM_THREADS`, `threads.OMP_NUM_THREADS`, `torch_build.cuda_available`, `torch_build.unavailable_reason`, `host.role_rule`.

S287 CANDIDATE KEYS, CANDIDATES ONLY -- naming a differing key is not a demonstration that it caused anything, and this row runs no simulator and re-scores nothing: `libraries.numpy` (2.2.6 against 2.1.2), `libraries.torch` (2.2.0+cu121 against 2.8.0+cu128), `threads.torch_num_threads` (6 against 128), `cpu_count` (12 against 256) and `python_version` (3.10.0 against 3.12.3). A sixth, `libraries.scipy`, is listed because a scipy special function can change between minor versions; it is the weakest of the six.

## NOT VERIFIED

- That any listed candidate key CAUSES the S287 divergence. Nothing was re-run; attribution needs a controlled arm this row does not have.
- That the recorded thread settings are the ones in force LATER in a run. `capture()` reads them before it imports anything, and importing `ultralytics` sets `OMP_NUM_THREADS` to 1 on this box (measured directly: `None` before the import, `'1'` after). A capture taken first therefore records the inherited value, not the post-import one.
- That this local capture is the interpreter S287 used. It is python 3.10.0 with numpy 2.2.6 and torch 2.2.0+cu121, whereas S287's memo describes a local box at python 3.10.20, torch 2.1.2+cu121 and numpy 1.26.4. This box has more than one interpreter, and no committed artifact ever said which one ran -- which is the gap, arriving in this row's own evidence.
- The three hooks are proven additive by test and by inspection, not by a full production run of any hooked runner; no route, no video, no GPU and no pod job ran here.
- cgroup and GPU details are best-effort where readable; a null is a real null. Retroactive attribution for landed rows remains impossible.
- The census counts a memo's PROSE mention of a version as an environment record, which can only OVERSTATE how many directories carry one.

## SHA-256 (LF-normalised) and wall time

census.csv c28fbe550890aa766d04fe8b462eaf6333e22390052e197252483f09b3f7662a | environment_local.json 8ceed0375ffda6f36d10e5febd10a5f9c66c81dcde9d88c5858a1915e9f9aef1 | environment_pod.json 031e9b96547ce1eb4d9776870882ef309b9fa6b30231b64267ff3e8e2f379dd7 | env_sidecar.py 5efd6c4073d6c5f5051bffef6a80fd14c7f535a508b826bcef6847883eeb831b | g62_env_census.py 53ab01d15708a24a6cb1e8fd26812b99012604c28d6525226841ac941d802118 | test_g62_environment_sidecar.py 36782375a7905d47d24a5e21484183e580ee2748d1d04f6b196caa7cc578d868

TESTS, each file run on its own, never a full suite: `test_g62_environment_sidecar.py` 7 passed; `test_g319_census_recomputable.py` 4 passed; `test_g310_instance_key.py` 10 passed; `test_g330_panorama_identity.py` 17 passed; `test_loc_rail_scope.py` 1 passed. Every touched file is at or under 300 lines (`env_sidecar.py` is 150, at the spec's own cap). Nothing under `src/`, `kernel/`, `api/`, `intel/`, `domains/`, `data/` or `data/registry/` was touched; no threshold, bar, register row, landed memo or committed hash moved; `TRACKING_GAPS_2026-09-01.md` was not edited; the pod was read-only (one `python3 -` over ssh, stdout captured locally) and pids 1168432, 1039858 and 1201700 were not signalled. Wall time about 55 minutes.
