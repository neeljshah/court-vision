# S446 observation support census - 2026-09-24

Candidate built and ten times fixed against binding review rounds. Per-file pytest across the eight owned test files: 66 passed (41 main, 9 fix-1b regressions, 6 fix-1c regressions, 2 fix-1d regressions, 2 fix-1e regressions, 2 fix-1f regressions, 1 fix-1g regression, 3 fix-1j regressions). No independent acceptance or real-run coverage result is claimed. Before = 0: the census module was absent before coding.

Machine: local Windows worktree C:/Users/neelj/nba-harness-h99. Two roles (AMENDMENT 7(b): recorded as roles, not as a claim of divergence), read fresh via `git rev-parse` at this lane's finish (AMENDMENT 8(b) is the fast-forward / A9-last rule; 9(b) is the NEW GAP) -- candidate HEAD (this worktree's own commit, unmoved during this lane): `907bb635c37f9ca52fc61a568e64b1b129ee052a`; verification base (`master`, equal to the candidate HEAD after the orchestrator fast-forwarded this worktree immediately before resubmission): `907bb635c37f9ca52fc61a568e64b1b129ee052a`. The must-not-move comparison and every A9 row below are regenerated against the verification base, the last edit of this lane. Only the spec-owned files were created or edited: observation_support_census.py, observation_support_phases.py, eight test files, this memo, and the tracked STEP 2 proposal mirror. No archive, network, pod, service, flag or production threshold was exercised or changed.

## Binding before-condition executed before coding

The read-only helper executed assertions against the current sources and
returned this exact output before the module was created:

```text
BEFORE a: PASS
BEFORE b: PASS
BEFORE c: PASS
BEFORE d: PASS
BEFORE e: PASS
BEFORE f: PASS
BEFORE g: PASS
BEFORE h: PASS
BEFORE i: PASS
BEFORE passed=9 failed=0
```

Exact source evidence supporting that output:

- (a) capture_scheduler.py:123: `if start - 120 <= now < start + 3600: priority.append(game); ids[game] = row["game_id"]`. Line 113 separately says `if any(b - a < 3600 for a, b in zip(starts, starts[2:])): raise ValueError("schedule exceeds two games per hour")`.
- (b) forward_capture_profile.json:2-6: `"focus_tick_s": 5`, `"reservation_ttl_s": 5`, `"focus_share_percent": 45`, `"maximum_scheduled_games_per_hour": 2`, `"anonymous_rate_ceiling": 3`.
- (c) capture_scheduler.py:9: `CLASSES = ("focus_books", "trades", "bulk", "discovery", "reserve")`; line 10: `SHARES = (45, 35, 10, 5, 5)`. local_capture_runner.py:182: `state["requests_by_class"] = {kind: 0 for kind in scheduler.CLASSES}`; line 197: `state["requests_by_class"]["reserve" if retry else kind] += 1`; line 204: `for kind, key in plan.requests:`. Line 236: `writer.atomic(lrow.heartbeat_path("kalshi", sport, writer.root), state["hb"][sport], "heartbeat")`.
- (d) local_capture_limiter.py:46: `FLOOR, CEILING, STEP, INCREASE_INTERVAL_SEC, WINDOW_SEC = 0.5, 3.0, 0.25, 60.0, 600.0`.
- (e) local_capture_runner.py:148-149: `batch = drain(client, scope.KALSHI_BASE + "/events",` and `{"series_ticker": key[1], "status": "open", "with_nested_markets": "true"},`.
- (f) local_state_capture_sources.py:27: `_MLB_STATUS = {"Preview": "pre", "Live": "live", "Final": "final", "Game Over": "final"}`. Lines 28-33 map STATUS_FINAL, STATUS_CANCELED, STATUS_WALKOVER, STATUS_RETIRED and STATUS_FULL_TIME to `"final"`.
- (g) ingame_gumbo_mlb.py:151: `"inning": inning,`; live_state_nba.py:91: `period=row.get("period"),`; ingest_nfl_states.py:205: `"period": period,`.
- (h) markout_causal.py:24: `DEFAULT_HORIZONS_S = (30.0, 120.0, 300.0)`; line 28: `DEFAULT_MAX_WAIT_S = 30.0`. microstructure_licence.py:36-37: `# PROPOSED sealed primary cell (family x this one horizon); every other` / `# horizon and family is descriptive only. One primary cell: no multiplicity`.
- (i) RESULTS_LEDGER_SYSTEM.md:750 records: `the books focus window closes 3600 s after start, so no late-game regime is measurable under this capture profile`. This checks the recorded S424 statement only. This lane did not remeasure its captured games.

## Imported landed interfaces read before coding

All direct project imports were read before implementation. Exact signatures:

```python
def parse_venue_time(value: object) -> float | None:
def count(value: object) -> int:
def _shards(root: Path, date: str, sports: set, required: bool = True) -> dict:
def _write_atomic(output: Path, result: dict) -> None:
```

`parse_venue_time` validates each receipt, including zones; non-finite and absurd timestamps are refused. `instant()` converts through it only: `int(round(parse_venue_time(v) * 1_000_000))`, a strict integer microsecond, never a Decimal string. Phase and HTTP counts use the landed strict-int count helper; inning/period values outside 1..100 are refused, not clipped. The census never consumes sizes, quantities, prices or fees.

CLASSES is imported from the scheduler. AMENDMENT 9(a) (FIX 1j) superseded the original rule here: a request class is NEVER inferred from record_type (record_type only gates whether a line is a recognized book row at all -- snapshot/snapshot_bulk, else nonbook:<type> folded into refused_schema_or_time). An explicit request_class field, when present, is used as-is (validated against CLASSES); when absent -- true of every real capture row today -- the row is still accepted but counted request_class_unresolved and excluded from focus/bulk support. No heartbeat count is represented as a receipt.

S410's shard discovery and atomic JSON writer are reused. Both D and D+1 are streamed in each channel, including games whose fixed hour ends on D but whose terminal is on D+1. Only served ticker/game_key receipts are retained in compact timestamp/label tuples. No whole shard read occurs. Inputs are hashed in the same streaming pass.

## Report semantics and denominators

Every visible served schedule row appears, even with no receipts. Schedule identity is validated and de-duplicated before the as-of filter runs (item h); a duplicate visible identity refuses the whole run with exit 3. State joins use the explicit native game_key in the schedule; books join through event_ticker == game_id (AMENDMENT 5(a), FIX 1f), so a game's two market tickers both count. Both required dates are listed, and every missing channel/sport/day is NO_SHARD. The v2 capture_version is required for state rows.

Phase boundaries are state receipt times, not estimated play times. Regulation phases absent from the feed remain UNOBSERVED. State rows received after the terminal receipt are counted `post_terminal_rows`, never dropped silently.

Every raw line lands in exactly one canonical category on every code path, including early exits: future, unserved and non-book rows fold into `refused_schema_or_time` (their specific reason kept beside as a named detail counter), so `rows == accepted + duplicate_receipt + out_of_order + refused_schema_or_time` always (AMENDMENT 2(b)). The first (stream id, instant) copy is kept; a later copy of an already-seen instant is `duplicate_receipt`; an earlier instant than the last accepted one is `out_of_order`. The stream id is the raw market ticker for books and the game_key for state (AMENDMENT 5(a)), so a game's two markets never share dedup/order state.

POST_FINAL begins exactly at the first unambiguous normalized final receipt (repeated finals: the first is terminal) and spans a fixed 300 seconds, clipped at that boundary regardless of when a closing receipt arrives (AMENDMENT 2(a)). The window is CLOSED only by evidence: a real book receipt at or after final+300s. Without one, the window is UNCLOSED and can never read "covered", only "partial" (a receipt exists inside the window) or "unresolved" (nothing does); a closure receipt after final+300s never becomes a support point itself, it only proves collection continued. `gap_s` is the trailing gap from the last in-window receipt to final+300; `max_receipt_gap_s` separately exposes interior holes, including the boundary-to-close span.

## Acceptance cases and executed checks

| Case | Construct assertion | Result |
|---|---|---|
| 1 | Native-shaped fixture through CLI twice; inning 3/4 exact | PASS |
| 2 | Inning 6/7 exact | PASS |
| 3 | NBA and NFL period 3/4 exact | PASS |
| 4 | MLB extras and NBA/NFL OT | PASS |
| 5 | Final boundary and one microsecond before it | PASS |
| 6 | Focus/bulk class counts, silent seconds and receipt gap | PASS (mechanism only, explicit request_class; see FIX 1j -- INSUFFICIENT on today's real rows, which carry no such field) |
| 7 | Inside-window fraction is exactly 100/200 | PASS |
| 8 | Fixed close and later terminal are separate instants | PASS |
| 9 | Full 300-second POST_FINAL with closure receipt at the boundary | PASS |
| 10 | POST_FINAL trailing gap, partial and covered=false | PASS |
| 11 | Missing final counted and unresolved | PASS |
| 12 | Served game with existing empty shards retained | PASS |
| 13 | Missing next-day state shard is NO_SHARD | PASS |
| 14 | First-copy kept, later duplicate/out-of-order refused | PASS |

Additional tests cover malformed count types, absurd counts, missing zones, non-finite timestamps, interior holes, censoring, late next-day rows, channel isolation, numeric JSON receipt decoding, streamed partial-line refusal, profile tick reading, multiple served games, an injected fsync failure, the AMENDMENT 1 items (a),(c),(e)-(i), and the AMENDMENT 2 regressions below.

## Executed commands and results

```text
python -m pytest tests/platformkit/ingame/test_observation_support_census.py -q -p no:cacheprovider
41 passed
python -m pytest tests/platformkit/ingame/test_observation_support_census_1b.py -q -p no:cacheprovider
9 passed
python -m pytest tests/platformkit/ingame/test_observation_support_census_1c.py -q -p no:cacheprovider
6 passed
python -m pytest tests/platformkit/ingame/test_observation_support_census_1d.py -q -p no:cacheprovider
2 passed
python -m pytest tests/platformkit/ingame/test_observation_support_census_1e.py -q -p no:cacheprovider
2 passed
python -m pytest tests/platformkit/ingame/test_observation_support_census_1f.py -q -p no:cacheprovider
2 passed
python -m pytest tests/platformkit/ingame/test_observation_support_census_1g.py -q -p no:cacheprovider
1 passed
python -m pytest tests/platformkit/ingame/test_observation_support_census_1j.py -q -p no:cacheprovider
3 passed
```

Only these eight per-file runs were executed; the full suite was never run.
CLI help: `python -m scripts.platformkit.ingame.observation_support_census --help`
exits 0. Case 1 runs the CLI entry point twice and asserts byte-identical JSON.
No real archive fixture or external dependency is used by any construct.

Final contract preflight over every current candidate path (FIX 1j; the
verdict file itself is never a preflight path):
`python -m scripts.platformkit.tracking.contract_preflight --base master --spec docs/evidence/tracking/specs/S446_spec.md --paths scripts/platformkit/ingame/observation_support_census.py scripts/platformkit/ingame/observation_support_phases.py tests/platformkit/ingame/test_observation_support_census.py tests/platformkit/ingame/test_observation_support_census_1b.py tests/platformkit/ingame/test_observation_support_census_1c.py tests/platformkit/ingame/test_observation_support_census_1d.py tests/platformkit/ingame/test_observation_support_census_1e.py tests/platformkit/ingame/test_observation_support_census_1f.py tests/platformkit/ingame/test_observation_support_census_1g.py tests/platformkit/ingame/test_observation_support_census_1j.py docs/evidence/harness/S446_observation_support_2026-09-24.md docs/evidence/harness/S446_PROPOSAL_focus_profile_2026-09-24.md`
Result: 9 PASS, 0 FAIL (vocab, crlf, loc, schema, head_slice, spec_threshold
19 literals matched, proposed, removed_artifact, row_duplication).

Current line counts (`wc -l`), all ASCII, all <= 300: census.py 289, observation_support_phases.py 112 (FIX 1l adds per-class trades/discovery/reserve support buckets), main test file 300, `_1b` test file 104, `_1c` test file 73, `_1d` test file 35, `_1e` test file 25, `_1f` test file 46, `_1g` test file 61, `_1j` test file 57 (FIX 1l adds the reserve-not-bulk regression), this memo (<= 300), and the tracked proposal mirror 84 lines (byte-identical to the gitignored copy).

## Step 2 proposal

Tracked file (AMENDMENT 2(c), named by this memo and by preflight):
`docs/evidence/harness/S446_PROPOSAL_focus_profile_2026-09-24.md`. The
gitignored copy at `docs/research/organization-sprint/PROPOSED_S446_focus_profile.md`
remains, byte-identical text, per the amendment. It proposes final-receipt+300
focus close (hard ceiling `min(final+300, start+21600)`) with a concurrent-focus
check against the two-games-per-hour capacity rule, and keeps the 3.0
requests/second AIMD ceiling. AMENDMENT 4(a) corrects that check to count
MARKET TICKERS, not games (see FIX 1e below): with the verifier's worked
example (2 games/hour, 6 h ceiling, 5 s tick, 3.0 req/s, 45 percent focus,
2 markets/game): 12 concurrent games, 24 requests/tick required (4.8 req/s),
6 requests/tick allocated (1.2 req/s), fits = FALSE -- the proposed parameters
are recorded as INFEASIBLE / UNRESOLVED pending a later owner decision.
Nothing is adopted; no scheduler, profile or threshold is changed. Real runs
performed: 0. Real games/shards/receipts processed: 0/0/0. The 2026-09-22 and
2026-09-24 orchestrator runs remain pending after landing.

## FIX 1b (AMENDMENT 1) -- applied items

| Item | Change |
|---|---|
| (a) | `support()` carries a pre-boundary receipt's remaining tick into POST_FINAL |
| (b) | `_collect()`: first (key, instant) copy kept; later copy/earlier instant refused |
| (c) | every raw line lands in exactly one counted category (later widened by AMENDMENT 2(b)) |
| (d) | `instant()` is a strict integer microsecond via the shared parser only, no Decimal |
| (e) | lower window boundary exact; repeated finals -> first is terminal; `delayed` != final |
| (f) | per-day/per-sport/per-channel counters beside the global totals |
| (g) | `_game()` counts `post_terminal_rows`, never drops them |
| (h) | schedule rows validated and de-duplicated before the as-of filter |
| (i) | a focus_books receipt outside the admission window is `snapshot_outside_focus` |
| (j) | proposal gains the hard ceiling and the concurrent-focus capacity check |

## FIX 1c (AMENDMENT 2) -- applied items

Round 2 codex sol REJECT (four blockers, one correction).

| Item | Change | Test(s) |
|---|---|---|
| (a) | `_game()`: POST_FINAL closes only on evidence -- a real book receipt at or after final+300s; the as-of cutoff no longer implies closure | `test_post_final_closure_absent_not_covered`, `test_post_final_closure_present_at_365_covered` (1c); `test_post_final_carry_forward_off_grid_covered`, `test_post_final_carry_forward_flips_uncovered` (1b, given a +365s closure receipt); `test_post_internal_gap_and_censoring` (main, updated: partial without closure, not unresolved) |
| (b) | `_collect()`: future/unserved/nonbook early exits now also bump `refused_schema_or_time` beside their detail counter | `test_future_row_folds_into_refused`, `test_unserved_row_folds_into_refused`, `test_nonbook_row_folds_into_refused`, `test_early_exits_partition_invariant_holds` (1c) |
| (c) | STEP 2 proposal mirrored to a tracked path; this memo and preflight name it | see Step 2 section above |
| (d) | RESULTS_LEDGER_SYSTEM.md row removed from the A9 table (it moves with every landing); every other row regenerated at base sha `ef7248901` | table below |
| (e) | superseded pre-fix narrative and stale length claims removed; this memo rewritten under 300 lines | this file |

A9 identities (this tree, candidate HEAD `907bb635c37f9ca52fc61a568e64b1b129ee052a`, regenerated as this lane's final edit against verification base `907bb635c37f9ca52fc61a568e64b1b129ee052a` (AMENDMENT 8(b) is the fast-forward / A9-last rule, not 9(b)), both read fresh via `git rev-parse`; bytes/SHA256 are LF-normalised, `read_bytes().replace(b"\r\n", b"\n")`; Resolution `n/a` -- no image inputs. 11 of these 22 rows also exist in `master`; all 11 were cross-checked byte-for-byte, LF-normalised, against `git show master:<path>` at the verification base and all 11 MATCH, including S446_spec.md (master already carries this row's own landed amendment text) and local_state_capture_sources.py. The other 11 rows are this row's own new/edited files, correctly absent from master):

| Full path | Bytes | SHA256 | Resolution |
|---|---|---|---|
| C:/Users/neelj/nba-harness-h99/docs/evidence/tracking/specs/S446_spec.md | 22369 | 865a8dfdff112df4ea79f5065ee1e3cb7f04cdba8efb1b1739431496da95f0a0 | n/a |
| C:/Users/neelj/nba-harness-h99/docs/evidence/tracking/specs/S431_spec.md | 16508 | c71cceab5443ea3189900d1347769408cc98e2fda28c41e337e9c95e7038a83e | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/execution/venue_time.py | 1972 | fbbe778f90ae1c70024dd97d9d5f49d66c8ea962e376dc0cb2ec5c22afc830f3 | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/ingame/observation_support_census.py | 17586 | fed126cb92e4684d5e80feb3d1acf885e73d833c88ff29cddb24b374283babda | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/ingame/observation_support_phases.py | 5498 | eca82038e9cd863894733dbfeaa9546702c04f9e5e853ab2125b7d08189c5b2c | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census.py | 14680 | 4f759dd027833b268ba232766a890a9897281b73dfe0c0d3ff2ea97d1ee88aca | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census_1b.py | 5476 | 3ab7cb609209036be65ebebe63a0ae55fd15dcead54cb5bd80c0f0e1ba5df08b | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census_1c.py | 3952 | 8723313e631ad3f4e1839db404e9c6e4023e811d667b78badc19dc0306654302 | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census_1d.py | 1963 | 95774edc01d6626544014288208a11da66e07eb1a3cb11055bd0630bae64ad70 | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census_1e.py | 1462 | 6beb51a28e80d0cc12e746434078623ee3882a287a2aab3fe492b7fa67033e39 | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census_1f.py | 2635 | a9339837ae168a7c1b9fb30ea019abc5c68d5b97a4eac33be1fbfc286bc7c6df | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census_1g.py | 3141 | ab51662da3fa877362ca000cb94a84f760202295590aa62191d1c08c9e73b1f2 | n/a |
| C:/Users/neelj/nba-harness-h99/tests/platformkit/ingame/test_observation_support_census_1j.py | 2759 | cc30ce6db0feb49ed137919a44fbbb4a0eaee96b993dd688a36b30f717bc99ec | n/a |
| C:/Users/neelj/nba-harness-h99/docs/evidence/harness/S446_PROPOSAL_focus_profile_2026-09-24.md | 5634 | 7c201a7339cd3a758d9219dfd4a94c2a967f698a6985f8ce79c6dee2ba78725b | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/ingame/capture_scheduler.py | 21843 | 1517de7383facfc8607be6ecbf3f376c331eeea208f3a001b3814bc133c2e5c4 | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/ingame/forward_capture_profile.json | 151 | 72f798f22269d6a3a74a25313d5743ee57e00732920b1d546b20d1272f046c46 | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/ingame/local_capture_runner.py | 17989 | b67b59ac799f259c61b5b9a4cab99340276717463a605b3b6b6ec11f5d8e834d | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/ingame/local_capture_limiter.py | 4064 | 74863878bca743e92b093b174386ff1f478e699f9c1fad16ab15ac0e89a4b7c2 | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/ingame/local_state_capture_sources.py | 20336 | c17bbb2e1f27c7f1ce09c97da6e954e7c93cea11e51448cff511b00978b83716 | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/execution/markout_causal.py | 14682 | 99c0069b11b297aac505c73da9a884aea96155803e01c632890fb5944dffec09 | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/execution/fill_realism_markout.py | 4547 | bd825edbc49b09e89bbb1dc56f8c807b294a1c02a75f5aaf6c61442332fefb0e | n/a |
| C:/Users/neelj/nba-harness-h99/scripts/platformkit/execution/microstructure_licence.py | 15385 | 0ea0b806a03b6d765a6b207fe5fea37eacc1e55f3e9a4fdc37a3c9c4cbe4fcf5 | n/a |

## FIX 1d (AMENDMENT 3) -- applied items

Round 3 codex sol REJECT (three blockers).

| Item | Change | Test(s) |
|---|---|---|
| (a) | `support()` (observation_support_phases.py) now tracks `max_silent_span_s`, the max continuous silent span (a gap minus the tick each receipt covers), separate from the raw `max_receipt_gap_s`; `_game()`'s `covered` check compares `max_silent_span_s` to the tick instead of the raw gap, so a receipt every 10 s with a 5 s tick (5 s silent spans) is covered | `test_post_final_ten_second_spacing_covered` (1d) |
| (b) | tracked STEP 2 proposal (and its gitignored twin) performs the concurrent-focus check with the verifier's worked example -- 12 concurrent games, 24 req/tick (4.8 req/s) required, 6 req/tick (1.2 req/s) allocated, fits=FALSE, marked INFEASIBLE / UNRESOLVED; nothing adopted (superseded by FIX 1e's market-count correction below) | see Step 2 section above |
| (c) | `audit()`: per-day/per-sport/per-channel row counters are seeded with explicit zeros for `rows`, `accepted`, `duplicate_receipt`, `out_of_order`, `refused_schema_or_time` for both shard dates, and `coverage_summary` always emits all four categories (`covered`/`partial`/`uncovered`/`unresolved`) with explicit zeros | `test_dense_zero_denominators_all_shards_missing` (1d) |

## FIX 1e (AMENDMENT 4) -- applied items

Verdict on the FIX 1d candidate (`_verdict_s446_1e.md`, this worktree): REJECT
-- one BLOCKING, one CORRECTION.

| Finding | Fix |
|---|---|
| BLOCKING: concurrent-focus math undercounted demand and overstated allocation. Verdict repro: `games/hour=2, hours=6, markets/game=2, tick=5, ceiling=3, focus%=45` -> `concurrent_games=12, required_per_tick=24, required_rps=4.8, allocated_per_tick=6, allocated_rps=1.2, fits=False`; the rejected text had divided demand by the tick as one request per GAME rather than per market, and multiplied the ceiling by the focus fraction directly, so both the required and allocated figures it printed were wrong | `capture_scheduler.py` admits only two-market games (:116) and focuses every market ticker of every admitted game each tick (:158, :195), so `required_requests_per_tick = concurrent_games(12) * markets_per_game(2) = 24`, `required_req_per_s = 24/5 = 4.8`; its own integer budget math (:147, :179) gives `budget_per_tick = floor(3*5) = 15`, `allocated_requests_per_tick = floor(15*45/100) = 6`, `allocated_req_per_s = 6/5 = 1.2`; `fits = 24 <= 6 = FALSE` -- INFEASIBLE / UNRESOLVED retained, nothing adopted. Expressed as a new pure function `concurrent_focus_fit()` in `observation_support_census.py` (module now 258 LOC) with a construct test on these exact inputs (`test_concurrent_focus_fit_counts_markets_not_games`, new file `test_observation_support_census_1e.py`, plus an input-guard test) so the figures cannot drift again. Both the tracked proposal and its gitignored twin are corrected in place; this memo's own repeats at the old lines 177 and 247 are corrected in the Step 2 section and the FIX 1d (b) row above |
| CORRECTION: A9 header promised "Full path" but held repo-relative paths with no Resolution column | Header is now `Full path \| Bytes \| SHA256 \| Resolution`; every path is absolute (`Path.resolve()`); `Resolution = n/a` for every row (no image inputs); identities regenerated at base sha `d6577e1f5`, LF-normalised bytes (`read_bytes().replace(b"\r\n", b"\n")`) |

Test: `python -m pytest tests/platformkit/ingame/test_observation_support_census_1e.py -q -p no:cacheprovider` -> 2 passed.

## FIX 1f (AMENDMENT 5) -- applied items

Verdict on the FIX 1e candidate (`_verdict_s446_1f.md`, this worktree):
REJECT -- three BLOCKING.

| Item | Finding | Fix |
|---|---|---|
| (a) | Book lookup joined only through the schedule's single selected ticker, so a served game's second market ticker was `unserved`. Verifier repro (`_collect` with rows `[('EV-H','EV'),('EV-A','EV')]`, lookup `{'EV-H':'GAME'}`): `accepted=1, unserved=1, refused_schema_or_time=1` | `_collect()` now joins books through `event_ticker == game_id` (`ref_field`), never the schedule's `ticker` alone; `audit()`'s books lookup is keyed by `game_id` (not `ticker`); duplicate/out-of-order state moved to a new `stream_id` (`ticker` for books, `game_key` for state) so it is tracked per market ticker, never merged across a game's two markets. Re-run of the exact repro with the corrected join (`lookup={'EV':'GAME'}`): `accepted=2, unserved=0`. New file `test_observation_support_census_1f.py` (2 tests: the two-market accept case and a per-ticker duplicate/order-independence case). Three pre-existing tests that depended on the old ticker-keyed `_collect` contract (`test_14_first_copy_kept_and_out_of_order_refused` in the main file; `test_future_row_folds_into_refused`, `test_unserved_row_folds_into_refused`, `test_nonbook_row_folds_into_refused`, `test_early_exits_partition_invariant_holds` in `_1c`) were updated to key lookups by `event_ticker`/`game_id` and to force the unserved case via a mismatched `event_ticker` instead of a mismatched `ticker`; no assertion's expected outcome changed |
| (b) | The rejected round's demand/allocation figures remained in the memo (FIX 1e row above), and the accounting still stated four files / 58 cases without the `_1e` file | The two rejected figures are removed from every line of this memo (reworded qualitatively in the FIX 1e row); the top summary and "Executed commands" sections now state six files, 62 cases (41+9+6+2+2+2), and the preflight command lists every test file through `_1f` |
| (c) | A9 rows were stale: recomputed from an earlier base sha rather than the final tree, and not cross-checked against `git show master:<path>`, so a checkout line-ending difference could hide behind a stale number | Every A9 row above is regenerated fresh from the current tree (HEAD `70eac9803`, unmoved) on LF-normalised bytes; the ten rows that also exist in master are additionally compared byte-for-byte (LF-normalised) against `git show master:<path>` and all ten match |

Test: `python -m pytest tests/platformkit/ingame/test_observation_support_census_1f.py -q -p no:cacheprovider` -> 2 passed.

## FIX 1g (AMENDMENT 6) -- applied items

Verdict on the FIX 1f candidate (`_verdict_s446_1g.md`, this worktree):
REJECT -- two BLOCKING, one CORRECTION.

| Item | Finding | Fix |
|---|---|---|
| (a) | `_collect()` merged a game's receipts (both market tickers, both shard dates) in raw file order and handed that list straight to `support()` (observation_support_phases.py:60), which assumes ascending time; identical two-market evidence in a different order changed coverage. Verdict repro (`intervals=[(0,20_000_000)]`, `tick=5_000_000`): input `[(10_000_000,"focus_books"),(0,"focus_books")]` -> `gaps_s=[-10000000]`, `max_silent_span_s=15000000`, `support_seconds.focus=5000000`; reversed input -> `gaps_s=[10000000]`, `max_silent_span_s=5000000`, `support_seconds.focus=10000000`. Reproduced verbatim on this candidate before the fix, byte-for-byte matching the verdict's numbers | `observation_support_census.py`, end of `_collect()` (after the per-ticker duplicate/order validation, before `return result`): each game's aggregated `(instant, class)` list is now sorted in place, `for entries in result.values(): entries.sort()`, so `support()` always receives chronological input regardless of file/ticker interleaving. Re-run of the exact repro with the fix: both orders now return the single, identical result `gaps_s=[10000000]`, `max_silent_span_s=5000000`, `support_seconds.focus=10000000` -- confirmed by direct assertion (`assert r1 == r2`). New file `test_observation_support_census_1g.py`, historical (2 tests at FIX 1g time, later found not to be a real regression and consolidated to one test by FIX 1h -- see below): `test_collect_sorts_two_market_receipts_chronologically` drives the fix through `_collect()` itself with forward/reversed/interleaved two-market JSONL input and asserts an identical sorted list; `test_support_byte_identical_for_reversed_and_interleaved_input` re-runs the verifier's own `support()` repro in three input orders and asserts all three results are equal |
| (b) | The memo claimed every master-side A9 row matched current master, but `master` had moved past the worktree's HEAD (`HEAD=70eac9803` vs `master=113718f55` at verdict time), and `local_state_capture_sources.py` (a must-not-move file) differed | This lane's worktree was fast-forwarded to master before FIX 1g started; per AMENDMENT 6(b), master keeps moving between rounds and re-base is part of the fix, so no commit/checkout is performed here (per the no-commit rail) -- the memo instead records two roles, candidate HEAD (this worktree's own commit) and verification base (whatever `master` resolves to when this lane's checks run), without asserting either divergence or equality as a narrative claim. The must-not-move comparison and every A9 row are regenerated against the verification base as this lane's last edit: `git diff master -- <path>` for all 8 must-not-move files returns empty (byte-identical), and the full A9 cross-check (`git show master:<path>`, LF-normalised) confirms every master-side row matches, including `local_state_capture_sources.py`. Both shas are recorded under their role labels in the Machine line and the A9 header above (see FIX 1h below for the values current at this lane's finish) |
| (c) | `test_observation_support_census_1f.py`'s advertised duplicate/out-of-order test (`test_two_market_duplicate_order_tracked_per_ticker`) had a duplicate on EV-H and a fresh later receipt on EV-A, but no row was actually earlier than an already-accepted instant, so `out_of_order` was asserted `== 0` -- the case it claimed to cover never fired | The `_1f` test now gives EV-H three rows: an accepted receipt at +10s, a duplicate of it, and a third row at +0s (earlier than the already-accepted +10s) which is refused `out_of_order`; EV-A keeps one fresh accepted receipt. Assertion changed to `counts["accepted"] == 2 and counts["duplicate_receipt"] == 1 and counts["out_of_order"] == 1`. Verified: `python -m pytest tests/platformkit/ingame/test_observation_support_census_1f.py -q -p no:cacheprovider` -> 2 passed |

Tests: `python -m pytest tests/platformkit/ingame/test_observation_support_census_1f.py -q -p no:cacheprovider` -> 2 passed;
`_1g` at FIX 1g time (historical) -> 2 passed, see FIX 1h/1i for the current count.
Preflight (all seven test files plus both source modules and both memo files): 9 PASS, 0 FAIL.
Must-not-move: all 8 files byte-identical to the verification-base master (`git diff master -- <path>` empty for each). Candidate HEAD unchanged throughout this lane; no git commit or push performed. See FIX 1h below for the exact shas recorded under each role at this lane's finish.

## FIX 1h (AMENDMENT 7) -- applied items

Verdict on the FIX 1g candidate (`_verdict_s446_1h.md`, this worktree):
REJECT -- one BLOCKING, two CORRECTIONS.

| Item | Finding | Fix |
|---|---|---|
| (a) | `test_observation_support_census_1g.py`'s interleaving regression was not real: `interleaved` was assigned the identical list object/values as `reversed_` in both tests, and the second test sorted its input locally instead of exercising `_collect()`'s own chronological handoff, so the regression could not have caught the AMENDMENT 6(a) defect it claimed to guard | The file is rewritten as one test, `test_collect_and_support_identical_across_real_orderings`: four receipts across the two market tickers (`H0` = EV-H at +0s, `A5` = EV-A at +5s, `H10` = EV-H at +10s, `A15` = EV-A at +15s) in three genuinely different orders -- forward `[H0,A5,H10,A15]`, reversed blocks `[A5,A15,H0,H10]`, interleaved `[A5,H0,A15,H10]` -- asserted pairwise distinct as lists (`forward != reversed_blocks`, `forward != interleaved`, `reversed_blocks != interleaved`). Each order is written to its own JSONL file and passed through the real `_collect()` (no local sort); all three return the identical chronological `[(H0,A5,H10,A15 instants, "focus_books")]` list, which is then fed to `support()` unmodified; all three results are asserted equal, with the concrete values (`gaps_s=[5000000,5000000,5000000]`, `max_silent_span_s=0`, `support_seconds.focus=20000000`) checked explicitly. `python -m pytest tests/platformkit/ingame/test_observation_support_census_1g.py -q -p no:cacheprovider` -> 1 passed |
| (b) | The memo presented candidate HEAD and verification-base master as if their relationship were itself a narrative claim ("advanced again") rather than two independently-read roles | Machine line and A9 header above now read both shas under their role labels only: candidate HEAD `342f8949e71ae2ee34492235fadccad55a71fbcf`, verification base `bd716a5696232a3bf6613380d92aba91b3625c52` (read fresh at this lane's finish); no wording claims divergence or equality as an event, it simply states what each role currently resolves to |
| (c) | The closing accounting (top summary and NOT VERIFIED) undercounted by one fix round: "six" test files / `41+9+6+2+2+2` (=62) contradicted the seven-file count elsewhere | Top summary now says "seven times fixed" and "seven owned test files" (line 3-6); NOT VERIFIED updated to match. This round's own `_1g` figure of 2 was itself still wrong (the file always collects 1 test after item (a) above); round 8 (FIX 1i) caught and corrected that residual miscount to `41+9+6+2+2+2+1` (=63), one `_1g` case |

Tests: `python -m pytest tests/platformkit/ingame/test_observation_support_census_1g.py -q -p no:cacheprovider` -> 1 passed.
Preflight (same nine `--paths` as FIX 1g, `_1g` file content changed): 9 PASS, 0 FAIL.
Must-not-move: `git diff master -- <path>` empty for all 8 files against `336e35357ec8c1a289af4a7e9c4fcccb32db764d`, the sha now held by both roles (candidate HEAD and verification base equal after this lane's fast-forward). A9 table above regenerated as this lane's final edit against that same sha; 11/11 master-side rows MATCH. No git commit or push performed.

## FIX 1i (AMENDMENT 8) -- applied items

Verdict on the FIX 1h candidate (`_verdict_s446_1i.md`, this worktree): REJECT -- one BLOCKING, one NOTE. (a) `_1g` always collected 1 test, not 2; every current-result reference above is corrected to seven files, 63 cases (`41+9+6+2+2+2+1`), one `_1g` case (`1 passed`), with the FIX 1g/1h historical two-test mentions labelled historical. (b) Worktree fast-forwarded onto current master immediately before resubmission; both roles read fresh via `git rev-parse` and recorded equal at `336e35357ec8c1a289af4a7e9c4fcccb32db764d`; A9 regenerated and preflight rerun last (memo-only lane, no `.py` change). `python -m pytest tests/platformkit/ingame/test_observation_support_census_1g.py -q -p no:cacheprovider` -> 1 passed; preflight (same 11 `--paths`) -> 9 PASS, 0 FAIL.

## FIX 1j (AMENDMENT 9) -- applied items

Verdict on the FIX 1i candidate (`_verdict_s446_1j.md`, this worktree): REJECT -- one BLOCKING. `observation_support_census.py:110` inferred a request class from `record_type` (snapshot -> focus_books), but real capture rows carry no `request_class` field at all (a retry charged to `reserve` at `local_capture_runner.py:194` emits a plain snapshot), so the census silently mislabeled it. Verdict repro, reproduced verbatim before the fix: `{'record_type':'snapshot'}` (no field) -> `census_label='focus_books'`; `{'record_type':'snapshot','request_class':'reserve'}` -> refused as `request_class_conflict` (`accepted_by_line_113=False`).

Hunk (`observation_support_census.py`, was lines 109-114): replaced `label = BOOK_CLASSES.get(row["record_type"]); if label is None: ...continue; if row.get("request_class", label) != label: raise ValueError("request_class_conflict")` with: `record_type` only gates nonbook/refused; `label = row.get("request_class")`; a present value outside `CLASSES` raises `invalid_request_class`; a missing value leaves `label = None` and, once the row survives dedup/order, bumps `request_class_unresolved` (a detail counter beside `accepted`, mirroring `nonbook:<type>`) instead of ever defaulting to a book-type label. Hunk (`observation_support_phases.py` `_credit()`, was lines 32-40): a `cls is None` receipt now credits a new `unresolved_class` bucket and never falls into `bulk`; `support_seconds` gained the `unresolved_class` key (additive). Hunk (`observation_support_census.py`, chronological sort): the sort key now handles a `None` label (`"" if pair[1] is None else pair[1]`) since same-instant resolved/unresolved receipts can now co-occur.

After the fix, the exact repro: no-field row -> `[(instant, None)]`, `request_class_unresolved=1`, `accepted=1`, never `focus_books`; explicit `request_class='reserve'` -> `[(instant, 'reserve')]`, `accepted=1`, `request_class_unresolved=0`, no conflict. New regressions (`test_observation_support_census_1j.py`): `test_snapshot_without_request_class_is_unresolved_not_focus_books`, `test_snapshot_with_explicit_reserve_is_reserve`. Existing tests that relied on the old inferred-class behavior were adjusted to state the new rule: `test_06_focus_bulk_silent_and_gaps` (main, CHANGE case 6) and `test_profile_tick_is_read` (main) now pass an explicit `request_class` to exercise the classification mechanism on purpose; `test_14_first_copy_kept_and_out_of_order_refused` (main) now expects `None` labels (dedup/order is orthogonal to classification); `test_snapshot_outside_focus_not_counted_as_focus` (`_1b`) and the `_book()` helper in `_1g` now pass an explicit `request_class="focus_books"` since their concerns (window/ordering) are independent of classification.

CHANGE case 6 is honestly INSUFFICIENT on today's real capture rows: the classification mechanism works when a row carries an explicit `request_class`, but no landed capture row writes that field, so per-class focus/bulk/reserve support is not currently measurable from real data -- only from construct rows that supply the field. NEW GAP (allocated at the next register touch, AMENDMENT 9(b)): add the actual request class to every capture row the books runner writes (additive field, byte-identical rows otherwise, flag-free); adoption is an owner-visible relaunch.

Tests: `python -m pytest tests/platformkit/ingame/test_observation_support_census.py -q -p no:cacheprovider` -> 41 passed; `_1b` -> 9 passed; `_1j` -> 2 passed (all eight files re-run one at a time, 65 total). Preflight (12 `--paths`, adding `_1j`): 9 PASS, 0 FAIL. Must-not-move: all 8 files (including `local_capture_runner.py`) untouched, `git diff master -- <path>` empty. No `.py` file outside `observation_support_census.py`/`observation_support_phases.py` and the row's own test files was edited.

## FIX 1k (AMENDMENT 10) -- applied items

Verdict on the FIX 1j candidate (`_verdict_s446_1k.md`, this worktree): REJECT -- one BLOCKING, two CORRECTIONS. (a) `observation_support_census.py:118` raised `ValueError("invalid_request_class")` on an out-of-`CLASSES` explicit value, caught by the generic handler, which bumped only `refused_schema_or_time` -- the specific reason was lost. Repro before the fix: `request_class="bogus"` -> `{rows:1, refused_schema_or_time:1}`, no `invalid_request_class`. Hunk: replaced the `raise` with `bump("invalid_request_class"); bump("refused_schema_or_time"); continue`, mirroring the `nonbook:<type>` detail-counter pattern. Repro after the fix: `request_class="bogus"` -> `{rows:1, invalid_request_class:1, refused_schema_or_time:1}`. Extended `test_snapshot_with_explicit_reserve_is_reserve` (`_1j`) in place with the bogus-class assertions (no new test; accounting stays 65). (b) `S446_PROPOSAL_focus_profile_2026-09-24.md` (and its gitignored twin, kept byte-identical) called the `test_09_post_final_complete` fixture's 61 rows "accepted focus receipts" and compared them against the 45 percent focus allocation, but those construct rows carry no `request_class`. Renamed them UNCLASSIFIED book receipts and removed the focus-allocation inequality, leaving only the classification-independent B/G rate check, until the NEW GAP (AMENDMENT 9(b)) supplies real request classes. (c) The fast-forward/A9-last rule is AMENDMENT 8(b), not 9(b) (9(b) is the NEW GAP); corrected at the Machine line and the A9 header above.

Tests: `python -m pytest tests/platformkit/ingame/test_observation_support_census_1j.py -q -p no:cacheprovider` -> 2 passed (all eight files re-run one at a time, 65 total, unchanged). Preflight (same 12 `--paths`): 9 PASS, 0 FAIL. Must-not-move: all 8 files untouched. Candidate HEAD and verification base read fresh via `git rev-parse`, equal; A9 regenerated last against that sha.

## FIX 1l (AMENDMENT 11) -- applied items

Verdict on the FIX 1k candidate (`_verdict_s446_1l.md`, this worktree): REJECT -- one BLOCKING, one CORRECTION. (a) `observation_support_phases.py:48` `_credit()` folded every explicit class except `focus_books` into `bulk`, violating CHANGE case 6 / AMENDMENT 9's per-class rule. Repro before the fix: `books=[(0,"reserve")]` over a 10s interval, 5s tick -> `requests_by_class.reserve=1` but `support_seconds.bulk=5000000`. Hunk: the `else` branch's `durations["focus" if cls == "focus_books" else "bulk"] += span` is replaced with `durations["focus" if cls == "focus_books" else cls] += span`; `support_seconds` gained additive `trades`/`discovery`/`reserve` keys beside `focus`/`bulk`/`silent`/`outside_focus`/`unresolved_class`. Repro after the fix: same input -> `support_seconds.reserve=5000000`, `support_seconds.bulk=0`. New regression (`test_observation_support_census_1j.py`): `test_reserve_receipt_credits_reserve_not_bulk` (accounting moves from 65 to 66); `test_06_focus_bulk_silent_and_gaps` (main)'s full `support_seconds` dict assertion updated for the three new keys. (b) The tracked proposal and its gitignored twin (kept byte-identical), in the `observed_book_requests` paragraph, described it as "focus/bulk book receipts per selected ticker"; corrected to "accepted book receipts across all market tickers for each served game," matching AMENDMENT 5(a)'s event_ticker join and the unclassified/multi-class reality after AMENDMENT 9-11.

Tests: `python -m pytest tests/platformkit/ingame/test_observation_support_census_1j.py -q -p no:cacheprovider` -> 3 passed (all eight files re-run one at a time, 66 total). Preflight (same 12 `--paths`): 9 PASS, 0 FAIL. Must-not-move: all 8 files untouched. Candidate HEAD and verification base read fresh via `git rev-parse`, equal; A9 regenerated last against that sha.

## REAL RUN 1 (2026-09-25, orchestrator; owed from the 09-25 stopping place)

Artifacts: `docs/evidence/forward/observation_support/2026-09-22_census.json` and `2026-09-24_census.json`
(the landed module over the books archive root and the state v2 root; `--as-of` = the run instant; counts only,
receipt-time phase bounds, per the module's own NOTICE). Every figure below is copied from the artifacts.

- 2026-09-22 (as_of 2026-09-25T13:46:00Z): scheduled games 3; coverage covered 0 / partial 1 / uncovered 0 / unresolved 2; accepted book rows 9959, of which request_class unresolved 9959 (no landed row carried request_class before S458; adoption = the 09-25 relaunch).
- 2026-09-24 (as_of 2026-09-25T13:46:05Z): scheduled games 4; coverage covered 0 / partial 0 / uncovered 4 / unresolved 0; accepted book rows 5782, of which request_class unresolved 5782 (no landed row carried request_class before S458; adoption = the 09-25 relaunch).

| date | game | book requests | PRE | INN 1-3 | INN 4-6 | INN 7-9 | POST_FINAL |
|---|---|---|---|---|---|---|---|
| 2026-09-22 | KXMLBGAME-26SEP221840MILPHI | 1498 | 0.000 (17 gaps) | 0.753 (880 gaps) | 0.129 (111 gaps) | 0.000 (1 gaps) | 0.000 (1 gaps) |
| 2026-09-22 | KXMLBGAME-26SEP221940MIACHC | 1574 | 0.000 (18 gaps) | 0.716 (962 gaps) | 0.085 (108 gaps) | 0.000 (0 gaps) | 0.000 (0 gaps) |
| 2026-09-22 | KXMLBGAME-26SEP221835TORBAL | 6887 | 0.043 (3003 gaps) | 0.000 (1449 gaps) | 0.000 (1011 gaps) | 0.000 (187 gaps) | n/a (0 gaps) |
| 2026-09-24 | KXMLBGAME-26SEP241435NYMTEX | 1460 | absent | 0.877 (1263 gaps) | 0.058 (70 gaps) | 0.000 (3 gaps) | 0.000 (0 gaps) |
| 2026-09-24 | KXMLBGAME-26SEP241805MILPHI | 1402 | 0.000 (13 gaps) | 0.678 (1203 gaps) | 0.000 (2 gaps) | 0.000 (3 gaps) | 0.000 (0 gaps) |
| 2026-09-24 | KXMLBGAME-26SEP241845CLEBOS | 1450 | 0.000 (15 gaps) | 0.783 (1224 gaps) | 0.048 (49 gaps) | 0.000 (1 gaps) | 0.000 (0 gaps) |
| 2026-09-24 | KXMLBGAME-26SEP241915CINATL | 1470 | 0.000 (16 gaps) | 0.693 (1303 gaps) | 0.000 (3 gaps) | 0.000 (2 gaps) | 0.000 (0 gaps) |

Cells are the phase's fraction of receipt-time duration that lies inside the focus window (start-120 s to start+3600 s),
with the count of observation gaps in that phase. Reading, from the table: no served game on either date has any
in-window observation in innings 7-9 or after the final; innings 4-6 are inside the window for at most a small fraction
of their duration; innings 1-3 are mostly inside the window except TORBAL 2026-09-22, whose state rows never left the
pre phase (the 2026-09-23 qualification memo records the adapter refusal), so every one of its receipts is classified PRE.
This is the S446 gap measured on real nights: the fixed 3600 s close leaves the late regimes unobserved. Adoption of a
different close is the PROPOSAL's owner decision (concurrent_focus_fit is FALSE at the current profile); a row to
adopt a feasible close is allocated separately. Nothing here changes any scheduler, profile, flag or threshold.

## NOT VERIFIED

- No independent verifier has accepted this fix.
- The sandbox verifier's required 41+9+6+2+2+2+1+3 (=66) tests collected but stopped during `tmp_path` setup (no writable temp directory in that sandbox); all eight owned test files were run on the host instead (see "Executed commands" above and the FIX 1l section below).
- No real archive, real served game, network, GPU or pod run was exercised.
- No actual phase clock, provider event-time lag or play boundary was measured; receipt-time phase intervals can differ from actual phase durations.
- No actual post-final market availability or settlement receipt was assured; the closure-evidence rule (AMENDMENT 2(a)) is exercised only on construct fixtures, never on a real receipt stream.
- No full-game or concurrent peak request budget was measured; nonbook attempts, failures and retries cannot be inferred completely from book receipts.
- No adoption, capture restart, profile edit, threshold change or flag change occurred.
- Soccer/tennis normalized status phases are implemented but not separately tested.
- No disk-full, forced-process-kill, directory fsync or concurrent writer was tested; only injected file fsync failure and deterministic atomic replacement were exercised.
- Sizes, quantities, prices, fees and fill behavior are not exercised or computed.
- No Git commit was created; files remain ready for lane_commit.
