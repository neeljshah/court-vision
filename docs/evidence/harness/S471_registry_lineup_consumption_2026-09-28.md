# S471 registry lineup consumption: FIX 1e

AMENDMENT 5(a)-(c) corrections implemented; the exact test-diff checker
uses a pinned base and permits the five specified blank-line removals.
Prior FIX 1c: 12/12 new construct cases and 2/2 invariants passed.
Construct evidence only.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h124.
No real archive, network, pod, measured corpus, real night or flag change.

## Identity and scope

HEAD df7367408e327fcbbf2151235883940fc99fd4d8.
master df7367408e327fcbbf2151235883940fc99fd4d8.
EQUAL; git diff verified that no S471-owned path drifted from
9140b77208cd1fdd9e2691285368510ad2383fad to this master.
The spec copy includes every amendment through AMENDMENT 5.
Changes are restricted to S471 owned files in this worktree.
The supplied spec change belongs to the orchestrator and was not edited here.
Both old seals, the S467 producer and capture defaults remain unchanged.
The implementation modules edited in FIX 1c are registry_scorer_e_ticks.py,
registry_scorer_e_config.py and registry_adapters_lineup.py.
Other candidate implementation changes from FIX 1b are retained.

## FIX 1b history

The prior lane added the lineup route, declared count bounds, newest-touching-
commit floor, exact fractional config comparisons, spanning-run supersession,
stale-first census and construct perturbations.
The verifier confirmed the S460 table, import closure, old seals, causal-prefix
import, date parser checks and existing-test diff restrictions.
Those behaviors remain. FIX 1c supersedes the prior shape requirements,
census population and blocked-invariant wording.

## FIX 1c

Before module edits, the new regression file reported:
"21 failed, 19 passed in 2.27s".
After the implementation corrections: "40 passed in 1.24s".
Read-only review then reproduced "KeyError: 'mid'" for a selection without mid;
a further regression now preserves an empty fit population. Final count: 41.

| Finding | Reproduction before correction | Change and passing evidence |
|---|---|---|
| Sol 1; Opus 10; 3(a) population | States 5/10 s, first book 7 s: one fit row; "assert 2 == 1" for pitcher-hand buckets. | Resolve mid first, discard pre-book ticks before other adapters/censuses. Regression asserts one row/one bucket; case 14 spies on fit. |
| Sol 2; Opus 3; 3(b) invariant | Fixture 4608 bytes, E [None, None, None]; six blocks encode three times; microstructure count_refused three times, omitted from census. | Exact size/full hash, outcome Counter and both E vectors asserted. Census records refusal once, only eligible ticks. Fixture bytes preserved. |
| Sol 3; Opus 11; 3(c) filename | Filename day 26, policy day 29. | Renamed BLOCK_CONFIG_E_2026-09-29.json; references updated; final seals below. |
| Sol 4; 3(d) authority | Original CHANGE named one test; cases 10-14 lived in another. | AMENDMENT 3(d) authorizes all three files; case map below. |
| Sol 5; Opus 12; 3(e) scratch | Test-Path .s471_tmp returned False at lane start. | Already removed by orchestrator; all fixture scratch uses system temp, no recreation. |
| Sol 6; Opus 7; 3(j) memo | Replaced invariant 2 still called BLOCKED; stale master SHA. | Invariant HOLDS; full current SHAs above; S480 and NOT VERIFIED below. |
| Opus 1; 3(f) sibling guard | Bytes-reading git_committed double: "PermissionError: denied". | Committed-sibling call moved inside OSError guard; exact block_config_sibling_unreadable regression passes. |
| Opus 2; 3(g) shape | pitcher_hand appearances=None raised lineup_shape_invalid; malformed refused used same undeclared name. | Block-scoped checks; pitcher-hand ignores appearances and rejects malformed refused as pitcher_hand_invalid. |
| Opus 4; 3(h) cases 11/12 | Source probe: substring matches; no exact exception-string assert. | Anchored matches, exact strings and exact receipt-refusal count. |
| Opus 5; 3(h) case 6 | Source asserted earlier load, no later score refusal. | Intervening construct night through score() asserts block_config_not_effective for later seal. |
| Opus 6; 3(h) case 8 | No asdict assertion against S460 source. | git show 19213365f reads source in subprocess; all twelve non-pitcher_hand entries compared. |
| Opus 8; 3(i) sibling | Present list raised block_absent:mlb_lineup. | Present non-dict sibling refuses block_config_sibling_invalid, no model_not_reconstructible. |
| Opus 9; 3(i) slots | All-invalid side "DID NOT RAISE"; undeclared keys counted three slots rather than one. | Only serialized keys 1-9 with positive exact-int ids count; nonempty zero-resolved sides refuse lineup_shape_invalid. |
| Opus 12; 3(i) hashes/paths | Eight-hex checks; cwd-relative seal paths. | Full LF hashes; paths resolve from Path(__file__) repository root. |

Empty sides retain current_lineup_absent. Old regression expectations changed
only where AMENDMENT 3 superseded them. Mid refusal diagnostics are retained;
_stream.mid_ineligible counts discarded ticks. Every field census population
is fit-eligible only. Case 2 asserts exact old-to-current census differences;
all other output matches except block_config_sha256. Snapshot bytes unchanged.
The unused committed_at parameter and confirmed behaviors were not altered.

## FIX 1d

Only AMENDMENT 4(a)-(c) is changed in this round.

| Finding | Reproduction before correction | Correction and regression |
|---|---|---|
| Blocking 1; 4(a) exact existing-test diff | git diff showed replaced direct calls and semicolon-combined git_committed lines. The stricter invariant failed at index 101; initial main suite: "4 failed, 1 passed". Omitted callback: "TypeError: load_block_config() missing 1 required keyword-only argument: 'committed_at'". | Restored original direct calls and git_committed lines; added separate adjacent monkeypatch lines. The loader defaults an omitted callback to None and refuses block_config_not_prospective after existing validation. Exact source comparison permits only the specified transformations; mutation regressions reject combined statements, direct-call rewrites and arbitrary mentions. |
| Blocking 2; 4(b) declared vocabulary | pitcher_hand with mlb_lineup=[1,2]: "refusal=block_config_sibling_invalid", "is_declared=False". Case 8 failed for all three blocks. | Consumer contracts extend imported S467 vocabularies with sibling, absent, causal and stale refusals; appearance_history also declares count_refused. Case 8 asserts exact contracts and membership for every producer refusal plus adversarial consumer inputs. Producer bytes and route behavior stay unchanged. Manifest, identity and seal are regenerated last. |
| Correction 3; 4(c) memo | Memo held HEAD a5cbdb08307a565a2edd5af90b699864fe6d8d7f and master ece12b9b1bbe980c68fd413926146813ea3cb2c3; final line was "SHA: NOT CREATED (sandbox); files ready for lane_commit". The memo regression failed on the stale identity. | Renamed memo to the landing date, refreshed full base SHAs and comparison, placed SHA statement before terminal NOT VERIFIED. Regression checks current base and terminal list. |

The five adjacent additions make the original 300-line scorer test 305 lines.
Resolving this conflicts with the no-removals rule; clarification is pending.
FIX 1d: all 14 per-file suites pass (214 tests), including main S471 5/5
and regressions 46/46. New construct cases pass 12/12; invariants hold 2/2.
The exact-diff invariant and all three vocabulary case-8 runs now pass.
CLI --help exits 0. Seal self-check passes 9/9. Preflight is 8/9: only loc
fails, reporting 305 lines. No exemption or preflight bypass was used.
The 305-line file preserves all original lines and adds only the five required
adjacent monkeypatch lines. Resolving the conflicting cap needs clarification.

## FIX 1e

Only AMENDMENT 5(a)-(c) is changed in this round. The generic module-edit
instruction is narrowed by this amendment to the owned checker/test modules;
no sealed implementation module changes and no reseal are authorized.

| Finding | Reproduction before correction | Correction and regression |
|---|---|---|
| Sol blocking 1; Opus correction 2; 5(a) line cap | "physical lines: 305"; "LOC reproduction: (False, 'tests/platformkit/execution/test_registry_scorer_e.py=305', ...)". | Removed exactly five base blank lines, keeping all original nonblank lines and all five adjacent additions. Checker permits exactly five whitespace-only removals in that file alone. Constructs cover zero/four/five/six removals across all six paths and reject nonblank removal and added lines. |
| Opus blocking 1; 5(b) moving ref | "POST-LANDING FAIL" for all five execution test files with current bytes as both base and candidate. | Invariant reads 19213365f:path. A git double makes master return landed bytes; the full invariant passes with the pinned reads and fails under a moving-master mutation. The unchanged current/current negative control still refuses for all five paths. |
| Sol correction 2; Opus correction 3; 5(c) memo | "STALE MEMO FAIL: live master absent"; memo master was 9140b77208cd1fdd9e2691285368510ad2383fad. | Refreshed full HEAD/master SHAs and equality above; git diff confirms no S471-owned path drift. NOT VERIFIED remains terminal. |

New regression file run before correction: "3 failed, 35 passed in 1.70s".
After checker correction and blank removals: "38 passed in 2.19s".
The raw seal hash is asserted in test_amendment5_seal_bytes_unchanged and
matches the pre-edit raw SHA256 below; the file was never written.
FIX 1d's LOC conflict and its pending clarification are historical; AMENDMENT
5(a) resolves them without a LOC exemption or preflight modification.

## FIX 1f

Refreshed the recorded base SHAs after verifying no committed drift across
all 18 S471-owned paths. The memo regression checks only the recorded
40-hex SHAs and their equality statement, with no live git lookup, and
requires NOT VERIFIED to remain the final section. Implementation and
seal bytes are unchanged.

## Case map

| Cases | Owned test file |
|---|---|
| Invariants 1-2; cases 3-9 | tests/platformkit/execution/test_registry_scorer_e_s471.py |
| Cases 10-14; each new block and flag-off comparison | tests/platformkit/execution/test_registry_scorer_e_s471_1b.py |
| Shape, census, timestamps, sibling and missing-mid regressions | tests/platformkit/execution/test_registry_scorer_e_s471_regressions.py |

Case 10 reads new ids from the manifest, scores five prior construct nights
and one target, asserts varying delta above 0.05 and constant delta at most 1e-9.
The echo control gives [0.0, 0.0] and fails the same predicate.
New count rationales remain NOT PROFILED: lineup completeness, appearance
depth and pitcher L/R indicator. Identities are not coefficients.

## Landed S460 arm E is never numeric (owned by S480)

Discovered 2026-09-28 by the S471 fix lane; owned by S480.
The landed S460 microstructure adapter converts counts to Decimal while
strict_count requires exact built-in int. With microstructure required,
arm E cannot produce a numeric value on that path.
S471 preserves this behavior. AMENDMENT 2 replaces invariant 2: six blocks
encode, microstructure refuses count_refused, and old and current E vectors
are [None, None, None]. Invariant 2 HOLDS as replaced.
Construct perturbation cases select their own blocks and remain separate.
Fixture: tests/platformkit/execution/fixtures/s471_case2_s460_snapshot.json.
4608 bytes; SHA256 a7d08a21d541cc6182e6dc572f4f0b0ec5601627f02eb76021216ae4e8ac4031.
The old-source fixture stays byte-identical; FIX 1c read no archive.

## Seals and floor

Old BLOCK_CONFIG_E_2026-09-25.json LF hash:
959ca04e325596334dc9120e509e4e1d3e6b95d68cab9af54433d0dab5add744.
Old PREREG_E_2026-09-25.json LF hash:
a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0.
Both equal their 19213365f blobs.
SUPERSEDED-UNSCORED: the old seal scored no night (orchestrator record).
Real git timestamp rechecked: 2026-09-25T18:07:18-05:00 = 23:07:18Z,
23 hours after effective_from. A matching-identity construct refuses
block_config_not_prospective; live identity mismatch retires it first.
Zero scored nights under either seal is the supplied orchestrator record.

New path: docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-29.json.
effective_from: 2026-09-29T00:00:00.000000Z.
implementation_identity: 33f9c433c4b8f11cbf8c3b60329e000b350a51865b6e0a0380d59f735a3ce339.
manifest_hash: 0c623d60115a6c79cc8c22277c5951eb642616dbfd9ea8a5a6cdaf813456d903.
Inner policy SHA256: 98dba026bdc64da79544de3e2decdce148d34420d3e55f309db60a92e46337f3.
Outer LF SHA256: cddcac1128e5318085906ff8fcf818ceb28ec3b07dc9da3c1f83184c4c47d0a9.
The seven-block manifest remains
6a94c03bf7385b63ecb15d3241a5205f99bc711fabfc84a04b2ec012a4447f4b.
The shipped-seal floor probe is one second after effective_from.
FIX 1d performed the final reseal after all sealed files were final.
FIX 1e keeps these seal bytes unchanged, as AMENDMENT 5 requires.
The lander must validate the actual commit time; if landing slips past the
declared instant, AMENDMENT 3(c) requires advancing the date and resealing.
The 30-game floor restarts at effective_from.

## FIX 1d validation

Every pytest invocation used one file:
python -m pytest <file> -q -p no:cacheprovider.
System temp only; no full suite or real-data command.

| Test file | Passed |
|---|---|
| tests/platformkit/execution/test_registry_scorer_e.py | 17 |
| tests/platformkit/execution/test_registry_scorer_e_1d.py | 20 |
| tests/platformkit/execution/test_registry_scorer_e_1e.py | 13 |
| tests/platformkit/execution/test_registry_scorer_e_1f.py | 16 |
| tests/platformkit/execution/test_registry_scorer_e_1g.py | 3 |
| tests/platformkit/execution/test_registry_scorer_e_fit.py | 15 |
| tests/platformkit/ingame/test_feature_registry.py | 16 |
| tests/platformkit/ingame/test_mlb_lineup_registry_adapter.py | 13 |
| tests/platformkit/ingame/test_registry_adapters.py | 21 |
| tests/platformkit/ingame/test_registry_adapters_1d.py | 5 |
| tests/platformkit/ingame/test_registry_adapters_1g.py | 12 |
| tests/platformkit/execution/test_registry_scorer_e_s471.py | 5 |
| tests/platformkit/execution/test_registry_scorer_e_s471_1b.py | 12 |
| tests/platformkit/execution/test_registry_scorer_e_s471_regressions.py | 46 |

214 passed, zero test failures across 14 per-file suites.
registry_scorer_e --help: exit 0; no separate self-check CLI exists.
Seal self-check: 9/9; contract preflight: 8/9 over 18 owned paths.
Only FAIL: loc, test_registry_scorer_e.py=305, from the conflicting rules.

## FIX 1e validation

Each command was python -m pytest <one file> -q -p no:cacheprovider.
All constructs used system temp; no scratch was created in the worktree.

| Test file | Passed |
|---|---|
| tests/platformkit/execution/test_registry_scorer_e.py | 17 |
| tests/platformkit/execution/test_registry_scorer_e_1d.py | 20 |
| tests/platformkit/execution/test_registry_scorer_e_1e.py | 13 |
| tests/platformkit/execution/test_registry_scorer_e_1f.py | 16 |
| tests/platformkit/execution/test_registry_scorer_e_1g.py | 3 |
| tests/platformkit/execution/test_registry_scorer_e_fit.py | 15 |
| tests/platformkit/ingame/test_feature_registry.py | 16 |
| tests/platformkit/ingame/test_mlb_lineup_registry_adapter.py | 13 |
| tests/platformkit/ingame/test_registry_adapters.py | 21 |
| tests/platformkit/ingame/test_registry_adapters_1d.py | 5 |
| tests/platformkit/ingame/test_registry_adapters_1g.py | 12 |
| tests/platformkit/execution/test_registry_scorer_e_s471.py | 5 |
| tests/platformkit/execution/test_registry_scorer_e_s471_1b.py | 38 |
| tests/platformkit/execution/test_registry_scorer_e_s471_regressions.py | 46 |

240 passed across 14 per-file runs. New construct cases: 12/12;
invariants: 2/2. The 26 added regression cases are reported separately
from those acceptance cases. CLI --help: exit 0. Seal self-check: 9/9
(raw hash, ASCII, LF, inner hash, implementation identity, manifest,
version map, effective date/filename, old seals against pinned blobs).
No separate self-check CLI exists. Contract preflight: 9/9 on all 18 owned
paths, with --base master and --spec docs/evidence/tracking/specs/S471_spec.md.
Pinned-base probe: 6/6; all five current/current negative controls refuse.
LOC probe now returns "(True, 'all .py <= 300 LOC', [])".
HEAD/master memo checks pass and NOT VERIFIED is terminal.
Read-only independent checker review found no blocking flaws.

## Disclosures

Sibling configs in another directory are not scanned. Loader refusals occur
before a stream census exists. Forged committer dates remain a limit.
Shared S431 dedup still collapses same-microsecond receipts; config timestamps
retain sub-microsecond fractions. NBA consumption remains deferred.
The source seam remains OFF. Constructs do not establish a corpus result.

## A9 identities (LF hashes; construct inputs have no image resolution)

| Path | Raw bytes | Lines | LF SHA256 |
|---|---|---|---|
| scripts/platformkit/ingame/feature_registry.py | 11141 | 216 | 9366d847147567bfdf2e1cbe7c439ba080e665ba095a7ff0bd83703b10aeb3e9 |
| scripts/platformkit/ingame/registry_adapters.py | 14480 | 299 | 9bc35f4ae049d2707dfb57b4ffae024547d4b1a3f18233d6441b0346bac2a468 |
| scripts/platformkit/ingame/registry_adapters_lineup.py | 9631 | 202 | 6a83ce1c497d2eb0d4b716cb144274f988c71be1f91a3a07f146d318f98ed1f0 |
| scripts/platformkit/execution/registry_scorer_e_ticks.py | 12636 | 235 | fdd163cbf1455fa942ffe207a24819bd847eb746e61a43a7c48cc7c77e9ca0cf |
| scripts/platformkit/execution/registry_scorer_e_config.py | 10568 | 186 | a1cbff0b7ba34e20c6e61c0d66f3331be247446119ea60fc3c962888f09a2ee1 |
| scripts/platformkit/execution/registry_scorer_e.py | 17756 | 297 | 55c75aca523c2803dbc65af06a12d5192b613e284543e72d0e2daf24f6b4cdbd |
| tests/platformkit/execution/test_registry_scorer_e_s471.py | 21058 | 297 | bb456a135bb0bcdf777e5032c4b9387f0bccffb04b29a340c5c4c8a40591de1d |
| tests/platformkit/execution/test_registry_scorer_e_s471_1b.py | 13998 | 276 | 9716ab6525c1cb93f48634970c9465f5d0fcc04323c563c408efac982dd2e18d |
| tests/platformkit/execution/test_registry_scorer_e_s471_regressions.py | 14779 | 296 | 962877ad56a64324bd72ff2cf6c44ee8db37dceea749a1d4d35261c293cd1211 |
| tests/platformkit/execution/fixtures/s471_case2_s460_snapshot.json | 4608 | 1 | a7d08a21d541cc6182e6dc572f4f0b0ec5601627f02eb76021216ae4e8ac4031 |
| tests/platformkit/ingame/test_feature_registry.py | 5713 | 134 | 910abf6ef1d35e00fb6c0aea88fb307bbddb6c11435055327a94751b74294eef |
| tests/platformkit/execution/test_registry_scorer_e.py | 15954 | 300 | 697960f92005368a7f0d6f19a4ee6c52c0976abda835b9f7c415ee6b2ad637ce |
| tests/platformkit/execution/test_registry_scorer_e_1d.py | 12962 | 249 | 050017623a509beba0211373f64cfc1fdee12c406c5a7f13b596d35505ce4c9a |
| tests/platformkit/execution/test_registry_scorer_e_1e.py | 14634 | 274 | 07c3234d4b7c1fb9ad3ebba1ea0784e7963bf4e78ba04ca46799d49d276ec8b3 |
| tests/platformkit/execution/test_registry_scorer_e_1f.py | 12448 | 233 | e6d509f32ec28fde5e4cc0fec7b15a3451e74780a6bc4d7e5d7d0b3466a7861d |
| tests/platformkit/execution/test_registry_scorer_e_1g.py | 4056 | 74 | cd651bc7f0293bb4ad88e9d0aea1f835b2157cb3a4b8ec59d30ddaba63e16c21 |
| docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-29.json | 948 | 32 | cddcac1128e5318085906ff8fcf818ceb28ec3b07dc9da3c1f83184c4c47d0a9 |

SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED

- arm E numeric on a real tick.
- Actual landing commit, new-seal committed_at/git_committed, and prospectivity.
- Any real flag-on capture, corpus/night, scored night or real ledger.
- Post-effective available-game counts, pod runs and live restart/backfill semantics.
- Forged committer dates.
