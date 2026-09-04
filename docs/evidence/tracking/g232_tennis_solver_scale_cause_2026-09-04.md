# G232 Tennis Solver Role Diagnosis

This diagnostic executes `docs/evidence/tracking/specs/G232_spec.md` and
follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no production
code, threshold, gate, coordinate contract, corpus, daemon, or keeper.

## Scope, machine, and pod guard

S1 machine: the solve ran in an own, one-process Python invocation on the pod
through `config.pod`, because the exact retained source video and its installed
runtime are pod-resident. The local worktree only stores the observation harness
and durable evidence. Nothing was copied to or deployed on the pod.

At `2026-09-04T06:20:37Z`, before frame writing, a 1,048,576-byte
`dd if=/dev/zero ... conv=fsync` probe under
`/workspace/nba-ai-system/data/.g232_dd_probe_20260904` succeeded and was
removed. `du -sm /workspace/nba-ai-system/data` reported 31,839 MiB. The
process census contained only the declared permanent residents, including
`keep_track_daemon.sh`, `track_daemon`, `foundry_runner`, and the service
daemons. No G211b or G226c measurement process was active. They were not waited
on, stopped, restarted, or otherwise touched. G233 was not present as a running
measurement process at this check.

## Source manifest and exact scope

| Historical table | Exact source-video result | Bytes | Resolution | Action |
|---|---|---:|---|---|
| `tennis_01` | No matching source MP4 remains anywhere under `/workspace/nba-ai-system/data`; only `/workspace/nba-ai-system/data/tracking_reports/tennis/tennis_01.json` remains. | N/A | Historical report: 1920x1080 | Dropped; no substitute used. |
| `tennis_02` | `/workspace/nba-ai-system/data/footage_corpus/tennis__tennis_02.mp4` | 4,131,436,578 | 1920x1080, 60000/1001 fps, 8,101.693600 s, 485,616 frames | Replayed. |
| `tennis_ref01` | No matching source MP4 remains anywhere under `/workspace/nba-ai-system/data`; only `/workspace/nba-ai-system/data/tracking_reports/tennis/tennis_ref01.json` remains. | N/A | Historical report: 640x360 | Dropped; no substitute used. |

The retained `tennis_02` CSV used to select the source-frame range is
`C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g219b_inputs\tennis_02_tracking_data.csv`
(255,168 bytes; tabular data, so raster resolution is not applicable). Its
emitted source-frame range is 342 through 179,664. I chose five evenly spaced
positions over that whole historical emission range: 342, 45,173, 90,003,
134,834, and 179,664. Each was obtained by a separate
`ffmpeg -ss <seconds> -frames:v 1` seek, never by a full decode. The five
temporary PNGs totalled 7,899,375 bytes.

The pod code identity exercised was:

| File | SHA-256 |
|---|---|
| `/workspace/nba-ai-system/domains/tennis/tracking/court_lines.py` | `799c1bf247f76d0579f78278b3f413f8f32791b158fb359e8db935909bd0c19b` |
| `/workspace/nba-ai-system/domains/tennis/tracking/adapter.py` | `c7314449ddccc9f27868ea5a20dbbe8458c96d9a4678b9597dc4b585708fcc58` |

## Unchanged solver observation

`scripts/platformkit/tracking/g232_tennis_solver_role_diagnosis.py` imports the
unchanged `court_lines` implementation. It calls `detect_court` directly and,
separately, records its existing Hough segments, clusters, `_match` evidence,
roles, corners, and homography without monkeypatching or editing
`domains/tennis/`. The complete detected line set for every contrast and frame
is in
`g232_tennis_solver_scale_cause_2026-09-04/g232_solver_observation.json`
(699,745 bytes, SHA-256
`c655f8e2dfbe984be0cf9ccd692803ac3527a136f76138e23fd681d761a7e0a5`).

| Seek frame | Solver result | Accepted contrast | Segment counts (horizontal / vertical) | Role result |
|---:|---|---:|---:|---|
| 342 | accepted | 45 | 487 / 37 of 525 | expected full role set |
| 45,173 | `far_right_consistency` | none | 476 / 32 of 509 at contrast 45 | line roles selected, but fifth-corner check rejected the solve |
| 90,003 | `insufficient_oriented_lines` | none | 104 / 0 at contrast 45; 87 / 0 at 60 | no vertical role assignment |
| 134,834 | `vertical_cluster_count` | none | 145 / 8 at contrast 45; 94 / 2 at 60 | no vertical role assignment |
| 179,664 | accepted | 60 | 389 / 33 of 424 | expected full role set |

For the accepted frame at 342, the selected vertical cluster indices were
`[3, 4, 5, 6, 7]`, with positions `425.9590, 561.7412, 961.3339,
1354.1533, 1486.5854`. They map in image order to `left_doubles`,
`left_singles`, `centre_service`, `right_singles`, and `right_doubles`.
The selected horizontal candidate indices were `[2, 4, 9, 10]`, mapping to
`far`, `far_service`, `near_service`, and `near`. Its observed four-line cross
ratio was 1.10709988 against the template 1.09890110 (absolute deviation
0.00819878, inside the unchanged 0.05 tolerance).

For accepted frame 179,664, the selected vertical cluster indices were
`[1, 2, 3, 4, 5]`, with positions `426.7896, 561.7837, 959.0000,
1354.3311, 1486.8530`, in the same expected role order. Its selected horizontal
candidate indices were `[1, 3, 8, 10]`, mapping to the same four roles. The
observed cross ratio was 1.11029391 against 1.09890110 (deviation 0.01139282,
inside tolerance). The complete role-to-fitted-line mapping, all rejected
template evidence, and every raw segment are retained in the JSON rather than
summarized from a head slice.

The frame at 45,173 independently chose that same expected vertical order and
the same four horizontal roles at both contrasts, but `solve_corners` rejected
it at `far_right_consistency`. This is a rejection, not a successful geometry
claim.

## Homographies and court extent

The accepted 342-frame image-to-feet homography was:

```text
[[ 0.0003715193, -0.6309730606, 460.5449025743],
 [ 0.3399119522,  0.3072489099,-310.7029155584],
 [-0.0000660037,  0.0169354620,   1.0000000000]]
```

The accepted 179,664-frame homography was:

```text
[[ 0.0011040816, -0.7147103399, 521.0083639973],
 [ 0.3868106822,  0.3495470987,-353.8420607574],
 [-0.0001277327,  0.0195731757,   1.0000000000]]
```

For each, the four returned image corners project to `(0,0)`, `(0,36)`,
`(78,0)`, and `(78,36)` feet, so the reported extent is 78.000000 by 36.000000
feet. This result is algebraically pinned by
`TennisAdapter.homography_from_corners`: it fits precisely those four source
corners to the fixed 78 by 36 model. It therefore cannot independently expose
a 123 by 67 foot extent; reporting any such number from those same four fitted
points would be circular. The retained historical out-of-bounds range is not
reproduced by these fresh accepted solves.

## Eye check and finding

The two successful overlays were reviewed:

- `g232_tennis_solver_scale_cause_2026-09-04/renders/tennis_02_f000342.jpg`
- `g232_tennis_solver_scale_cause_2026-09-04/renders/tennis_02_f179664.jpg`

In both, the projected outer court lands on the painted doubles sidelines and
baselines, while the centre and service-line roles land on their corresponding
painted lines. The infinite fitted-line drawings continue beyond the painted
segments into the surrounding image, as expected for line fits; their court
intersections, which define the overlay, land on the court. These are
single-labeller eye judgements, not ground truth.

There is no good-versus-bad role comparison because the specified good
`tennis_ref01` source is gone, and `tennis_01` is gone too. On the only retained
bad source, however, the two fresh accepted solves show the expected role order,
and their court overlays look correct. Thus G232 does **not** establish a role
permutation as the historical cause. More importantly, the fresh single-frame
solves do not reproduce the historical bad-table signature. Per the spec, that
mismatch is the finding; it is not adjusted away or explained as a new defect.

## Artifact cleanup, limits, and verification

After SHA-256 comparison of the local copies with the pod outputs, the exact
temporary directory `/tmp/g232_tennis_solver_20260904` was deleted. It freed
9,420,505 bytes. No corpus source was deleted. The copied evidence directory is
1,521,130 bytes: the JSON plus five 1280-pixel-wide JPEG renders. The three
rejected-frame renders are retained to show their solver gates; only the two
accepted frames carry a projected court model.

Focused test:

```text
python -m pytest scripts/platformkit/tracking/test_g232_tennis_solver_role_diagnosis.py -q
1 passed in 1.36s
```

Contract self-check: B1 has no scored or exclusion-derived metric; all five
preselected seeks, including rejections, are named. B2-B4 change no schema,
status, gate, or claim lifecycle. B5 made no pod deployment. B6 moves no
module. B7 records evenly spaced positions across the whole retained historical
emission range, not a head slice. B8 does not treat corner-fit round trips as
independent geometry evidence. B9 uses source frames and solver observations,
not recycled identifiers. B10 changes no bar or threshold. B11 is respected:
this is a one-run observation on a non-deterministic route, not a system-level
repeatability claim. A7 evidence paths named here exist before commit. A12 does
not apply: the new 208-line harness does not grow an allowlisted file.

NOT VERIFIED: whether the absent `tennis_01` and `tennis_ref01` source videos
can be recovered elsewhere; a cross-clip good-versus-bad role comparison; route
repeatability; historical route-file identity for the retained tables; player
position accuracy; and a population-level rate from one retained clip. The five
eliminations named in G232 remain accepted premises and were not re-derived.
