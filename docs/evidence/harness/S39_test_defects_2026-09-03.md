# S39 -- the three pre-existing per-file test defects, root-caused and fixed

Lane: S39 (main repo, no worktree). Register row S39, evidence
`TEST_BASELINE_2026-09-03.md` at commit `e0eb96e12`. Calibration language only.
Every number below is a measurement taken in this session on the system Py3.10
interpreter the baseline used, one file per process, canonical shape:

```
timeout <cap> python -m pytest <one file> -q -p no:cacheprovider -rfE
```

**Q8 premise check (row is one day old).** Re-measured all three before any work.
All three reproduced exactly as the baseline recorded them; no premise falsified.
The register's own hedge -- "likely the S32 bridge" for the capture loop -- IS
falsified: see defect 1.

---

## Verdicts

| # | file | before | after | root cause | verdict |
|---|---|---|---|---|---|
| 1 | `tests/platformkit/ingame/test_inplay_capture_loop.py` | 51 passed / 10 failed | 61 passed / 0 failed | STALE TEST -- maker lifecycle landed 2026-09-01, test kept the taker contract | FIXED |
| 2 | `tests/platformkit/test_scoreboard.py` | 24 passed / 2 failed | 26 passed / 0 failed | STALE TEST (duplicate suite) + drifted module docstring | FIXED |
| 3 | `tests/platformkit/mcp_server/test_server.py` | 7 passed / 1 failed, 138 s | 8 passed / 0 failed, 3.2-4.2 s | FLAKY-SLOW, not a hang: 15 stale claims-index sidecars forced a 2.87 GB residual full scan per ask | FIXED (data/ops) |

---

## Defect 1 -- capture loop: 10 failures, one decision contract

**Symptom.** `test_one_cycle_captures_pair_with_prior_and_paper_decides` failed
`assert (False is True)` on `g["bet"]`; nine more tests that each assert "the
decision path is unaffected by X" fell with it. One defect, ten failures, as the
baseline suspected.

**NOT the S32 series-twin mis-bind.** Measured, not assumed: the failing cycle
pairs correctly. The heartbeat game row read
`paired=true, p0_source="PRIOR", model_prob=0.65, devigged_price=0.53999...` --
every pairing field is right. The failing field is the DECISION, downstream of
`_scan_live_by_legs`, and the fixture injects `live_state_fn` directly so the
leg-scan bridge is never even entered. The S32 PROPOSED guard (FIX B) is
therefore NOT implemented here: it addresses a different code path and would not
have moved any of these ten. S32 stays open on its own row.

**Root cause.** Commit `a1fb821c6` (2026-09-01, "Wire paper maker lifecycle into
day-trader") changed `inplay_daytrader.on_tick` so an ENTER no longer crosses the
book on the deciding tick: it submits a resting maker quote and fills on a later
cross or TTL cancel. The row now reads
`bet=False, action="resting", reason="maker_quote_submitted"`
(`inplay_daytrader_maker.py:144`). That commit shipped its own coverage
(`tests/platformkit/ingame/test_maker_only_wiring.py`, 12 tests, GREEN in the
baseline) and `test_inplay_daytrader.py` (41 tests, GREEN, asserts
`maker_quote_submitted` at four sites) -- but it did not touch
`test_inplay_capture_loop.py`, whose fixtures still encoded the pre-maker taker
contract. The CODE is current and covered; the TEST was stale.

**Fix (test-only, no production code touched).** One helper,
`_assert_enter_decision(g)`, holds the ENTER contract in a single place; all ten
sites route through it. The assertion is STRICTLY STRONGER than what it replaced:
it now pins `action` and `reason` as well as `bet` and `model_prob`, so a silent
future flip back to a taker enter fails loudly instead of passing. No assert was
weakened, no threshold moved, no production module edited. The main test's
`hb["n_bets"] == 1` becomes `== 0` because `n_bets` counts rows where `bet` is
truthy (`inplay_capture_loop.py:700-701`) -- a resting quote has not filled.

**Rerun (this session, MASTER, whole file):** `61 passed in 119.17s`.

---

## Defect 2 -- scoreboard: settled-no-close rows in the settled count

**Symptom.** `test_settled_no_close_excluded_from_clv_count` (`assert 2 == 0`) and
`test_n_settled_counts_only_clv_rows` (`assert 3 == 2`), both asserting that
`n_settled` counts only rows carrying a `clv_pct`.

**Root cause.** Commit `8b297860b` (2026-06-26, "platformkit/scoreboard: n_settled
counts ALL settled rows, not just clv-bearing") deliberately split the two
populations in `scripts/platformkit/pm_trading/scoreboard.py`: `n_settled` and the
flat-unit win/loss record count every `status=='settled'` row so a real settled
bet whose close was never captured cannot vanish from the track record, while
every CLV statistic stays over the narrower `_clv_subset`, and the remainder
surfaces as the new `n_no_close`. That commit updated the module's SIBLING test
(`scripts/platformkit/pm_trading/test_scoreboard.py`, +91 lines, 5 tests) but not
the DUPLICATE suite `tests/platformkit/test_scoreboard.py`, which landed the same
day in the unrelated snapshot commit `b1f55adc6` still carrying the pre-fix
expectations. Two test files, one module, contradictory contracts.

**Is it an honesty defect?** NO, and this was checked rather than assumed. The
concern would be no-close rows inflating a CLV denominator. They do not:
`pct_beat_close` divides by `n_clv_rows` (scoreboard.py:233), `mean_clv_pct`
averages only true closes, and `flat_unit_clv` averages only decided rows that
carry a close. The real-money gate does not read this file at all --
`realmoney_gate.evaluate` recomputes eligibility from the ledger rows themselves
via `_settled_clv_rows` (realmoney_gate.py:57-62), which requires
`clv_pct is not None`. `GATE_MIN_N` has NO production reader anywhere in
`scripts/`, `tests/` or `api/` (grepped): it is an advisory constant plus one
test that pins its value.

**What WAS wrong beyond the tests: the module docstring drifted.** Two lines still
described the pre-fix semantics -- the field shape said `n_settled` is the "count
of settled rows with clv_pct", and the gate block said `GATE_MIN_N = 500 settled
rows with clv_pct required`. Read together with the current code those two lines
invite exactly the mistake the row feared: a future gate author reading the
docstring would compare `n_settled` (which now includes no-close rows) against a
threshold documented as a CLV-sample threshold. That doc drift is fixed.

**Fix.**
- `tests/platformkit/test_scoreboard.py`: both tests rewritten to the current
  contract. Neither is weakened -- each now pins the whole honest split
  (`n_settled` / `n_clv` / `n_no_close` / `n_true_close` / `n_proxy_close`) and
  the CLV denominator, where before each pinned a single count.
- `scripts/platformkit/pm_trading/scoreboard.py`: docstring only. `n_settled`
  documented as ALL settled rows; `n_no_close` added to the documented field
  shape; the `GATE_MIN_N` line states that the 500 applies to the
  `n_clv`/`n_true_close` sample and NOT to `n_settled`, and records that
  `realmoney_gate` recomputes from the ledger so this file cannot spoof it.
  **No constant changed value.** `GATE_MIN_N` is still 500, `GATE_CLV_LB_PCT`
  still 0.0, `GATE_PCT_BEAT_CLOSE` still 55.0, `MIN_CLV_N` still 8 (B10/Q3).
  File LOC 279 -> 283, still under the 300 rail; ASCII verified.

**Rerun (this session, MASTER):** `tests/platformkit/test_scoreboard.py`
`26 passed in 0.88s`; sibling `scripts/platformkit/pm_trading/test_scoreboard.py`
`5 passed in 1.10s`.

---

## Defect 3 -- MCP server: flaky-slow, not a hang

**Three runs of the single test, as instructed** (canonical shape, one file per
process, nothing else writing the repo):

| run | result | wall |
|---|---|---|
| 1 | FAILED `subprocess.TimeoutExpired ... 120 seconds` | 121.76 s |
| 2 | PASSED | 73.66 s |
| 3 | FAILED `subprocess.TimeoutExpired ... 120 seconds` | 121.95 s |

2 of 3 failed. **Not a hang.** The server subprocess DOES answer: driven directly
outside pytest it returned a complete, well-formed envelope in 88.1 s
(`status="ok"`, `category="verified_claims"`, `claim_id="mlb_profile_framing_2025"`,
a five-row ranking excerpt). The test's own 120 s `subprocess.run` timeout simply
straddles the true cost, so the outcome is decided by box noise.

**Root cause (profiled, not guessed).** `cProfile` on the `ask` handler in-process,
same arguments: 65.195 s total, of which
`intel_query/ask.py:191 load_verified_claims` is 50.126 s cumulative and
`json/decoder.py raw_decode` is 38.190 s across 203,876 parsed lines.
`ask()` has a fast path -- `ask_index.index_top_n_lookup` reads a
`<family>.index.jsonl` sidecar and skips the whole-store load -- and falls back to
`load_verified_claims(stale_pairs)` for any family whose index is missing or
stale (`ask.py:305-318`). Measured on this box: **100 claim source pairs, 82 with
a fresh index, 18 stale, totalling 2,870.7 MB** -- dominated by
`nba_player_box_rate.jsonl` at 2,820.3 MB. `mlb_profile_claims.jsonl` (0.9 MB),
the store that actually answers this query, was itself stale, so the query missed
the fast path and paid the full residual scan of all 18. The claims stores live
under `data/cache/` (gitignored, local-only), so this is a LOCAL corpus-state
defect, not a code regression: the module is behaving exactly as designed on an
index that nothing had rebuilt.

**Fix: the wait, not the timeout.** The test's 120 s timeout is UNCHANGED. The
sidecar indexes were rebuilt with the module's own CLI
(`python -m scripts.platformkit.intel_query.claims_index --family <f>`), 15
families rebuilt in under 1 second of total build time. Stale count 18 -> 2. No
code was edited for this defect.

**Rerun, this session, MASTER.** Rebuilding `mlb_profile_claims` alone took the
single test from 73.66 s to **2.18 s**. Whole file, three consecutive runs:
`8 passed in 4.15s`, `8 passed in 3.25s`, `8 passed in 3.16s` -- against the
baseline's `7 passed / 1 failed in 138s`. Sibling
`tests/platformkit/mcp_server/test_artifact_tools.py`: `5 passed in 0.41s`.

---

## Files changed

| path | change | committed |
|---|---|---|
| `tests/platformkit/ingame/test_inplay_capture_loop.py` | `_assert_enter_decision` helper + 10 call sites | yes |
| `tests/platformkit/test_scoreboard.py` | 2 stale tests rewritten to the current contract | yes |
| `scripts/platformkit/pm_trading/scoreboard.py` | docstring only; no constant, no logic | yes |
| `data/cache/intel_claims/*.index.jsonl` (15) | rebuilt sidecars | NO -- `data/` is gitignored by design |

No production logic was changed by this lane. `inplay_capture_loop.py` was NOT
edited: its root cause was a stale test, so the additive-edit permission the row
granted was not needed.

---

## NEW GAPs (filed, not fixed here -- outside the S39 ACCEPTANCE RULE)

- `NEW GAP:` nothing rebuilds the claims-index sidecars. No daemon, scheduler or
  producer in `scripts/` references `claims_index` (grepped); the 18 stale
  families had simply drifted since their last manual build, and will drift again
  the moment a producer rewrites a store. Every stale family costs the ask surface
  a full-store scan.
- `NEW GAP:` `claims_index.discover_families` claims in its own docstring to use
  "the same pairing rule as ask.py's discover_claim_source_pairs" but does not
  honour `ask.py`'s `_LEGACY_VALIDATION_OVERRIDES`. `gate_verdict_claims` is
  therefore visible to `ask()` yet permanently unindexable
  (`IndexError_: validation summary not found`), so it can never leave the
  residual full-scan path.
- `NEW GAP:` the residual scans at `ask.py:318` and `ask.py:344` pass no
  `max_lines_per_file`, while the general path at `ask.py:348` passes
  `_QUERY_SURFACE_MAX_LINES`. The uncapped path is the one that reads the 2.82 GB
  store. Capping it would change ANSWERS (a truncated read can hide a VERIFIED
  claim and turn an `ok` into a `no_data`), so it is a decision for the module's
  owner, not a test-repair edit.
- `NEW GAP:` two test files cover
  `scripts.platformkit.pm_trading.scoreboard` -- `tests/platformkit/test_scoreboard.py`
  (26 tests) and `scripts/platformkit/pm_trading/test_scoreboard.py` (5 tests).
  The split is exactly why the contract change of `8b297860b` reached one and not
  the other. Consolidating them is a separate decision.
- `NEW GAP:` `test_inplay_capture_loop.py:42` carries a pre-existing fixture
  comment using the word this program's Q6 language rail bans. Left untouched to
  keep this diff to the defect; a Q6 sweep over test-source comments is its own row.

---

## NOT VERIFIED

- Whether defect 3 recurs. Three post-fix runs were green in 3.2-4.2 s, which is
  a wide margin under the 120 s timeout, but the index will go stale again the
  moment a producer rewrites a store (see the first NEW GAP). No producer was run
  to force that and observe the regression.
- `nba_player_box_rate` (2,820.3 MB) was deliberately NOT reindexed -- the build
  cost was not measured and the store is not what answers these tests. Any ask
  query that misses the sidecar still pays a scan of it.
- Defect 1's fix is asserted against the maker contract as the day-trader
  implements it TODAY. Whether the resting quote later fills correctly is
  `test_maker_only_wiring.py`'s territory (12 tests, GREEN); this lane did not
  re-derive that behaviour.
- The seven `scripts/platformkit/eval_gate/` collection-time import failures
  (baseline Group 1) are untouched by this lane. They are a separate defect class
  (invocation shape) and were not in the S39 row.
- No claim here about the `basketball_ai` conda env; every measurement is on the
  system Py3.10 interpreter the baseline used.
- Cross-file interference was not tested: each file ran in a fresh interpreter,
  one file per process, as the baseline did.
