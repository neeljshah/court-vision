CLOSED AT LIMIT (prerequisites) -- 3/6 stage receipts, 1/2 connection receipts; labels survive 5/5 routes; stale, mismatched and missing-prerequisite routes refuse without a number

# S313 attempt 3 -- the harness receipt to answer round trip (2026-09-08)

Run locally in worktree `C:/Users/neelj/nba-track-a22`; the resolver reads local text artifacts. Calibration only. Prereg `S313_answers_roundtrip_attempt3_prereg_2026-09-08.md`,
its seal EMBEDDED as its own last line (contract Q1) and committed ALONE as `5b45a5133` BEFORE the first metric: `SEAL sha256
9eb403d5d6ea7c712856a2156592a19754dae9429381aaf7a274dd7eea602c28` over the LF-normalised bytes above that line. Attempts 1, 2 and fix 2b are EXPLORATORY relative to this seal.
**What changed, and only this.** (a) The receipt check, the as-of floor and the `mechanism_effect` envelope build moved out of
`resolver_registry.mechanism_effect` into `receipt_guard.mechanism_envelope`, so the module now FITS master's unchanged 1323 allowance at 1320
lines (from 1330); the allowance itself is master's, synced back by `7455fd81e`, never raised. (b) The answer's `as_of` is now
`min(ledger mtime, the mtime of every artifact the answered rows name)`, so derived freshness can no longer outrun its oldest required input. (c) The reference regex now
recognises any `<path> sha256 <hex>` pair in a row note, not only a `receipt=`/`summary=` labelled one, so R3's S312 spec and S314 receipt are
hash-verified and set its as-of floor too. No ledger row was appended, edited or removed. Nothing under `api/`, `intel/`, `src/`, `kernel/`,
`scripts/team_system/`, `data/`, `data/registry/` or `docs/research/` was touched; no flag flipped; no bar moved; no `RESULTS_LEDGER_SYSTEM.md` write.

| id | row | label required | in `findings[0].verdict` | survived composed answer | numbers equal receipt | as-of emitted |
|---|---|---|---|---|---|---|
| R1 | S296 | NULL | NULL | yes | yes | 2026-09-08T05:44:15.193717+00:00 |
| R2 | S310 | CLOSED AT LIMIT | CLOSED AT LIMIT | yes | yes | 2026-09-08T05:44:16.454257+00:00 |
| R3 | S312 | NOT_TESTABLE | NOT_TESTABLE | yes | n/a, no number; n is present with a null value | 2026-09-08T05:44:16.565142+00:00 |
| R4 | S293 | BEHIND | BEHIND | yes | yes | 2026-09-08T05:44:15.144950+00:00 |
| R5 | out of domain | numeric claim withheld | none (not_supported) | refusal survives | n/a | none, a non-ok envelope carries no as-of |

Labels survive 5 of 5 routes. Number equality was re-checked mechanically -- every decimal and every 3-or-more-digit integer in each composed
answer, the as-of excluded as a machine clock value, was searched for in that route's own receipt file(s): 6, 12 and 8 tokens for R1, R2 and R4,
zero mismatches. Pass 2, from a SECOND fresh consumer process, equals pass 1 route-for-route.
**Bars NOT met, verbatim from the spec ACCEPTANCE RULE.** `6/6 funnel stages AND 2/2 connection entries carry real trace receipts` -- measured 3/6
stages (MODELS, ENGINES, INTELLIGENCE; missing DATA, SIGNALS, PREDICTIONS) and 1/2 connections (CONNECTION 2; missing CONNECTION 1).
`S71's <= 1-red bar is rechecked and ANY remaining red touching this chain BLOCKS FINISHED` -- rechecked this run: 5 failed, 46 passed (W01-W04
WNBA probes, H01 `system_health` missing two envelope fields), so the bar stays red and FINISHED stays BLOCKED. Those three stage receipts,
CONNECTION 1 and the `<= 1` red bar were declared UNREACHABLE in the sealed prereg before any metric was computed: they depend on blocked row S312
(BLOCKED-ON S314 and S315) and on 5 contract reds that pre-exist this row. MET: `100 pct of supported-route answers preserve artifact hash, basis,
n, CI, measured_as_of and verdict EXACTLY`; `every missing, stale, corrupt or unverified fixture REFUSES the numeric claim`; `derived freshness may
never exceed its oldest required input`. The `+0.004` bar is not an input to this row and was not touched.
**Two honest deviations from the sealed prereg.** (1) The prereg's as-of RULE is per-answer but its worked example predicted one shared value for
R1, R2 and R4; the rule is what shipped, so each route is dated by its own oldest input and the predicted value holds for R4 only. (2) The prereg's
pass rule item 7 required R3 to name S312, S314 and S315; the landed ledger row names S312 and S314 but not S315, and no ledger row was edited to
fix that, so the sub-clause is met 2 of 3. R3 still emits no number, carries `n` present with a null value, and names the exact missing prerequisite.
**LIVENESS: OFFLINE VERIFIED / LIVE NOT VERIFIED.** The round trip reproduced from a fresh consumer process; the resident MCP consumer answers from
the main repo tree, which does not carry these ledger rows, and it was not restarted or re-probed in attempt 3.
**Absorbed S290 capability manifest**, carried forward UNCHANGED (`c0aa68b4f3ef7ebf1037b88a0947d0f6b81d287c4aa20eaf1cb6e86fd38323b5`): nba 1814
rows / 563 p_close / tails 25 and 60 (n=85); mlb 39162 / 910 / 1 and 1 (n=2); soccer 25834 joined 16322; tennis 41886 joined 33766. This row builds
no tail-capability answer route, so all four `answer_connection_status` values stay NOT_TESTABLE; raising one would be coverage inflation.
**Tests, each file alone.** `tests/platformkit/test_s313_answers_label_survival.py` -> 11 passed (10 replayed plus the new as-of assertion: the emitted as-of equals the oldest
named input while the ledger is the newer file). `tests/platformkit/test_loc_rail_scope.py` -> 1 passed at master's 1323. `tests/platformkit/mcp_server/test_envelope_contract.py`
-> 46 passed, 5 failed, the binding baseline with no new red. `scripts/platformkit/eval_gate/test_s275_key_explicit_consumers.py` -> 1 passed. Readers of the modules code moved
between: `test_resolver_registry_routing.py` 37 passed, `test_mechanism_effect.py` 20 passed, `test_effect_graph.py` 10 passed. The aggregate ledger readers
`mechanism_ledger_export --check` and `mechanism_survival --check` both still report 291.
**Scan.** Contract Q6 vocabulary and restricted-figure scan over every added byte of all three attempt-3 commits and every file this attempt writes:
0 word hits, 0 figure hits, the patterns assembled from single characters so the scanner never spells a restricted token. Every artifact SHA-256 is
in `S313_attempt3_artifact/sha256sums.txt`, computed over LF-normalised bytes. Two quoted file basenames embed a restricted token; Q6 NOTE exempts verbatim identifiers.
**Ledger line for the lander** (this row does not write `docs/evidence/RESULTS_LEDGER_SYSTEM.md`):
`2026-09-08 | harness-to-answers calibration | S313 | 3/6 stage receipts and 1/2 connection receipts; labels survive 5/5 routes; stale, mismatched and missing-prerequisite routes refuse without a number | CLOSED AT LIMIT`
**Pod reader tests (fix 3c, 2026-09-08).** The census reproduces at 21 direct importers; its 14 `scripts/platformkit/answers/` members each ran on the pod through `pod_run` (route A, one
file per command, Python 3.12.3) in a job root carrying the linked tree `data -> /workspace/nba-ai-system/data`, and again from `origin/master` `0ed7bd4e3` shipped by the same launcher rule.
14/14 gave a count: candidate 148 passed / 4 failed / 82 skipped, master identical FILE FOR FILE, so NO red is candidate-only; the linked tree itself carries no `data/cache/profiles` and no `data/cache/intel_claims`, so the 4 reds and 82 skips remain corpus absence, NOT FIXED here. `S313_attempt3_artifact/pod_reader_tests.md`.
**NOT VERIFIED.** LIVE resident connectivity (no consumer restart against a tree carrying these rows). The DATA, SIGNALS and CONNECTION 1 receipts (absent since attempt 1). The
PREDICTIONS receipt and the S312 result itself (not landed; S312 is BLOCKED-ON S314, whose before-condition fails, and S315, spec only). That any reader outside `mechanism_effect`
consumes these rows (only the two aggregate ledger readers were checked). Mirroring the rows into the other three sport ledgers.
Vocabulary follows contract Q6; automated scan required.
