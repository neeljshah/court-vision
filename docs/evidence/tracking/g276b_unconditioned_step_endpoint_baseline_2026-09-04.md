# G276b: Unconditioned same-ID step endpoint baseline

## Verdict

**ACCEPT (measurement only): 18 / 60 = 0.300 sampled unconditioned detector-box steps had a NOT A PERSON crop at one or both endpoints.** This directly measures the prior `[0.208, 0.373]` bracket. G272b's jump-conditioned 24 / 48 = 0.500 is `0.500 / 0.300 = 1.667x` this sample baseline. Its 1.667x ratio is a sample point, not a population claim; the respective 95 percent Wilson intervals are 0.199--0.425 and 0.364--0.636.

This asserts no causation in either direction. It does not show that non-person locations cause jumps, that jumps cause non-person locations, or allocate a cause among detection, localisation, association, and projection. The units are retained detector boxes / associated observations, not authenticated players.

## Inputs, location, and exact population match

**Local analysis** read only `docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`, 12,446,681 bytes, SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`. Its inherited source is `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps, frames 19599--23399. Selection, the sealed order, unblinding, and arithmetic ran in this local `track-a5` worktree; no re-detection, reassociation, map fit, or source-data write ran.

**Pod render only** used `~/bin/pod_run a5 --ship ... --fetch ... -- bash scripts/platformkit/tracking/g276b_pod_render.sh` in `/workspace/wt/a5`, because the full-resolution source is there. It did not write `/workspace/nba-ai-system`. The exercised route SHA-256 was `129ebb12e168439c5fc344835aeae69e9ab7170f3da096acf84e7ad3fdf7a7a1`.

The eligible denominator is **23,783 finite consecutive same-emitted-ID detector-box steps with a positive frame gap and both retained footpoints inside the unchanged inclusive 50 x 94 ft court.** This is G272b's structural both-endpoints-on-court population with its strict-over-40-ft/s condition removed. G272b's >83-px restriction is its downstream jump-candidate definition rather than a structural population filter; it was not carried, as G276 explicitly prohibits speed, displacement, jump, or downstream-conditioned sampling. This is the named difference; no other position, ID, speed, displacement, or outcome filter was applied.

The seeded spread draw selected one step in every one of 60 equal-width current-frame bins: 60 steps, 120 endpoint crops, 54 emitted IDs, and current frames 19656--23366. It is not G272b's speed-conditioned 2,507-step denominator and is not a head slice.

## Pooled blind order and categories

Each endpoint is a separate 512x640 native-pixel footpoint-centred crop. It shows the neighbourhood claimed by a retained location, not a detector rectangle; no box was drawn, reconstructed, or inferred. The 120 crop files total 5,478,005 bytes.

Both endpoints of every selected step were pooled then shuffled with selection seed `27620260904` and blind seed `27620904`. The labeller saw only randomized blind index and crop filename in `blind_presentation_order.csv`; it contains no step, endpoint, frame, ID, or pair field, so pairing was hidden. Commit `4672ec052` sealed the pooled order, all crops, and completed verdicts before the withheld map was opened. `blind_order_commitment.json` contains that map's canonical SHA-256 commitment.

| Independent crop category | Count | Fraction of 120 |
|---|---:|---:|
| PLAYER on the court of play | 64 | 0.533 |
| PERSON NOT PLAYER IN PLAY | 22 | 0.183 |
| NOT A PERSON | 34 | 0.283 |
| CANNOT JUDGE | 0 | 0.000 |

This is a coarse categorical eye measurement, not G257's sub-pixel geometric question.

## Unblinded joint result

NOT A PERSON is binary-positive. In the including-CANNOT-JUDGE table, CANNOT JUDGE remains separately enumerated and is in the denominator but is not claimed positive; in the excluding-CANNOT-JUDGE table every step with either such crop is removed. There are zero CANNOT JUDGE crops and zero such steps, hence the results are identical rather than silently merged.

| Prior NOT A PERSON | Current NOT A PERSON | Including CANNOT JUDGE (60) | Excluding CANNOT JUDGE (60) |
|---:|---:|---:|---:|
| 0 | 0 | 42 | 42 |
| 0 | 1 | 1 | 1 |
| 1 | 0 | 1 | 1 |
| 1 | 1 | 16 | 16 |

| Quantity | Including | Excluding |
|---|---:|---:|
| Per-crop NOT A PERSON | 34 / 120 = 0.283 | 34 / 120 = 0.283 |
| One-or-both NOT A PERSON | 18 / 60 = 0.300 | 18 / 60 = 0.300 |
| Endpoint phi correlation | 0.918 | 0.918 |
| Bracket from observed per-crop rate | [0.283, 0.486] | [0.283, 0.486] |
| Observed one-or-both position | 0.017 above lower, 0.186 below upper | same |

The per-crop 0.283 differs from G273's 0.208 in another sample of the same detector draw. That is sampling variation, not a change in the detector. The high correlation is descriptive of this sample only.

## Pod hold, guard, cleanup, and verification

The raw distinct Python-CWD worktree set was `{ /workspace/wt/a17, /workspace/wt/a5 }`. Excluding this row's own `a5` process/checker ancestry gave the peer set `{ /workspace/wt/a17 }`, one peer, so this was the permitted second lane; no process was interrupted.

The pod-side in-command guard, not a local guard, reported `du -sm /workspace` = 38,486 MB before crop writing. The 8,388,608-byte `dd conv=fsync` probe passed and was removed; `df` was not used. The launcher separately observed 38,422 MB before shipping. After fetch, the exact pod scratch crop directory (5,478,005 bytes) and tarball (5,703,680 bytes) were removed: 11,181,685 bytes, or 19,570,293 known temporary bytes including the probe. No corpus source or either bridge `.part` was deleted. The final committed artifact is 5,560,392 bytes.

```text
python -m pytest scripts/platformkit/tracking/test_g276b_unconditioned_step_endpoint_baseline.py -q -p no:cacheprovider
2 passed
```

This follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. A7 evidence paths exist; A9 names input and source bytes/resolution; A11 records the route hash. B1 names and retains the structural population before sampling; B2--B6 change no schema, lifecycle, deployment, production route, or module; B7 spans all bins; B8 uses no fitted residual; B9 names detector-box, ID, step, and crop denominators; B10 moves no bar. Q does not apply. The new 213-line harness and 34-line test do not trigger A12.

## NOT VERIFIED

- Another clip, shot, arena, sport, detector draw, labeller, or population rate beyond this 60-step sample.
- Ground-truth person precision/recall, identity, on-court status, duplicate status, association correctness, or detector-box extent.
- Any causal direction or production filter, gate, threshold, tuning, re-detection, reassociation, or readiness change.
- Eye-label reliability; this programme has not cleared 80 percent blind agreement on four measured criteria.
