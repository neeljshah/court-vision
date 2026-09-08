PARTIAL -- 3/6 stage receipts and 1/2 connection receipts. All five asked routes pass and all four labels survive the composed answer verbatim, but the spec bar of 6/6 funnel stages and 2/2 connection entries is NOT reached: DATA (S223 source -> S232 candidate), SIGNALS (S232 -> factory outcome) and CONNECTION 1 still carry no receipt, and PREDICTIONS is a measured NOT_TESTABLE naming prerequisite S312, which is BLOCKED-ON S314.

# S313 attempt 2 -- the harness receipt to answer round trip (2026-09-08)

Run 2026-09-08T05:51Z to 05:58Z UTC, locally in worktree `C:/Users/neelj/nba-track-a22` (S1: no pod compute is needed; the resolver reads local text artifacts).
Attempt 1 (`ace9f953d`) closed NOT_TESTABLE because the S296/S310/S312 receipts were absent. S296 (74bd5ad45), S310 (2a708672e) and S293 (4a41c436e) have since landed; S312 has not.
Calibration only. Vocabulary follows contract Q6; automated scan required.
Prereg `S313_answers_roundtrip_attempt2_prereg_2026-09-08.md`, sealed and committed ALONE as `b44d9bef6` BEFORE the first metric, seal `14905e91bc9ee1490521b4d18d850036ffbb2173c3774f6b77b9025b09359406` (Q1).

**What was built.** Four receipt rows were APPENDED to `domains/basketball_nba/knowledge/validation_ledger.jsonl`, the declared `source_artifact` of the
already-registered `mechanism_effect` category. That is the whole connection: no resolver code was written, no category added, nothing under `api/`, `intel/`,
`src/`, `kernel/`, `data/`, `data/registry/` or `docs/research/` touched, no flag flipped, no bar moved (the +0.004 bar is not an input). Each row quotes its
receipt path, receipt SHA-256, basis, CI and `measured_as_of` inside a `note` the resolver returns verbatim.

| id | row | label required | in `findings[0].verdict` | survived composed answer | numbers equal receipt | citation |
|---|---|---|---|---|---|---|
| R1 | S296 | NULL | NULL | yes | yes | source_artifact + as_of |
| R2 | S310 | CLOSED AT LIMIT | CLOSED AT LIMIT | yes | yes | source_artifact + as_of |
| R3 | S312 | NOT_TESTABLE | NOT_TESTABLE | yes | n/a, no number emitted | source_artifact + as_of |
| R4 | S293 | BEHIND | BEHIND | yes | yes | source_artifact + as_of |
| R5 | out of domain | numeric claim withheld | none | n/a | n/a | registered-hypothesis list |

R5 returned `not_supported` and composed `NOT_SUPPORTED -- ...`; a correct refusal is a pass. Number equality was checked mechanically: every decimal and every
3-or-more-digit integer in each composed answer was searched for in that route's own receipt file. Zero mismatches.

**Stage receipts 3/6 and 1/2, so the bar is NOT met.** CONNECTED stages: MODELS (S296), ENGINES (S310), INTELLIGENCE (composed response); CONNECTION 2 (offline) is the connected CONNECTION entry, never a stage.
Still without a receipt: DATA (the S223 census is not an answer-ready source receipt), SIGNALS (S232 is a dry run, no applied factory outcome), CONNECTION 1
(same blocking fact), PREDICTIONS (S312 has not landed). Full table `S313_attempt2_artifact/route_status.md`; CONNECTION 2's entrypoint string carries the
correction filed by `S313_VERIFY_2026-09-07.md`, re-verified at `scripts/platformkit/mcp_server/tools.py:11-23`.

**S71 red recheck.** Rechecked on master this session: 5 failed, 46 passed (W01-W04, H01) against an unchanged <= 1 bar, so the bar is still red and FINISHED
stays BLOCKED. W01-W04 are WNBA probes; H01 is `system_health` missing two envelope fields -- on the consumer tool surface, though not on the `ask` ->
`mechanism_effect` route this row exercises.

**LIVENESS: OFFLINE VERIFIED / LIVE NOT VERIFIED.** The round trip reproduced byte-identically from a FRESH consumer process and from the documented CLI, but the
resident MCP consumer answers from the main repo tree, whose ledger is `1d32d42fc81edf713baa9dedde2c1117ac504b488047e367d515d65cc69c9478` (85 rows) and does not
carry these rows; its pre-connection envelope is recorded in the artifact directory.

**Absorbed S290 capability manifest**, carried forward UNCHANGED from attempt 1's verifier-reproduced recount (`c0aa68b4f3ef7ebf1037b88a0947d0f6b81d287c4aa20eaf1cb6e86fd38323b5`):
nba 1814 rows / 563 p_close / tails 25 and 60; mlb 39162 / 910 / 1 and 1; soccer 25834 joined 16322; tennis 41886 joined 33766. This row builds no
tail-capability answer route, so all four `answer_connection_status` values stay NOT_TESTABLE -- raising one would be the coverage inflation NON-TAUTOLOGY forbids.

**Test.** `python -m pytest tests/platformkit/test_s313_answers_label_survival.py -q -p no:cacheprovider --confcutdir=tests/platformkit` -> 10 passed.
A5 reader checks after the append, each run alone: `test_mechanism_effect.py` 20 passed, `test_effect_graph.py` 10 passed, `test_resolver_registry_routing.py`
37 passed, `test_loc_rail_scope.py` 1 passed. Both vocabulary scans report 0 hits under contract Q6 and its 2026-09-04 opaque-identifier NOTE; every apparent
substring hit is classified in `S313_attempt2_artifact/scan_report.md`. All ten artifact SHA-256 values are in `S313_attempt2_artifact/sha256sums.txt`, itself
`55fa8871cd3fe80aae87ac4f03013bf801496f6f44f9ec52dadb9c373a87219e`; the ledger after the append is `fc3f7d293fc1b5c5d5c8af0f1fc9c8ac523b3c119430df622093fc619fe15a11`.

**NOT VERIFIED.** LIVE connectivity (the resident MCP consumer has not been restarted against a tree carrying these rows); DATA, SIGNALS and CONNECTION 1
receipts (unchanged since attempt 1, still absent); the S312 teacher-to-student result itself (not landed, hence R3 emits no number); that any reader outside
`mechanism_effect` consumes these rows (only aggregate ledger readers were smoke-checked); mirroring the rows into the other three sport ledgers (not attempted).

**NEW GAPS.** S313-REGISTER-DIGIT-DRIFT: the S293 register row prints the tail log-loss improvement ending 8484 where the memo and its summary JSON
both print 8454; the artifact value was used and the two agree to 1e-14. S313-STALE-LEDGER-DOCSTRING is CLOSED by the corrections below.

**Corrections (fix 2b, 2026-09-08).** RECOUNT: three stage receipts -- MODELS, ENGINES, INTELLIGENCE. CONNECTION 2 is a connection entry that was double-counted as a
stage, so 4/6 becomes 3/6 (line 1, line 26, `route_status.md` line 19); 1/2 connections and every unmet bar are unchanged. REFUSAL: the new module
`scripts/platformkit/answers/receipt_guard.py` validates each receipt-bearing row BEFORE `status=ok` -- an absent artifact, a SHA-256 mismatch, an artifact newer than
the ledger quoting it, or a stated number nothing within 1e-9 reproduces all return `no_data` carrying status, note and source_artifact only; a row that measured nothing
composes no `n`, not a literal 0. Envelopes and manifest regenerated from the same prereg questions; the manifest gained its required `scan`; both readers now say 291.
