# S49b -- /ready selfcheck evaluates the route set at probe time (2026-09-03)

Lane Z, main repo. Calibration language only: nothing here is a performance,
profit or edge claim. This row measures PROBE CORRECTNESS -- whether `/ready`
reports the route table the process is actually serving.

Gap (from `docs/evidence/harness/S21_deploy_2026-09-03.md` section 5 and its
NEW GAP list): `supervisor/health.py:222-224` returned a cached `mount_selfcheck`
snapshot, and `predict_service/app.py:579` takes that snapshot at module scope --
before the paper routers finish registering. `/ready` therefore served the
pre-registration snapshot for the life of the process, reporting `not_ready`
with `missing:['/api/paper/predictions']` while that route answered HTTP 200.
Every restart-to-fix instruction that reads `/ready` was acting on a false
negative. Neither `supervisor/**` nor `predict_service/**` is a human-gated path
(`.claude/rules/human-gated-paths.md` gates `src/`, `kernel/`, `api/`,
`scripts/team_system/`, `intel/`).

## 1. Live pod evidence (read-only, no deploy, no restart)

Reached with `ssh -o BatchMode=yes -F ~/.ssh/config.pod pod`. The lane's brief
named port 8098; nothing listens there (`curl` exit code 000, empty body). The
m1_api_paper service is on **8099**, as in the S21 memo. Read there, 2026-09-03:

```
curl -s localhost:8099/ready
{"status":"not_ready","selfcheck":{"checked":["/api/paper/predictions","/health","/api/sports"],
 "present":["/health","/api/sports"],"missing":["/api/paper/predictions"],"ok":false}}

curl -s -o /dev/null -w "%{http_code}" "localhost:8099/api/paper/predictions?limit=1"   -> 200

curl -s localhost:8099/openapi.json ->  predictions_in_openapi True
                                        n_paper_paths 11
                                        n_paths 70
```

So the pod is serving the route (HTTP 200, present in its own OpenAPI schema,
11 `/api/paper/*` paths of 70 total) while `/ready` calls it missing. The false
negative is reproduced live and unchanged since the S21 observation.

## 2. Local reproduction, before the fix

In-process against the REAL `predict_service.app` object, mimicking the pod's
boot ordering: detach `/api/paper/predictions`, clear the cache attribute, run
`mount_selfcheck` (the pre-registration snapshot), re-attach the route (the
routers register afterwards), then probe through `TestClient`.

BEFORE (cache in force):

```
pre-registration selfcheck: {"checked": ["/api/paper/predictions","/health","/api/sports"],
  "present": ["/health","/api/sports"], "missing": ["/api/paper/predictions"], "ok": false}
GET /ready -> 503 {"status": "not_ready", "selfcheck": {... "missing": ["/api/paper/predictions"], "ok": false}}
openapi has /api/paper/predictions: True     paper paths in openapi: 11
GET /api/paper/predictions -> 200
```

Same shape as the pod: 503 `not_ready` beside a 200 on the route it calls missing.

AFTER (same script, same procedure, post-fix):

```
pre-registration selfcheck: {... "missing": ["/api/paper/predictions"], "ok": false}
GET /ready -> 200 {"status": "ready", "selfcheck": {"checked": ["/api/paper/predictions","/health","/api/sports"],
  "present": ["/api/paper/predictions","/health","/api/sports"], "missing": [], "ok": true}}
openapi has /api/paper/predictions: True     paper paths in openapi: 11
GET /api/paper/predictions -> 200
```

The stale snapshot is gone; the pre-registration selfcheck still reports the
route missing at the moment it ran, which is the honest answer for that instant.

## 3. The fix (root, one function)

`supervisor/health.py` `mount_selfcheck` now re-reads `app.routes` on EVERY
call instead of returning a cached snapshot. Both callers route through this one
function (`predict_service/app.py:193` for `/ready`, `:579` for the startup log)
and there are no others in the tree, so the single change covers every path.

The last result is still stored on the app object (`_SELFCHECK_ATTR`) but is now
used only to decide whether to log -- the WARN/INFO line is emitted when the
missing set CHANGES, not on every probe, so a per-second readiness probe does not
spam the log.

Fail-closed semantics are unchanged and were re-tested:

- a required route that is genuinely absent -> `ok=False` -> `/ready` 503 `not_ready`;
- `mount_selfcheck` unavailable or raising -> `/ready` 200 liveness-only with
  `selfcheck: "unavailable"` (unchanged);
- `/health` remains a bare 200 `{"status":"ok"}` (supervisor contract untouched);
- `_REQUIRED_ROUTES` unchanged; no threshold, bar or gate value moved.

`supervisor/health.py` is 283 lines (<= 300 cap).

## 4. Tests (per-file only; the full tree was never run)

- `python -m pytest predict_service/test_app_ready_probe.py -q` -> **5 passed**
  (4 before + new R6). R6 detaches the required route on the real app, asserts
  the first probe is 503 `not_ready` with the route surfaced (fail-closed), then
  re-attaches it as the paper routers do after module execution and asserts the
  NEXT probe is 200 `ready` with the route in `present`. It restores the route
  and clears the attribute in a `finally`.
- `python -m pytest supervisor/test_health.py -q` -> **7 passed** (count
  unchanged). SH3 was rewritten: it previously asserted `result1 is result2`,
  i.e. it PINNED the caching defect. It now asserts two calls on an unchanged app
  agree by value, and that a route added after the first call reads PRESENT on
  the next call.

Honesty rail: every `/ready` body in the tests is checked for `$`, `pnl`,
`profit`, `roi` tokens (pre-existing `_assert_no_money`); the new test reuses it.

## 5. Deploy note

Nothing was deployed and nothing was restarted from this lane: the pod was read
over ssh only (no scp, no kill, no service bounce). `supervisor/health.py` is not
in the S21 deploy set, so the pod still runs the cached-snapshot version and its
`/ready` will keep reporting the false negative until the file ships. The
parity-deploy lane owns the pod today and should carry
`supervisor/health.py` (plus the two test files, which are inert on the pod) in
its next set; the fix takes effect on the next m1_api_paper start after that.

## 6. NOT VERIFIED

- Not verified on the pod: the fix was measured locally only. No pod process
  runs the new code, and no post-deploy `/ready` reading exists yet.
- The lane's stated probe port (8098) is not the serving port; only 8099 was
  read. Whether anything is meant to listen on 8098 was not investigated.
- Why the paper routers register after the module-scope selfcheck on the pod
  (import failure vs. ordering) was not re-diagnosed; S21 attributes it to the
  routers being registered after module execution. This row fixes the PROBE, not
  the mount ordering.
- The m1_api_paper ProcSpec still points its HTTP readiness at `/health`, not
  `/ready` (`supervisor/stack_specs.py` -- unread this lane); no supervisor
  decision consumes `/ready` today, so the false negative was misleading humans
  and instructions, not gating a restart automatically.
- Log-volume claim (WARN only on change) is read off the code path exercised by
  the tests; no long-running process was observed to confirm it in production.
- No metric in any other S-row moves; no bar, threshold or gate value was touched.
