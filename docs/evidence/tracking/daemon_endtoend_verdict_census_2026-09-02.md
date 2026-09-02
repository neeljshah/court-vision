# End-to-end daemon verdict census: 148 tracked runs, 8 sports, ZERO passes

Date: 2026-09-02. Read-only census of `/workspace/track_daemon.log` on the pod,
taken after the pod was reallocated and the daemon restarted on deployed master.
No threshold moved, no gate touched, nothing re-tracked for this row.

**Headline: 148 tracked runs across 8 sports, `passed=True` count = 0.** This
reproduces the public claim in `docs/TRACKING.md` ("0 harness passes stand across
all sports") on the current daemon rather than on recollection, and it names the
binding failure per sport.

## 1. Per-sport tally

| sport | tracked runs | passed | dominant failure |
|---|---:|---:|---|
| football | 37 | 0 | coordinate contract (image_px) |
| kbo | 29 | 0 | coordinate contract (image_px) |
| mlb | 26 | 0 | coordinate contract (image_px) |
| soccer | 26 | 0 | coordinate contract (image_px) |
| npb | 14 | 0 | coordinate contract (image_px) |
| tennis | 9 | 0 | **quality gates, not the contract** |
| wnba | 4 | 0 | coordinate contract (NBA production image pixels) |
| ncaa_basketball | 3 | 0 | coordinate contract (NBA production image pixels) |
| **total** | **148** | **0** | |

## 2. This answers research row B5 (why the G12 keeps fail `coordinate_contract`)

Four distinct contract reason strings exist in the whole log, and they are all
the same finding:

```
coordinate_contract: rows declare coordinate_space image_px not accepted for sport baseball
coordinate_contract: rows declare coordinate_space image_px not accepted for sport football
coordinate_contract: rows declare coordinate_space image_px not accepted for sport soccer
coordinate_contract: NBA production tracking uses image pixels in x_position/y_position
```

**The G12 keeps do not fail for a G12-specific reason.** Every non-tennis sport
fails identically, because each one emits `image_px` and the contract refuses to
score `image_px` rows. That is the contract working exactly as designed: the rung
ladder says `image_px` rows never pass `court_feet`, and a preserved detection
corpus is never a scorable game. It is fail-closed behaviour, not a defect, and
it needs no fix. B5 is answered and closes without work.

The corollary is worth stating plainly: for five of the eight sports, a
`passed=True` is unreachable by construction at their current rung, so their
zero is not evidence about tracking quality at all. Only tennis is currently
producing coordinates the harness will even score.

## 3. Tennis is the one sport that gets scored, and it fails on quality

Tennis emits `court_feet`, so the contract admits it and the real gates apply.
All 9 runs (8 distinct clips; `tennis_09` appears twice at different lengths):

| clip | rows | coverage (bar 0.90) | oob (bar 0.08) | jump_p95 (bar 8.00) |
|---|---:|---:|---:|---:|
| tennis_01 | 9,547 | 0.67 | - | - |
| tennis_02 | 2,421 | 0.15 | - | 22.13 |
| tennis_03 | 5,610 | 0.44 | - | 34.36 |
| tennis_04 | 7,492 | 0.60 | - | 10.03 |
| tennis_05 | 4,303 | 0.33 | - | 36.79 |
| tennis_07 | 1,356 | - | 0.23 | 31.31 |
| tennis_08 | 4,595 | - | 0.09 | 36.53 |
| tennis_09 | 4,303 | 0.64 | 0.59 | 1583.88 |
| tennis_09 | 578 | - | 0.61 | 171.17 |

Failure mode frequency: **jump_p95 8 of 9**, **coverage 6 of 9**, **oob 4 of 9**.

## 4. The finding that matters: PASS on ranges is not PASS on clips

The program's tennis result is real but narrower than the register makes it
sound. G05/G18 established harness PASS on **selected 300-frame sequential
ranges** at 0.897 coverage. This census says that **no tennis clip passes
end-to-end through the production daemon**, and whole-clip coverage is 0.15 to
0.67 against the same frozen 0.90 bar.

Both numbers are correct and they are not in conflict. The sequential ranges are
rally segments; a whole clip includes changeovers, replays, close-ups and crowd
shots, which the camera lock cannot solve by construction. **The gap between
0.897 and 0.15-0.67 is the non-rally share** -- which is exactly the quantity
row G34 was opened to measure, and this census is the strongest argument yet
that G34 is on the critical path rather than a nicety.

Two of the three failure modes already have owners: `oob` is G26 (courtside
non-players selected as the per-half player), and `coverage` is the G34
denominator question. **`jump_p95` has no owner** -- it fires on 8 of 9 runs,
reaching 1583.88 against a bar of 8.00, and nothing in the register explains it.
That is new, and it is allocated below as **G38**.

## 5. Pod ops recorded with this row

The pod was reallocated (new SSH port; the host key changed and the old port
refused connections). What persisted on `/workspace`: the repo, the corpus at 63
clips, `data/models` including both G31 fold checkpoints. What was lost: `/tmp`
in full, and every running process except the MLB book capture.

Restored today: 7 landed tracking modules deployed by `git archive` and verified
md5-identical CRLF-normalised (`track_daemon.py`, `track_daemon_sources.py`,
`tracking/source_timebase.py`, `tracking/tennis_sequential_plan.py`,
`tracking/ledger_hook.py`, `tracking/worktree_data_links.py`,
`soccer_s1_stream_packet.py` -- the last being the G08 deploy that harness row
S21 flagged as outstanding); the keeper and daemon restarted (daemon pid 4035).

**The Python environment did not survive and had to be rebuilt**: `pandas`,
`scipy`, `opencv-python-headless` and `ultralytics` were all absent and were
reinstalled with `--break-system-packages` (PEP 668 blocks a plain install on
this image). The versions that landed are **newer major releases than the code
was written against -- pandas 3.0.5 and cv2 5.0.0**. `test_track_daemon.py`
passes 28/28 on the pod against them, which is reassuring but is not a full
compatibility audit.

## NOT VERIFIED

- The census reads the daemon log, not the per-game manifests. Runs whose log
  line was truncated or rotated away are not counted, so 148 is a floor.
- pandas 3 and cv2 5 compatibility is evidenced by one test file (28 tests) and
  by the daemon continuing to track. No systematic audit was run, and a silent
  behavioural change in either library would not be caught by that test.
- `jump_p95` is reported, not diagnosed. Nothing here establishes whether it is
  an identity-swap artifact, a units problem, or genuine tracking instability.
- No clip was re-tracked for this row, so every number is from runs produced by
  whatever code was deployed when that run happened, which is not uniform across
  the 148.
- The tennis clips in this census (`tennis_01` to `tennis_09`) are not the same
  set as the G18 sequential-range matches (`nyYk`, `tennis_09`, `tennis_10`);
  only `tennis_09` is in both.
