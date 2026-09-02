# G14 pod deploy -- tracking code brought to master, daemon restarted

Lane G14-POD-DEPLOY, 2026-09-01/02. Pod `213.192.2.83:40048`, repo
`/workspace/nba-ai-system`, Python 3.12.3. Local HEAD `89c6da9ce`.
No git command was run on the pod; deploy is `git archive HEAD | tar -x`.
`data/` on the pod was not written. Nothing was killed except the
`keep_track_daemon.sh` watchdog and the daemon it owns; the MLB book capture
(pid 3040635) was checked ALIVE before and after.

## 1. Diff inventory -- how "lags master" was measured

Scope: every tracked file under `scripts/platformkit/tracking/`,
`scripts/platformkit/tracking_*.py`, `scripts/platformkit/track_daemon.py`,
`scripts/platformkit/footage_*.py`, `domains/*/tracking/**`,
`domains/*/adapter*.py`, unioned with the `.py` files touched by the six
commits this lane was given (1c5f1e6b7, beb8e4c6d, 398410393, 452c9d954,
55c90a911, 8f8db7c8d). **148 files.**

Comparison is `git show HEAD:<path> | md5sum` against the pod file. The first
pass reported 141/148 mismatched, which was a **line-ending artifact, not a
lag**: every pod `.py` carries CRLF (`file` reports "with CRLF line
terminators") because earlier deploys scp'd the Windows working tree, whose
`core.autocrlf=true` checkout is CRLF. `.gitattributes` pins only `*.sh` to LF.
The honest comparison strips the carriage returns on the pod side
(`tr -d '\r' < "$f" | md5sum`). That gives the real answer:

**50 of 148 files behind -- 32 absent from the pod entirely, 18 stale.**

## 2. Deployed

One `git archive HEAD -- <50 paths> | ssh 'tar -x -C /workspace/nba-ai-system'`
(419,840-byte tar, 64 entries incl. directories) at **2026-09-02 00:09:05 UTC**
(the mtime of every deployed file). Three more files followed as a dependency
closure (section 2b). All md5s below are of the LF content
(`git show HEAD:<path>`), and every one was re-read from the pod after the
deploy: **50/50 now match, 0 remaining mismatches.**

### 2a-i. Absent from the pod before this deploy (32)

| file | md5 (now on pod) |
|---|---|
| domains/football/tracking/clustering_diagnostic.py | 808cd21a9197849f377918d9905a843b |
| domains/football/tracking/numeral_probe.py | ca723ff7e08e54ad830148621a539513 |
| domains/football/tracking/numeral_registration.py | 27c0b1d276a7d6c83781debd7e0aa2aa |
| domains/football/tracking/scale_probe.py | f318960429b9049d0b8c787737ecf16e |
| domains/football/tracking/scale_source_probe.py | cb3f582a1112b741a59e6ec409356418 |
| domains/football/tracking/test_numeral_registration.py | b139f3d10095c7032b8a0da49adf64bd |
| domains/tennis/tracking/camera_lock.py | eb9f9f8ef072fd6cbf3f2865d92b950f |
| domains/tennis/tracking/court_lines.py | 92854fd52aef1a233ef49bd53f4be39a |
| domains/tennis/tracking/identity.py | 1b21bc3e43ae11038de00cc61055fab5 |
| domains/tennis/tracking/test_camera_lock.py | ae871ef5d2ef6e60d5ec1c98336b5e18 |
| domains/tennis/tracking/test_court_lines.py | f930cd61ffb202889b8635db9dec6a7b |
| scripts/platformkit/ops_healthcheck.py | 470f0ca4c73c94f07bf984513a3a05ec |
| scripts/platformkit/test_footage_bridge.py | 05e93cefbeed510137c962252a04af18 |
| scripts/platformkit/test_ops_healthcheck.py | a83e39e3f18e890dd8418a7d37081658 |
| scripts/platformkit/test_tracking_corpus_ab.py | 52b36593b8237fa52614c55b4880ce1b |
| scripts/platformkit/test_tracking_schema_coordinate_space.py | ad385562eedfcc486df8c94bba663814 |
| scripts/platformkit/tracking/depth_replay.py | a256297360d6360d0c79ffa98d30d084 |
| scripts/platformkit/tracking/football_fieldview.py | e31900e0a672f89e8072e72cb61a974a |
| scripts/platformkit/tracking/football_snap.py | cfe9c20e4897ba67484f1908ad2669f2 |
| scripts/platformkit/tracking/framing_coverage.py | 89fb49050d132e7278f30431b6f7ac30 |
| scripts/platformkit/tracking/motion_bounds.py | 0f9a5451373f5c177ba54c5cb447f88f |
| scripts/platformkit/tracking/tennis_vertical_probe.py | ebd8a29b4d19788915f5ad02ff9cd883 |
| scripts/platformkit/tracking/test_depth_replay.py | 5e03db4604c2b22986fed6805edfdd1f |
| scripts/platformkit/tracking/test_footage_census.py | f165f5767f62c1317e2ce222aee995d4 |
| scripts/platformkit/tracking/test_football_fieldview.py | ba943bc29cd9570929addf4eae197f5c |
| scripts/platformkit/tracking/test_football_snap.py | 9a23577a8c8facf2e3450872b6d6da51 |
| scripts/platformkit/tracking/test_framing_coverage.py | bd95d37583c614442b5cef068fd0fc88 |
| scripts/platformkit/tracking/test_image_px_containment.py | d61be74247908cc1b7a3d0e467462f78 |
| scripts/platformkit/tracking/test_motion_bounds.py | b2f7622dda52b714e55ce71ef4d86a39 |
| scripts/platformkit/tracking/test_tracklet_merge.py | c6e27516f807c84b13731275b542e2d6 |
| scripts/platformkit/tracking/tracklet_merge.py | 96fceb35069c58b38eed2fc18ade3ce5 |
| scripts/platformkit/tracking_regression.py | e2969337ffff51215416a5452989befc |

### 2a-ii. Stale on the pod before this deploy (18)

| file | pod md5 before | md5 now |
|---|---|---|
| domains/baseball/tracking/command_meter.py | 052d1f10f35cd5573e4afa7da8540cac | 7c8a830c6f9d5ec020fb0d323336ae87 |
| domains/baseball/tracking/test_segmenter.py | 1e8bc93badc466d356171b4f0c5aed09 | b3ec7e50e42d665b742cfb259998035f |
| domains/basketball_nba/tracking/quality_probe.py | 07f9452beacf55026fa7dd766e295fbb | d26ff2de15918d8eb92259ddfb874807 |
| domains/basketball_nba/tracking/test_quality_probe.py | 7420650173470a1cd92a158f74c2f7f5 | 1808e403fa2fcfeb54354e5dd1eeeb62 |
| domains/football/tracking/adapter.py | 5fec87b1729a43490436efcf2d5ab2c0 | 1299329fbb5b7c0c3fdace04fdc3e070 |
| domains/football/tracking/field_gates.py | 0ec4cd7f3bf1f48951d994643d2046f6 | 8b2e7c093590feb47e312fd0826e253a |
| domains/football/tracking/geometry.py | 924c6405370cc26b89a36a41df3afc88 | 5771bde66cdb08fd51809b5291ddde1d |
| domains/football/tracking/test_adapter.py | da74566708b81e5012d532811cf5d7d5 | 11a19c3e1fb6a21bf1f66e6270f7f31d |
| domains/football/tracking/test_field_gates.py | 98cc4d7833bb24fa61c4b4a0c47f8728 | 1cb09633ceb046985f418591412cc0d0 |
| domains/soccer/tracking/pressing.py | 3ceddd2b4c89eff96238515d54c68cbf | 31d362484ef1a146736f6ffba4ddc063 |
| domains/tennis/tracking/adapter.py | 5a7a16393af4759f67a7ba81a2443168 | de56c8a1fb22a7b7f9dcc7e738cf279a |
| domains/tennis/tracking/court_diagnostics.py | 0c4082a6e82b3dd3cf5e4577bfb919f1 | 15122b8c46a094f3dd9caa158c110cfa |
| domains/tennis/tracking/frame_manifest.py | 5d0320abbe258c81bc4847f80c2559ec | eb42fbfb856f6d0fc6df02a5437bc88f |
| domains/tennis/tracking/test_adapter.py | e839a9ff2c4d2790d9377a1a688c8f22 | 34625e0ef771e051c32a10cd12b689ed |
| scripts/platformkit/footage_bridge.py | 6911e585f4a431300efe7b267c0aecad | 50ea98bce58ac074ce2e21153b59825e |
| scripts/platformkit/footage_cycle.py | 279ba81ddbc4aabceef5b7a558c44e3d | 9473938a3cdd0c26ae31f289e1b599b7 |
| scripts/platformkit/tracking/footage_census.py | 7f3cf55506ccaf219963cc0073a5fd17 | fed61f1510cfde41f3fe967de468d4d7 |
| scripts/platformkit/tracking_corpus_ab.py | 1e0c3800253108bfee24d8abd1b36778 | 5aeadef82527050c3d5007ca624deb73 |

**Already current before this lane (no action):**
`scripts/platformkit/tracking_schema.py` (6fd630b076542037e7f8a2a20420a419) and
`scripts/platformkit/tracking/image_px_containment.py`
(1ac8f3a6...) -- the beb8e4c6d containment gate was already on the pod, as were
`track_daemon.py`, `tracking_harness.py`, `tracking_features.py` and the other
93 in-scope files. Their raw-md5 difference was CRLF only.

### 2b. Dependency closure (3 more files)

- `scripts/platformkit/section_fallback.py` 74781e9f80f264f1cbe32fd7b54352d6 -- absent; `footage_bridge` could not import without it.
- `scripts/platformkit/demo_render.py` ae18897d600d780319c033150ba07fd6 -- stale.
- `scripts/platformkit/tennis_camera_lock_measure.py` 5d1b456aa49ac96c4255dcf163d4c6be -- absent; this is the script that produces the section-4 coverage number.

### 2c. Smoke import on Python 3.12.3 (30 non-test modules)

**28/30 OK.** Two failures, neither a py3.12-vs-3.10 issue:

- `scripts.platformkit.footage_bridge` -- `ModuleNotFoundError: No module named
  'scripts.platformkit.section_fallback'`. **Fixed by deploying the missing
  module**, not by editing code. Re-imported: OK.
- `scripts.platformkit.footage_cycle` -- `ImportError: cannot import name
  'render_csv' from 'scripts.platformkit.demo_render'`. **Not fixed, and not a
  pod problem**: it fails identically on the local box at HEAD `89c6da9ce`.
  `demo_render.py` defines `render`, not `render_csv`; `footage_cycle.py:26`
  imports a name that does not exist on master. Pre-existing broken import,
  reported rather than patched (no code edits in this lane).

No py3.12 incompatibility was found anywhere. No source file was edited.

## 3. Daemon restart

Every liveness read is from `/proc`, never `pgrep`.

| t (UTC) | event | pid |
|---|---|---|
| 00:09:05 | deploy tar extracted (file mtimes) | -- |
| 00:13:59 | pre-state: stage EMPTY (0 staged `.mp4`), 0 adapter/run_clip jobs in flight, ledger 395 lines | -- |
| 00:14:12 | pre-restart cmdlines recorded from `/proc` | keeper 1278551, daemon 2201564 |
| 00:14:13 | `kill 1278551` -- keeper first, so it cannot race the restart | 1278551 |
| 00:14:15 | `kill 2201564` -- the daemon | 2201564 |
| 00:14:17 | both confirmed gone (`/proc/<pid>` absent); MLB book capture 3040635 confirmed **ALIVE** | -- |
| 00:14:24 | keeper relaunched: `nohup setsid bash /workspace/keep_track_daemo?.sh` -- came up as a ppid=1 setsid leader | keeper **3047264** |
| 00:14:24 | keeper logged `track_daemon down -- restarting` and started the daemon, which publishes its own pidfile (`track_daemon.py:378`) | daemon **3047270** |

Restart was zero-cost: the stage was empty and no tracking job was in flight,
so nothing was interrupted.

Post-restart verification, all from `/proc`:

    pid=3047270
    cmdline: python -u -m scripts.platformkit.track_daemon --workers 10 --forever --interval 15
    cwd:     /workspace/nba-ai-system
    state=S ppid=3047264 sid=3047264
    start:   Wed Sep  2 00:14:24 2026
    /workspace/track_daemon.pid -> 3047270

The cmdline is byte-identical to the pre-restart one recorded in
`basketball_producer_fix_2026-09-01.md` section 7. Daemon start (00:14:24) is
after the deploy (00:09:05), which is the ordering evidence that the running
process loaded the new files.

The glob in the relaunch path (`keep_track_daemo?.sh`) is deliberate. The
keeper's own start-up self-clean is `pgrep -f keep_track_daemon.sh`, which
kills every other process whose command line mentions the script -- including
the ssh that launched it. Writing the name with a `?` keeps the literal out of
my command line while the shell still expands it to the real path.

**Landmine hit anyway (and survived):** the relaunch ssh returned exit 255 with
no output because a *diagnostic* `case` pattern later in the same command still
contained the literal script name, so the freshly started keeper `kill -9`'d my
`bash -c` wrapper. The keeper and daemon were unaffected; a follow-up ssh whose
patterns avoid the literal (`*keep_track_daemo[n]*`) confirmed both alive and
gave the pids above. Fifth sighting of this self-match landmine.

## 4. Proof the new code is live on the pod

`scripts/platformkit/tennis_camera_lock_measure.py` (deployed this session) on
`data/footage_corpus/tennis__tennis_nyYk2nPZAwY_720p.mp4` (274,423,923 bytes --
the same file the local run used), sequential plan `--range 15300 15600`, run
as my own `nohup setsid nice -n 15` job, log `/tmp/g14_tennis_seq.log`, output
`/tmp/g14_tennis_seq/`. Nothing under `data/` was touched.

| metric | local (1c5f1e6b7) | **pod, this session** |
|---|---|---|
| requested_source_frames | 301 | 301 |
| decoded | 301 | 301 |
| raw_accepts | 198 | 198 |
| fresh_solves | 187 | 187 |
| locks_formed | 12 | 12 |
| drift_checked_reuses | 83 | 83 |
| drift_rejects | 2 | 2 |
| solved_frames | 270 | 270 |
| **solved_frame_coverage** | **0.8970099667774086** | **0.8970099667774086** |

Bit-identical, every intermediate included. The frozen harness on the pod
output also reproduces: `n_frames 270`, `ball_rows 186`, `coverage_pct 1.0`,
`oob_pct 0.013`, `ball_valid_pct 0.6889`, `passed true`, `failures []`. Two
values differ in the last printed digit -- `jump_p95` 0.78 local vs 0.80 pod,
`median_step_distance` 0.1737 vs 0.1738 -- float/BLAS platform noise, nowhere
near a threshold. Before this deploy the pod could not have produced this
number at all: `domains/tennis/tracking/court_lines.py` and `camera_lock.py`
were absent from the pod filesystem.

## 5. Quarantine skip -- premise corrected, then measured

**The lane brief's premise is wrong and I did not confirm it.** The *daemon*
ledger enumerator does **not** skip quarantined clips and was never changed to.
`track_daemon.claimable()` (`track_daemon.py:129-161`) globs the staging dir
`data/footage_bridge/*.mp4` and filters on `.part` naming plus a 1 MB size
floor only; it never imports `footage_content_gate`. The quarantine is enforced
in two other places: at download time in `footage_bridge.py:572-574`
(`screen_fail_open` -> `quarantine`, which **moves** the file), and in the
corpus enumerators `tracking_corpus_ab.corpus_clips` and
`tracking/footage_census`, both of which call `is_quarantined`.

Measured on the pod against the real corpus, after the deploy:

    football  raw=9   after_gate=9      ncaa_basketball raw=6  after_gate=6
    kbo       raw=11  after_gate=11     npb             raw=6  after_gate=6
    mlb       raw=10  after_gate=10     soccer          raw=5  after_gate=5
    tennis    raw=9   after_gate=9      wnba            raw=5  after_gate=5
    TOTAL raw=61  after_gate=61  skipped=0

**The gate currently skips zero clips, and that is the honest result.** All 9
quarantined videos already sit physically outside `data/footage_corpus`, in
`data/footage_quarantine/`: `football__football_DrxDFaRonuE`, `GU6CrRLjTkw`,
`L3WOKdFhdkQ`, `VEoXn84p9o8`, `cxbBz4nkovE`, `iaDDTxNEOfE`,
`kbo__kbo_2ZtgAvs67so`, `mlb__mlb_QqHhEShXAX0`, `mlb__mlb_dVNOESziFWQ`. The
enumeration denominator is 61 rather than 70 because of the *move*, not the new
sidecar check. Zero clips in the corpus carry an in-place
`sport_verified=false` sidecar, so the new in-place branch has nothing to act
on today.

Positive control that the deployed code does work -- synthetic tmpdir, 2 clips,
one given a `sport_verified=false` sidecar, run through the pod's
`corpus_clips`:

    raw=2  after_gate=1  kept=['tennis__a.mp4']

So the guard functions; it is currently redundant with the physical move, and
becomes load-bearing the first time a clip is flagged without being moved.

## 6. Reproduce

    # inventory (local)
    git ls-tree -r --name-only HEAD | grep -E '^(scripts/platformkit/tracking/|scripts/platformkit/tracking_[^/]*\.py$|scripts/platformkit/track_daemon\.py$|scripts/platformkit/footage_[^/]*\.py$|domains/[^/]+/tracking/|domains/[^/]+/adapter[^/]*\.py$)'
    # local blob md5:               git show HEAD:<path> | md5sum
    # pod md5, CRLF-normalised:     tr -d '\r' < <path> | md5sum
    # deploy
    git archive HEAD -- <paths> | ssh -p 40048 root@213.192.2.83 'tar -x -C /workspace/nba-ai-system'
    # coverage proof (on the pod)
    python -u -m scripts.platformkit.tennis_camera_lock_measure \
      data/footage_corpus/tennis__tennis_nyYk2nPZAwY_720p.mp4 /tmp/g14_tennis_seq --range 15300 15600

## 7. Not verified

- **No pytest on the pod** (already documented in
  `basketball_producer_fix_2026-09-01.md`). The 22 deployed test files are now
  present and current there but were NOT executed. Evidence for the deployed
  modules is the 3.12 smoke import plus the section-4 end-to-end reproduction,
  not a pod test run.
- **The daemon has not yet processed a game under the new code.** The stage was
  empty at restart and is still empty; the ledger is unchanged at 395 lines.
  "Deployed and restarted" is proved; "the new code changed a ledger verdict"
  is not, and cannot be until the bridge stages a game.
- **`footage_cycle` is broken on master** (`render_csv` import). Not fixed here.
  It is not in the daemon's path, so tracking is unaffected, but any lane that
  runs `footage_cycle` will fail at import.
- Only the tennis lever was re-measured on the pod. The football, soccer and
  baseball modules deployed here are verified by smoke import alone; no adapter
  was re-run against its corpus, so no before/after adapter verdict is claimed.
- Line endings now differ within the pod tree: newly deployed files are LF, the
  pre-existing tree is CRLF. Python is indifferent, but any future md5
  comparison must keep normalising or it will report a false 100% drift.
