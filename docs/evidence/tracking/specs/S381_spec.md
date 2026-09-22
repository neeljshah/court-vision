GAP S381 | sport tennis | worktree harness-h37 (master-based) | log cx_s381_tennis_point_probe
# Point-level live tennis state: bounded source probe, or an honest BLOCKED (design: ASTRA_ROUND13 section 1 row 12)

SINGLE PROBLEM: tennis is the highest-volume captured market family (tens of thousands of prints a day) but NO qualifying state
source exists: 0 of 986 historical matches carry wall-clock score state and the live scoreboard feed in use reports per-set games
only. The landed recursion model (row S361) needs server + point score + games + sets at a known receipt time.

BINDING BEFORE-CONDITION: `ls domains/tennis/live_point_probe.py` fails.

CHANGE (NEW files only):
1. domains/tennis/live_point_probe.py (<= 300 LOC, stdlib urllib only): `--candidates <json> --out <json> [--max-requests 20]
   [--spacing-sec 2.0]`. For each candidate {name, url, kind} issue plain unauthenticated GETs with the DEFAULT urllib headers (a
   custom User-Agent is known to be refused by one provider), no cookies, no credentials, no login, no challenge solving; the
   global request budget and the per-host spacing are hard limits; a 401 / 403 / 429 or any challenge page stops that host for the
   run and is recorded as BLOCKED_BY_HOST. Record per response: request_start_utc, response_end_utc (timezone-aware), status,
   content type, byte length, body SHA-256, whether it parses as JSON, and a FIELD CENSUS by recursive key search -- does the
   payload expose (a) a server / serving indicator, (b) a within-game point score (0 / 15 / 30 / 40 / AD or tiebreak points), (c)
   games in the current set, (d) sets, (e) stable player or match identities, (f) a source timestamp. Bodies are NOT stored (hash +
   field census only; at most 300 characters of key PATHS, never values that identify a person beyond a match id). Verdict per
   candidate: POINT_LEVEL (a to d all present on a live match), SET_LEVEL, NO_LIVE_MATCH (cannot judge now), BLOCKED_BY_HOST,
   ERROR. Overall verdict: QUALIFYING_SOURCE_FOUND only if some candidate is POINT_LEVEL twice, at least 30 s apart, with a changed
   body hash; otherwise BLOCKED with the reason. Strict-int counts; every except clause counts or re-raises.
2. domains/tennis/live_point_candidates.json: the candidate list -- the public scoreboard and per-event summary endpoints of the
   provider already used by the state capture (its module is not on master yet, so the shapes are given here verbatim:
   https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/scoreboard?dates={date} with league atp and wta, and the
   per-event summary under the same /apis/site/v2/sports/tennis/{league}/ prefix: summary?event={event_id}; do not invent other
   hosts), plus the official ITF live page named in the design (https://www.itftennis.com/en/world-tennis-tour-live/). No candidate may need a key or a login.
3. tests/domains/tennis/test_live_point_probe.py (mirror the existing domains/tennis test layout; say where it is): an injected
   opener (NO network in tests): budget and spacing enforced, host stop on 403 / 429, field census on a synthetic point-level
   payload and a set-level payload, the two-observation rule, bodies never written, timezone-aware receipts.
4. Memo docs/evidence/harness/S381_tennis_point_probe_2026-09-21.md (the builder has no network; the orchestrator runs the probe
   once from the main tree and records the verdict in the ledger).

CONTROLS: PREPARE only, NEW files only, construct tests, no network in the build lane. ACCEPTANCE: per-file test passes; --help
works; diff = NEW files only; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends with a NOT VERIFIED list. The pod is OFF.
