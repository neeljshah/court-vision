GAP G226c | sport wnba | worktree a6 | log g226c_basketball_adapter_deploy_and_run
**DEPLOYMENT AND VALIDATION.** `src/` is HUMAN-GATED: READ and IMPORT only. This row deploys ALREADY-
LANDED, ALREADY-TESTED code to the pod and runs it once. **It writes no new production logic.**

**HELD UNTIL G211b HAS REPORTED.** G211b is measuring per-frame TIME on the pod and a route job would
corrupt it. **Check first and say in your memo that you checked and when you began.** The `track_daemon`,
`keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner` are PERMANENT
residents and the load floor -- never wait for them, never kill or restart them. Preparation may proceed
immediately.

**WHY THIS ROW EXISTS.** G226 landed a basketball tracking adapter emitting the canonical schema with
honest `image_px` provenance (`domains/basketball/tracking/adapter.py` 169 lines, `geometry.py` 29 lines,
plus an additive `"basketball"` entry in `scripts/platformkit/adapter_run.py`); 8 adapter/geometry tests,
the 9 shared `test_adapter_run.py` tests and the LOC rail all pass in master. **G226b then found the pod
does not have it: `MISSING domains/basketball/tracking/adapter.py`, `MISSING
domains/basketball/tracking/geometry.py`, and `POD_GIT_PRESENT=no`** -- the pod is a NON-GIT checkout
with no incremental deploy path, and the only mechanism in the repo is `scripts/bootstrap_pod.sh`, a full
scp bootstrap. G226b correctly refused to hand-copy and stopped.

**THE DEPLOYMENT IS SAFE, AND HERE IS THE EVIDENCE, verified in master by the orchestrator so you do not
have to re-derive it.** The concern was that registering `basketball` in the adapter registry might
change what the LIVE daemon routes. **It cannot.** `scripts/platformkit/track_daemon.py:75` defines
`CLIP_SPORTS = {"wnba", "basketball", "ncaa_basketball", "nba"}`, and `build_command` at `:83-105`
branches on it FIRST:

    if sport in CLIP_SPORTS:
        return [sys.executable, "scripts/run_clip.py", "--video", ..., "--frames", "3000", ...]
    adapter = SPORT_ADAPTER.get(sport, sport)
    return [sys.executable, "-m", "scripts.platformkit.adapter_run", adapter, ...]

**Every basketball sport returns before the adapter dispatch is reached, so the daemon will keep sending
basketball clips to `run_clip.py` exactly as it does now. The new adapter runs ONLY when a human or this
row invokes `adapter_run basketball` explicitly.** **Changing `CLIP_SPORTS` is a SEPARATE decision with
its own id -- do NOT touch it in this row.**

METHOD:
  1. **Confirm the pod is free of measurement rows and record the load floor you observed.**
  2. **DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE here (it reports the whole cluster filesystem
     against a 50 GB volume cap, which caused a `Disk quota exceeded` incident). **`dd conv=fsync` write
     probe of a few MB before writing, record `du -sm /workspace/nba-ai-system/data` (baseline ~31,450 MB
     of 50,000), and STOP and report if the probe fails -- do not delete anything to make room.**
  3. **Deploy EXACTLY THREE FILES by scp and nothing else**:
     `domains/basketball/tracking/adapter.py`, `domains/basketball/tracking/geometry.py`, and
     `scripts/platformkit/adapter_run.py`. **Record the SHA-256 of each on BOTH sides and show they
     match.** **Back up the pod's existing `adapter_run.py` first and record its SHA-256
     (`90172789dc13bf771a93c5dacbb9568eceb06783dc51e8b591fa2f380621f4e0` as G226b measured it) so the
     change is reversible.** **Do NOT run `bootstrap_pod.sh`** -- it is a full bootstrap and would
     overwrite far more than this row intends. **Deploy nothing else: no `src/` file, no weights, no
     config.**
  4. **Immediately after deploying, prove the daemon is unaffected**: re-read
     `scripts/platformkit/track_daemon.py` ON THE POD and confirm `CLIP_SPORTS` still contains the
     basketball sports and that `build_command` still branches on it before the adapter dispatch.
     **Report that check explicitly.** If the pod's daemon file differs from master's in a way that
     breaks this argument, **STOP, roll back `adapter_run.py` from your backup, and report.**
  5. **Run the adapter ONCE, manually and bounded**, on one basketball clip
     (`wnba__wnba_01.mp4`: 2,931,985,407 bytes, 1920x1080, 174,430 frames). **Write to a NEW tracking
     directory. Do NOT delete, overwrite or migrate any legacy basketball table** -- G207, G226 and
     G226b all cite them. Note from G206 that `--frames N` counts DETECTOR-SELECTED gameplay frames and
     FAILS CLOSED, so choose a budget large enough to select gameplay frames rather than a tiny one.
  6. **Score the result with the harness.** Report the **stage reached (EXCLUDED / UNSCORABLE / SCORED),
     the verdict and the FIRST FAILURE HEAD verbatim**, the emitted row count with its named eligible
     denominator (attempted/evaluated frames, never `--frames`), and a **column-by-column comparison of
     the emitted header against a REAL adapter table read from the pod** (not transcribed from a spec).
  7. **Clean up your temporary artifacts and report bytes freed.** **Leave `adapter_run.py` deployed**
     -- it is additive and provably inert for the daemon -- but say plainly that you left it, and keep
     the backup in place.

**WHAT SUCCESS IS, AND IT IS DELIBERATELY MODEST: basketball reaching SCORED rather than EXCLUDED, then
failing `coordinate_contract`.** Football, baseball and soccer all emit `image_px` and all fail that
gate, but they are SCORED, so their failure is visible and measurable; basketball is not even that.
**Do NOT change the coordinate contract, any gate, any threshold or the harness to force a pass.**
Automatic basketball corner search is 0/17 (G210b, G214) and G223, G224 and G227 closed the in-repo
classical routes tonight, so there is no basis whatever for emitting a court coordinate here.

**HONEST LIMITATIONS to state, not discover:** one clip, one bounded run, on a shared pod -- an EXISTENCE
result, not a rate. The route is NON-DETERMINISTIC (G190/G195/G198/G203) so a single score is one draw.
An adapter is necessary but demonstrably NOT sufficient for court coordinates. **You are not claiming the
legacy basketball feature table is wrong**; this adds a canonical table beside it.

ACCEPTANCE RULE:
  metric        = both-sides SHA-256 for the three deployed files; the post-deploy daemon-routing check;
                  the stage reached; the harness verdict and first failure head verbatim; the schema
                  comparison; the row count with its named denominator; bytes freed
  before        = basketball is 0 scored / 3 EXCLUDED for noncanonical columns; the adapter is landed and
                  unit-tested in master but absent from the pod, which has no git and no incremental
                  deploy path
  bar           = **basketball reaches SCORED rather than EXCLUDED**, with a `coordinate_contract`
                  failure being the expected and accepted outcome. **An honest failure to reach SCORED,
                  with the reason named, is also a real result.** Force no pass.
  n             = 1 clip, 1 bounded run (EXISTENCE)
  eye check     = none; this is a schema and contract result
  must not move = `CLIP_SPORTS` and every other line of `track_daemon.py`, the coordinate contract, the
                  harness, every gate, threshold, bar and verdict, `src/` (READ and IMPORT only), the
                  other sports' adapters and registry entries, the legacy basketball tables, the pod
                  daemon and keeper processes, the corpus
EVIDENCE: docs/evidence/tracking/g226c_basketball_adapter_deploy_and_run_2026-09-04.md with the deploy
manifest and both-sides hashes, the backup path and hash, the daemon-routing check, the stage reached,
the verdict and first failure head, the schema comparison, the denominator, every disk-guard probe,
bytes freed, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: per-file tests only, pasted. NEVER a full pytest.
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
