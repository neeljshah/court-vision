# S474 scoreboard history - FIX 1c

Acceptance: 18/18 enumerated CONSTRUCT/fixture cases pass.
Prepare-only; no scored comparison.
Items 1-6 implemented; item 7 integration assertions and construct fixtures updated.
Per-file results below are generated from this candidate. No archive was opened by this lane.
Pinned verification base full SHA: 737f3939b01f6dab566ec82fa46cfbc98ae103ce.
Pinned original dispatch base full SHA: 3b351fceb95121ff26daf55d5eccacd5d534a9b4.
Candidate full SHA: NOT CREATED (sandbox); candidate/base identity is reported per file.

## Case table
| Case | Evidence | Result |
|---|---|---|
| 1 | chronology, run snapshot spy, exact CLI refusal reasons and equality | PASS |
| 2 | final at snapshot included; final at boundary unseen until successor | PASS |
| 3 | repeated and conflicting finals on both sides of boundary | PASS |
| 4 | appended future receipts preserve rows/config/result; future_records counted | PASS |
| 5 | tick equals final kept; later tick counted through settlement double | PASS |
| 6 | exact completeness reasons and preservation of other valid rows | PASS |
| 7 | zero-tick and conflict census; missing/malformed fields refuse census_mismatch | PASS |
| 8 | strict schema, canonical chronology, source sanitization, size limits | PASS |
| 9 | all publication states; incomplete pair restored and reproduced with changed mtime | PASS |
| 10 | interrupted publication and retry; rows remain the commit point | PASS |
| 11 | subprocess overlap lock refuses before reads | PASS |
| 12 | pinned-base predict inputs/counters and pre-existing output keys equal | PASS |
| 13 | encoding refusal counters and unsupported sports | PASS |
| 14 | verbatim copied fixture; exact literal; settled census ticks=1 rows=1 | PASS |
| 15 | history last; guarded deadline and failure lifecycle | PASS |
| 16 | own-night validated config handoff and counted refusal | PASS |
| 17 | fresh construct producer/scorer; finite B/C; FITTED then A_ONLY | PASS |
| 18 | produced boundaries enter actual scorer training selection | PASS |

Case 17 construct evidence: `finite B/C asserted by case17`.
Case 14 uses shutil.copyfile on the two orchestrator-provided JSONL fixtures without reserialization.
The exact emitted line is asserted against EXPECTED in test_scoreboard_history.py.

## Per-file validation
| File under tests/platformkit/execution/ | Passed | Failed |
|---|---|---|
| test_scoreboard_history.py | 36 | 0 |
| test_scoreboard_history_store.py | 80 | 0 |
| test_scoreboard_history_e2e.py | 13 | 0 |
| test_ingame_scoreboard.py | 43 | 0 |
| test_ingame_scoreboard_1b.py | 16 | 0 |
| test_ingame_scoreboard_1e.py | 4 | 0 |
| test_ingame_scoreboard_amendment.py | 69 | 0 |
| test_ingame_scoreboard_model_optional.py | 16 | 0 |
| test_ingame_scoreboard_night.py | 31 | 0 |
| test_ingame_scoreboard_night_table.py | 104 | 0 |
| test_ingame_scoreboard_night_e2e.py | 8 | 0 |
| test_paper_night.py | 39 | 0 |
| test_paper_night_steps.py | 56 | 0 |
| test_paper_night_steps_1d.py | 25 | 0 |
| test_paper_night_steps_1e.py | 8 | 0 |
| test_paper_night_scoreboard_step.py | 14 | 0 |
| test_paper_night_scoreboard_step_1c.py | 4 | 0 |
| test_paper_night_scoreboard_step_1d.py | 2 | 0 |
| test_paper_night_scoreboard_step_1e.py | 1 | 0 |
| test_paper_night_inputs.py | 40 | 0 |
| test_paper_night_inputs_e2e.py | 11 | 0 |
| test_paper_night_deadline.py | 20 | 0 |
| test_paper_night_deadline_1b.py | 9 | 0 |
| test_paper_night_deadline_1c.py | 3 | 0 |
| test_paper_night_scratch.py | 19 | 0 |
Total: 671 passed, 0 failed in 25 separate invocations.
Commands: python -m pytest <one file> -q -p no:cacheprovider; never the whole suite.
CLI --help: history producer, scorer, paper night, night selector and amendment generator pass.

## FIX 1a
| Verifier finding | Reproduction before fix | Change and regression |
|---|---|---|
| sol 1 / Opus N1 | lookahead _manifest complete= True | Now corrupt_artifact:schema; exact nested schemas, chronology and current config required. |
| sol 2 | missing served_games returned empty rows; malformed census _nights= None | Both now census_mismatch; explicit integer count, exact keys, canonical timestamps and status consistency. |
| sol 3 / Opus C4 | Memo said 17/18 and fixture absent; old generator ignored | Tracked-path generator, verbatim fixtures, complete tests/inventory and attributed E2 evidence. |
| sol 4 / Opus C3 | Existing tests passed without required reasons/census | Assert exact reasons, future_records, preserved other rows, byte-copy fixture and settled census. |
| sol 5 | SHA followed NOT VERIFIED | SHA precedes final NOT VERIFIED section. |
| Opus B1 | ValueError: amendment_mismatch; identity and default-artifact tests failed | Original seal checked on pinned six blobs; replacement checks live identity; pre-existing receipt keys preserved; new prospective SEALS entry. |
| Opus B2 | ValueError: is not in the subpath | Skip own-night computation for a refused plan; whole-night record remains available. |
| Opus C1 | committed step count 5 == 4; history child_nonzero_exit | Fifth-step assertion and both fake child modules updated. |
| Opus C2 | Incomplete-freezing mutation passed owned tests | New regression fails mutation: assert already_present == published; restore input and assert rows/mtime. |
| Opus C5 | history_refused set but absent from run record | Scoreboard record carries counted refusal and exact reason. |

History owned tests: exact refusal reasons; future_records=4 on construct append; completeness reasons and prior-game row preservation.
Before case-14 fix, both books byte_equal=False and state byte_equal=False; copied targets now equal source bytes.
Orchestrator cleared the scoreboard_step conflict state before FIX 1b; S484 dispatch lines retained.
Generator moved from ignored docs/evidence/harness to nonignored scripts/platformkit/ops/probes; staging also awaits lane_commit.

## FIX 1b
Scope: AMENDMENT 2(a)-(c) only; prior FIX 1a findings above remain unchanged.
Reproduced before edits with python -m pytest <one file> -q -p no:cacheprovider:
- test_ingame_scoreboard_night.py: `16 failed, 14 passed`; `ValueError: seal_index_invalid`.
- test_ingame_scoreboard_night_table.py: `1 failed, 103 passed`; replacement absent at pinned base; `ValueError: seal_index_invalid`.
- test_ingame_scoreboard_night_e2e.py: `7 failed, 1 passed`; `ValueError: seal_index_invalid`.
After: the three per-file totals above include every formerly failing test; none skipped or removed.
SEALS sha256(_json(SEALS)) before: c13a22da05779e3cece5f6d50101c791a6cc9c3b470a095cd51f9af73fb7cd1f.
SEALS sha256(_json(SEALS)) after: 17a5ff7a67ad397cfce1ead6ae17e0e617995a382a1a64d4175c33b5d196fc3e.
Replacement LF SHA256 remains 801af61b2755a99f9d5e238acd59bb1b6cf88212d1cb81b11a576ac32877b7aa; no sealed file changed in FIX 1b.
No new JSON seal or fixture path in FIX 1b; existing LF patterns below cover the candidate.

## A9 inventory (LF-normalised)
Full repository-relative source paths, LF byte counts and SHA256 below; source/JSON/JSONL text resolution.
This inventory measures candidate bytes; tests do not pin mutable-module byte lengths.
| Path | LF bytes | SHA256 | Pinned base comparison |
|---|---|---|---|
| .gitattributes | 1202 | e747b3d00b62b9677772f645bd13ab8bb79ad3c381100f3ba1ee42176101344d | EQUAL |
| docs/evidence/forward/schedules/2026-09-24_maker_forward.json | 1094 | ae92f7cf5369940317db0beb9beb137481c51286c5ab90b368b0329106159c22 | EQUAL |
| docs/evidence/forward/scoreboard/2026-09-24.json | 3443097 | 2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06 | EQUAL |
| docs/evidence/forward/scoreboard/PREREG_2026-09-24.json | 5046 | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | EQUAL |
| docs/evidence/forward/scoreboard/PREREG_2026-09-29.json | 2010 | 6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e | EQUAL |
| docs/evidence/forward/scoreboard/PREREG_2026-09-30.json | 2010 | 801af61b2755a99f9d5e238acd59bb1b6cf88212d1cb81b11a576ac32877b7aa | NEW |
| docs/evidence/tracking/specs/S474_spec.md | 32763 | ee4a03007074e3b31db7983f3dae9371ace817a539a57e67ee04d52b87d0937f | EQUAL |
| scripts/platformkit/execution/ingame_scoreboard.py | 19914 | 12492ba687ff76ad5638613427efd247973544025f2bd1cc9fe2771485a92cf6 | NOT EQUAL |
| scripts/platformkit/execution/ingame_scoreboard_night.py | 8399 | cd19047527cc6ec0a41561fba2e6e5058f34f07f4522013f235f3119bd005ca8 | NOT EQUAL |
| scripts/platformkit/execution/ingame_scoreboard_rules.py | 9871 | 207dab8fff5cd781c001ff89a1d44a4add96fde69cb81e51b005c799afca7351 | NOT EQUAL |
| scripts/platformkit/execution/paper_night.py | 16182 | 9d0410e124d7087f005f1ab87a64ed1855a5ad6d5f1c6ecc3a59486dbad3927b | NOT EQUAL |
| scripts/platformkit/execution/paper_night_budget.json | 1543 | 2a2d66c34003aca18ce86a5ca3d469e37d9948c1352df99363b2ba625bdab9f2 | NOT EQUAL |
| scripts/platformkit/execution/paper_night_deadline.py | 14592 | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | EQUAL |
| scripts/platformkit/execution/paper_night_inputs.py | 9358 | 4163a4ed8217b9eedb67965cb0b49161594b0b1ab7078bc182b110638d159da9 | EQUAL |
| scripts/platformkit/execution/paper_night_lock.py | 1069 | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | EQUAL |
| scripts/platformkit/execution/paper_night_steps.py | 14794 | 898d7fc07ff6157fe4110e96f731562b75568bb13dbf71fa470234748df3f595 | NOT EQUAL |
| scripts/platformkit/execution/scoreboard_history.py | 13751 | b21ccac74b0acaf524d113e54203cdcc889835562fc3de58c931f80c804d50c7 | NEW |
| scripts/platformkit/execution/scoreboard_history_store.py | 14706 | 18c75744234b43bb3988566e8960ef1d7ea2a11e41eeadef67ec4fc52139769f | NEW |
| scripts/platformkit/ingame/baseline_four_arm.py | 17688 | dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2 | EQUAL |
| scripts/platformkit/ingame/baseline_four_arm_eligibility.py | 11759 | d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032 | EQUAL |
| scripts/platformkit/ingame/baseline_four_arm_features.py | 15466 | 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade | EQUAL |
| scripts/platformkit/ops/probes/s474_memo_facts.py | 22543 | e170bfc4cc79df0779678c5ef8ddede8d9170c416280262769486e34b6e3221b | NEW |
| tests/platformkit/execution/fixtures/s465_case1_legacy_snapshot.json | 4274 | 46ecb1acd3217028e74de5fc48c984e276d115b57c0382c8d27edcefb98b52c3 | EQUAL |
| tests/platformkit/execution/fixtures/s470_case1_legacy_snapshot.json | 3312 | 5e3b709129048a9279bddbbb4184025fd282db6e823c7f39298739c585ff8084 | EQUAL |
| tests/platformkit/execution/fixtures/s474_mlb_822842_books.jsonl | 2855 | f747f78a6ffc1f3dd38272eb88ac3dba5ed87e0ffc0fadce83da6ea8a44e9e2c | NEW |
| tests/platformkit/execution/fixtures/s474_mlb_822842_state.jsonl | 1982 | b2b2c50c37281ad2a26f7b5c5adc43845569cdb6343180656857c136494c05a0 | NEW |
| tests/platformkit/execution/test_ingame_scoreboard.py | 18140 | 201ce74642cc080276787c0dfd5b4a556bfdfb5865a1b592bca0735d34743f94 | EQUAL |
| tests/platformkit/execution/test_ingame_scoreboard_1b.py | 13174 | 1ec6abe6e513394fc66494b29885d3e8f27beee7c372a5ba009e59921a33c091 | EQUAL |
| tests/platformkit/execution/test_ingame_scoreboard_1e.py | 5385 | 3c7a9313d81340a1401d0503ac1ff983dad96c3fef5fed5f52cc6f2b4e3ae2fc | EQUAL |
| tests/platformkit/execution/test_ingame_scoreboard_amendment.py | 13956 | 641bb7bf18f6b45a1482cab07c214bccaea5175684a78da2b68358f2b39d8528 | NOT EQUAL |
| tests/platformkit/execution/test_ingame_scoreboard_model_optional.py | 12800 | eef65058598734589f4409b3a0f719733550c4190bc2d8616ccca8b6ec61b7b1 | NOT EQUAL |
| tests/platformkit/execution/test_ingame_scoreboard_night.py | 10445 | 89d7f46375959485b472362c1b9619e11d6f452b1d26392abd2aa44113558db6 | NOT EQUAL |
| tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py | 13221 | e2607ec4c24fa7840b16990dc042b445467997377ad0477db8839257647ba563 | NOT EQUAL |
| tests/platformkit/execution/test_ingame_scoreboard_night_table.py | 10901 | 183ddfc7419ebcdf7cb93c18ea2e5459e9866cf45582504d376a41c83d80269b | NOT EQUAL |
| tests/platformkit/execution/test_paper_night.py | 17309 | 9918eaba99c6fd0a0c2d4344fb6efefd455d3f8cf8a221837f71f88b5838def4 | NOT EQUAL |
| tests/platformkit/execution/test_paper_night_deadline.py | 15815 | 05f1a7f436cc4e256d5e45ade249955b3c0272e3b1888ea5e8ea1770a3f96149 | EQUAL |
| tests/platformkit/execution/test_paper_night_deadline_1b.py | 13769 | fd797e953540e37770d7211c480608b9cc4ea7228887995782851111bdca98e9 | EQUAL |
| tests/platformkit/execution/test_paper_night_deadline_1c.py | 6688 | 7e3c1b52be69925c4722500581ae579cc2d4b5a8e38085d0fac71a9bf723535c | EQUAL |
| tests/platformkit/execution/test_paper_night_inputs.py | 16000 | 139c9eef41df8acb9607f4995738c0f128e11155847620093bf503fb68c89d17 | NOT EQUAL |
| tests/platformkit/execution/test_paper_night_inputs_e2e.py | 15671 | 11cd51a3607f14897762dfad1afb1ba5bd6f9a6a9780c12755a4e43460bc44e9 | NOT EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step.py | 17003 | c2548135217d030641f90e2b17678763091dde141cdf55afd441fdcaf5416907 | NOT EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step_1c.py | 5070 | b6f9505cd08831da2af0b33074d332a9ff9d6c963be74aaf768764682cd2fedb | NOT EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step_1d.py | 2147 | 1c92d1faffd9dc799957da97af29e499da83afbd20419655815629b6e53a473d | EQUAL |
| tests/platformkit/execution/test_paper_night_scoreboard_step_1e.py | 1255 | e8d9c87342324927bf6bffd61725a5908d113ceb70f9efae7ad8cc9b43db719e | EQUAL |
| tests/platformkit/execution/test_paper_night_scratch.py | 6496 | 7063a021782c9b1eb1ae99be75d976ca14c056f5622859b088296b0ea2081517 | EQUAL |
| tests/platformkit/execution/test_paper_night_steps.py | 15701 | 3d87bdf86600a8fe07c13fe0121f85a17eac80dfcc4ebf0e50551005ea97fa93 | NOT EQUAL |
| tests/platformkit/execution/test_paper_night_steps_1d.py | 4511 | b22f9b67dbe2058228f95ab6daeac20076a1a53dc71175f2f33693b733223ff9 | EQUAL |
| tests/platformkit/execution/test_paper_night_steps_1e.py | 2348 | 330150ab367f207701613d9c945fe7c1ec389898a305fc10e6f65651a51a5d84 | EQUAL |
| tests/platformkit/execution/test_scoreboard_history.py | 17334 | a98694026a5b0759a48a05259881a65f9fe89c48eba5b2844e9800a48507dee2 | NEW |
| tests/platformkit/execution/test_scoreboard_history_e2e.py | 17185 | e552e7a929f6727a04511b0b9ced710d976397ffff1c61b141ed91fb347d745f | NEW |
| tests/platformkit/execution/test_scoreboard_history_store.py | 17966 | 3f9565c398fbbf3b59e4c2af9b882d394c0cb6fef06be9be68ebf7967be12bbd | NEW |

## Literal test edits before / after (FIX 1c)
Each JSON array contains exact source lines; [] means no lines. Line numbers use the pinned base and candidate respectively.
Blank-only edits are grouped per file with their exact coordinates; no edit or seal shim is omitted.
| File / old:new lines | Authority | Before | After |
|---|---|---|---|
| test_ingame_scoreboard_amendment.py 237:236/237:238 | AMENDMENT 1(a); AMENDMENT 3(c) | ``[]`` | ``["@pytest.mark.parametrize('day,base', [('2026-09-29', '150136727000f977dd0c0358fb1dffa615156c76'),", "                                    ('2026-09-30', None)])"]`` |
| test_ingame_scoreboard_amendment.py 238:241/240:243 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["def test_identity_after_landing_and_later_commit(tmp_path, monkeypatch, changed):", "    relative = 'docs/evidence/forward/scoreboard/PREREG_2026-09-29.json'", "    raw = (m.ROOT / relative).read_bytes()", "    assert json.loads(raw)['sha256'] == '171c0f5af1aff8d53b567859a24b20abb24e16e4ca72138ca8c4bccddaf358cc'"]`` | ``["def test_identity_after_landing_and_later_commit(tmp_path, monkeypatch, changed, day, base):", "    relative = 'docs/evidence/forward/scoreboard/PREREG_' + day + '.json'", "    if base:", "        assert json.loads((m.ROOT / relative).read_bytes())['sha256'] == '171c0f5af1aff8d53b567859a24b20abb24e16e4ca72138ca8c4bccddaf358cc'"]`` |
| test_ingame_scoreboard_amendment.py 243:245/245:249 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["        path = tmp_path / name", "        path.parent.mkdir(parents=True, exist_ok=True)", "        put(path, (m.ROOT / name).read_bytes().replace(b'\\r\\n', b'\\n'))"]`` | ``["        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True)", "        data = (subprocess.run(['git', '-C', str(m.ROOT), 'show', base + ':' + name],", "                check=True, capture_output=True).stdout if base and name in m.IMPLEMENTATION_FILES", "                else (m.ROOT / name).read_bytes())", "        put(path, data.replace(b'\\r\\n', b'\\n'))"]`` |
| test_ingame_scoreboard_amendment.py 251:252/255:255 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["    git('init', '-b', 's475-construct')", "    git('config', 'core.autocrlf', 'false')"]`` | ``["    git('init', '-b', 's475-construct'); git('config', 'core.autocrlf', 'false')"]`` |
| test_ingame_scoreboard_amendment.py 257:259/260:261 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["    commit()", "    payload = json.loads(m._git_head(tmp_path, relative))", "    live = {name: probe.digest((m.ROOT / name).read_bytes()) for name in m.IMPLEMENTATION_FILES}"]`` | ``["    commit(); payload = json.loads(m._git_head(tmp_path, relative))", "    live = {name: probe.digest((tmp_path / name).read_bytes()) for name in m.IMPLEMENTATION_FILES}"]`` |
| test_ingame_scoreboard_amendment.py 265:265/267:267 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["            probe.verify_landing(path, root=tmp_path, clock=lambda: DAY + 'T00:00:00Z')"]`` | ``["            probe.verify_landing(path, root=tmp_path, clock=lambda: day + 'T00:00:00Z')"]`` |
| test_ingame_scoreboard_amendment.py 267:267/269:269 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["            m.verify_amendment(path, DAY, root=tmp_path)"]`` | ``["            m.verify_amendment(path, day, root=tmp_path)"]`` |
| test_ingame_scoreboard_amendment.py 275:276/277:278 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["        for day in (DAY, '2026-10-05'):", "            assert probe.verify_landing(path, root=tmp_path, clock=lambda: day + 'T00:00:00Z') == {'mlb', 'soccer'}"]`` | ``["        for query_day in (day, '2026-10-05'):", "            assert probe.verify_landing(path, root=tmp_path, clock=lambda: query_day + 'T00:00:00Z') == {'mlb', 'soccer'}"]`` |
| test_ingame_scoreboard_amendment.py 282:282/284:284 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["        probe.verify_landing(path, root=tmp_path, clock=lambda: DAY + 'T00:00:00Z')"]`` | ``["        probe.verify_landing(path, root=tmp_path, clock=lambda: day + 'T00:00:00Z')"]`` |
| test_ingame_scoreboard_model_optional.py 102:103/102:105 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["    assert m._json(native.run()) == base._json(native.run(base))", "    assert m._json(native.run(model_optional=frozenset())) == base._json(native.run(base))"]`` | ``["    expected_report = native.run(base)", "    for report in (native.run(), native.run(model_optional=frozenset())):", "        assert set(report) == set(expected_report) \| {'settlement'}", "        assert m._json({k: v for k, v in report.items() if k != 'settlement'}) == base._json(expected_report)"]`` |
| test_ingame_scoreboard_model_optional.py 109:109/111:114 | AMENDMENT 1(a); AMENDMENT 3(c) | ``["    assert m.main(argv) == 0 and out.read_bytes() == before"]`` | ``["    assert m.main(argv) == 0", "    receipt = json.loads(out.read_bytes())", "    assert set(receipt) == set(json.loads(before)) \| {'settlement'}", "    assert (m._json({k: v for k, v in receipt.items() if k != 'settlement'}) + '\\n').encode() == before"]`` |
| test_ingame_scoreboard_night.py 14:14/14:14 | AMENDMENT 1(a); AMENDMENT 2(b); AMENDMENT 3(c) | ``["POLICY, AMENDMENT = m.SEALS[0][1], m.SEALS[1][1]"]`` | ``["POLICY, ORIGINAL, AMENDMENT = (entry[1] for entry in m.SEALS)"]`` |
| test_ingame_scoreboard_night.py 27:28/27:28 | AMENDMENT 1(a); AMENDMENT 2(b); AMENDMENT 3(c) | ``["    raw = (m.ROOT / AMENDMENT).read_bytes()", "    atomic(tmp_path / AMENDMENT, raw)"]`` | ``["    for path in (ORIGINAL, AMENDMENT):", "        atomic(tmp_path / path, (m.ROOT / path).read_bytes())"]`` |
| test_ingame_scoreboard_night.py 40:40/40:40 | AMENDMENT 1(a); AMENDMENT 2(b); AMENDMENT 3(c) | ``["            '--out', str(tmp_path / 'out.json'), '--date', '2026-09-29',"]`` | ``["            '--out', str(tmp_path / 'out.json'), '--date', '2026-09-30',"]`` |
| test_ingame_scoreboard_night.py 75:75/75:75 | AMENDMENT 1(a); AMENDMENT 2(b); AMENDMENT 3(c) | ``["@pytest.mark.parametrize('path', [POLICY, AMENDMENT, 'data/report.json', 'source.json'])"]`` | ``["@pytest.mark.parametrize('path', [POLICY, ORIGINAL, AMENDMENT, 'data/report.json', 'source.json'])"]`` |
| test_ingame_scoreboard_night.py 79:79/79:79 | AMENDMENT 1(a); AMENDMENT 2(b); AMENDMENT 3(c) | ``["    if path not in (POLICY, AMENDMENT):"]`` | ``["    if path not in (POLICY, ORIGINAL, AMENDMENT):"]`` |
| test_ingame_scoreboard_night.py 91:91/91:91 | AMENDMENT 1(a); AMENDMENT 2(b); AMENDMENT 3(c) | ``["                                         ('2026-09-29', frozenset({'mlb', 'soccer'}))])"]`` | ``["                                         ('2026-09-30', frozenset({'mlb', 'soccer'}))])"]`` |
| test_ingame_scoreboard_night.py 140:140/140:141 | AMENDMENT 1(a); AMENDMENT 2(b); AMENDMENT 3(c) | ``["    step = paper._steps(tmp_path, day, as_of, 'construct', budget, context)[-1]"]`` | ``["    step = next(s for s in paper._steps(tmp_path, day, as_of, 'construct', budget, context)", "                if s['name'] == 'scoreboard')"]`` |
| test_ingame_scoreboard_night_table.py 16:15/16:17 | AMENDMENT 1(a); AMENDMENT 2(a); AMENDMENT 3(c) | ``[]`` | ``["REPLACEMENT = 'docs/evidence/forward/scoreboard/PREREG_2026-09-30.json'", "REPLACEMENT_SHA = '801af61b2755a99f9d5e238acd59bb1b6cf88212d1cb81b11a576ac32877b7aa'"]`` |
| test_ingame_scoreboard_night_table.py 195:195/197:199 | AMENDMENT 1(a); AMENDMENT 2(a); AMENDMENT 3(c) | ``["    assert night.SEALS[:2] == TABLE"]`` | ``["    assert night.SEALS[:3] == (*TABLE, ('amendment', REPLACEMENT, None))", "    raw = json.dumps(night.SEALS[:3]).encode('ascii')", "    assert hashlib.sha256(raw).hexdigest() == '17a5ff7a67ad397cfce1ead6ae17e0e617995a382a1a64d4175c33b5d196fc3e'"]`` |
| test_ingame_scoreboard_night_table.py 231:230/235:238 | AMENDMENT 1(a); AMENDMENT 2(a); AMENDMENT 3(c) | ``[]`` | ``["        if path == REPLACEMENT:", "            raw = (root / path).read_bytes().replace(b'\\r\\n', b'\\n')", "            assert hashlib.sha256(raw).hexdigest() == REPLACEMENT_SHA", "            return raw"]`` |
| test_ingame_scoreboard_night_table.py 243:242/251:252 | AMENDMENT 1(a); AMENDMENT 2(a); AMENDMENT 3(c) | ``[]`` | ``["    assert night.select('2026-09-30', night.SEALS, **kwargs)['amendment']['path'] == REPLACEMENT", "    assert verifier.call_args.args == (night.ROOT / REPLACEMENT, '2026-09-30')"]`` |
| test_ingame_scoreboard_night_e2e.py 23:23/23:24 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["AMENDMENT = 'docs/evidence/forward/scoreboard/PREREG_2026-09-29.json'"]`` | ``["ORIGINAL = 'docs/evidence/forward/scoreboard/PREREG_2026-09-29.json'", "AMENDMENT = 'docs/evidence/forward/scoreboard/PREREG_2026-09-30.json'"]`` |
| test_ingame_scoreboard_night_e2e.py 60:60/61:61 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    path = root / AMENDMENT"]`` | ``["    path = root / ORIGINAL"]`` |
| test_ingame_scoreboard_night_e2e.py 64:63/65:68 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``[]`` | ``["    commit(root, [*amendment.IMPLEMENTATION_FILES, ORIGINAL])", "    for relative in amendment.IMPLEMENTATION_FILES:", "        put(root / relative, (ROOT / relative).read_bytes().replace(b'\\r\\n', b'\\n'))", "    put(root / AMENDMENT, (ROOT / AMENDMENT).read_bytes())"]`` |
| test_ingame_scoreboard_night_e2e.py 123:123/128:128 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    argv = construct(index, '2026-09-29', soccer=True)"]`` | ``["    argv = construct(index, '2026-09-30', soccer=True)"]`` |
| test_ingame_scoreboard_night_e2e.py 129:129/134:134 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["        payload_sha256=payload['sha256'], effective_from='2026-09-29T00:00:00.000000Z',"]`` | ``["        payload_sha256=payload['sha256'], effective_from='2026-09-30T00:00:00.000000Z',"]`` |
| test_ingame_scoreboard_night_e2e.py 137:138/142:143 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    expected = scorer.run(index/'books', index/'states', index/'schedule.json', '2026-09-29',", "        ['mlb', 'soccer'], ROOT/POLICY, [index/'history.jsonl'], '2026-09-29T23:59:59Z',"]`` | ``["    expected = scorer.run(index/'books', index/'states', index/'schedule.json', '2026-09-30',", "        ['mlb', 'soccer'], ROOT/POLICY, [index/'history.jsonl'], '2026-09-30T23:59:59Z',"]`` |
| test_ingame_scoreboard_night_e2e.py 143:145/148:150 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["def test_policy_fresh_process_byte_identity(tmp_path):", "    argv = construct(tmp_path, '2026-09-28'); out = tmp_path/'out.json'", "    result = child(tmp_path, argv)"]`` | ``["def test_policy_fresh_process_byte_identity(index):", "    argv = construct(index, '2026-09-28'); out = index/'out.json'", "    result = child(index, argv, injected=True)"]`` |
| test_ingame_scoreboard_night_e2e.py 151:151/156:156 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    result = child(tmp_path, argv, legacy=True)"]`` | ``["    result = child(index, argv, legacy=True)"]`` |
| test_ingame_scoreboard_night_e2e.py 157:157/162:162 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    argv = construct(index, '2026-09-29'); out = index/'out.json'; put(out, b'preserved\\n')"]`` | ``["    argv = construct(index, '2026-09-30'); out = index/'out.json'; put(out, b'preserved\\n')"]`` |
| test_ingame_scoreboard_night_e2e.py 160:160/165:165 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["        night.main(argv, root=index, git_commit_time=lambda *_: '2026-09-29T00:00:00Z')"]`` | ``["        night.main(argv, root=index, git_commit_time=lambda *_: '2026-09-30T00:00:00Z')"]`` |
| test_ingame_scoreboard_night_e2e.py 168:175/173:173 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    changed = amendment.IMPLEMENTATION_FILES[0]; put(index/changed, b'# replacement construct\\n')", "    replacement = 'docs/evidence/forward/scoreboard/PREREG_2026-10-01.json'", "    amendment.main(['--write', str(index/replacement), '--effective-from', '2026-10-01'],", "                   root=index, clock=lambda: '2026-09-30T12:00:00Z')", "    commit(index, [changed, replacement], '2026-09-30T12:00:00Z')", "    base_seals = night.SEALS", "    seals = (*base_seals, ('amendment', replacement, None))", "    monkeypatch.setattr(night, 'SEALS', seals)"]`` | ``["    base_seals, seals = night.SEALS[:2], night.SEALS"]`` |
| test_ingame_scoreboard_night_e2e.py 183:183/181:181 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    for day in ('2026-09-29', '2026-09-30'):"]`` | ``["    for day in ('2026-09-29',):"]`` |
| test_ingame_scoreboard_night_e2e.py 188:188/186:186 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    for day in ('2026-10-01', '2026-10-05'):"]`` | ``["    for day in ('2026-09-30', '2026-10-05'):"]`` |
| test_ingame_scoreboard_night_e2e.py 191:191/189:189 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["        assert result['amendment']['path'] == replacement"]`` | ``["        assert result['amendment']['path'] == AMENDMENT"]`` |
| test_ingame_scoreboard_night_e2e.py 201:200/199:199 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``[]`` | ``["        args[args.index('--date')+1] = '2026-09-30'"]`` |
| test_ingame_scoreboard_night_e2e.py 207:207/206:206 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    result = child(index, argv)"]`` | ``["    result = child(index, argv, injected=True)"]`` |
| test_ingame_scoreboard_night_e2e.py 214:214/213:212 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["    identity = index/amendment.IMPLEMENTATION_FILES[0]; put(identity, b'# changed\\n')"]`` | ``[]`` |
| test_ingame_scoreboard_night_e2e.py 227:228/225:226 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["def test_arms_parity(tmp_path, arms, expected):", "    argv = construct(tmp_path, '2026-09-28') + ([] if arms is None else ['--arms', arms])"]`` | ``["def test_arms_parity(index, arms, expected):", "    argv = construct(index, '2026-09-28') + ([] if arms is None else ['--arms', arms])"]`` |
| test_ingame_scoreboard_night_e2e.py 230:230/228:228 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["        result = child(tmp_path, argv, legacy=legacy)"]`` | ``["        result = child(index, argv, legacy=legacy, injected=not legacy)"]`` |
| test_ingame_scoreboard_night_e2e.py 232:232/230:230 | AMENDMENT 1(a); AMENDMENT 2(b),(c); AMENDMENT 3(c) | ``["        assert strict_report(tmp_path/'out.json')['arm_order'] == expected"]`` | ``["        assert strict_report(index/'out.json')['arm_order'] == expected"]`` |
| test_paper_night.py 163:163/163:163 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["    assert set(b[\"ceiling_bytes\"]) == set(night.NAMES) \| {\"scoreboard\"}"]`` | ``["    assert set(b[\"ceiling_bytes\"]) == set(night.NAMES) \| {\"scoreboard\", \"history\"}"]`` |
| test_paper_night_steps.py 56:57/49:49 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["", "def test_scoreboard_step_history_finds_prior_files_sorted_skips_missing_and_stale(tmp_path):"]`` | ``["def test_scoreboard_step_history_never_lists_prior_files(tmp_path):"]`` |
| test_paper_night_steps.py 65:66/57:57 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["    assert history == [\"training/2026-09-19.jsonl\", \"training/2026-09-21.jsonl\"]", ""]`` | ``["    assert history == []"]`` |
| test_paper_night_steps.py 77:76/68:93 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``[]`` | ``["@pytest.mark.parametrize(\"change,reason\", [(None, None), (\"lookback\", \"config_mismatch\"),", "    (\"embargo\", \"config_mismatch\"), (\"seal\", \"config_mismatch\"),", "    (\"boundary\", \"corrupt_artifact:schema\"), (\"snapshot\", \"corrupt_artifact:schema\"),", "    (\"generated_at\", \"corrupt_artifact:schema\")])", "def test_scoreboard_step_requires_current_config(tmp_path, change, reason):", "    import hashlib", "    from scripts.platformkit.execution import scoreboard_history_store as store", "    from tests.platformkit.execution.test_scoreboard_history_store import manifest", "    prereg = tmp_path / \"docs/prereg.json\"", "    prereg.parent.mkdir(); prereg.write_bytes(b\"construct seal\")", "    config = steps.history_config(\"2026-09-22\", 3, 3, hashlib.sha256(prereg.read_bytes()).hexdigest())", "    artifact = manifest(b\"\"); artifact[\"config\"] = dict(config)", "    if change == \"lookback\": artifact[\"config\"][\"lookback_days\"] = 4", "    if change == \"embargo\": artifact[\"config\"] = steps.history_config(\"2026-09-22\", 3, 4, config[\"prereg_sha256\"])", "    if change == \"seal\": artifact[\"config\"][\"prereg_sha256\"] = \"b\" * 64", "    if change in (\"boundary\", \"snapshot\"): artifact[\"config\"][change] = \"2099-01-01T00:00:00.000000Z\"", "    if change == \"generated_at\": artifact[\"generated_at\"] = \"2099-01-01\"", "    artifact[\"result\"][\"nights\"] = [dict(artifact[\"result\"][\"nights\"][0], date=\"2026-09-18\")] if change == \"lookback\" else []", "    artifact[\"observation\"][\"nights\"] = [dict(artifact[\"observation\"][\"nights\"][0], date=\"2026-09-18\")] if change == \"lookback\" else []", "    rows, meta = tmp_path / \"training/2026-09-22.jsonl\", store.manifest_path(tmp_path, \"2026-09-22\")", "    rows.parent.mkdir(); rows.write_bytes(b\"\"); meta.parent.mkdir(parents=True)", "    meta.write_text(json.dumps(artifact), encoding=\"ascii\")", "    step = steps.scoreboard_step(tmp_path, \"2026-09-22\", \"2026-09-22T10:00:00Z\", [\"mlb\"],", "                                 dict(p_dict(), history_lookback_days=\"3\"), raw_dict())", "    assert step[\"argv\"][step[\"argv\"].index(\"--history\") + 1:] == ([] if reason else [\"training/2026-09-22.jsonl\"])", "    assert (step[\"history_refused\"], step[\"history_refusal_reason\"]) == (int(reason is not None), reason)"]`` |
| test_paper_night_steps.py 78:87/95:95 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["def test_scoreboard_step_lookback_days_from_producer_arg(tmp_path):", "    training_dir = tmp_path / \"training\"", "    training_dir.mkdir(parents=True)", "    (training_dir / \"2026-09-20.jsonl\").write_text(\"{}\")  # 2 days back: outside a 1-day lookback", "    p = dict(p_dict(), history_lookback_days=\"1\")", "    step = steps.scoreboard_step(tmp_path, \"2026-09-22\", \"2026-09-22T10:00:00Z\", [\"mlb\"], p, raw_dict())", "    assert step[\"argv\"][step[\"argv\"].index(\"--history\") + 1:] == []", "", "", "def test_scoreboard_step_history_deduplicates_repeated_candidates(tmp_path):"]`` | ``["def test_scoreboard_step_history_requires_valid_pair(tmp_path):"]`` |
| test_paper_night_steps.py 95:96/103:103 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["    assert history == [\"shared.jsonl\"]", ""]`` | ``["    assert history == [] and step[\"history_refused\"] == 1"]`` |
| test_paper_night_steps.py 186:187/182:182 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["    assert steps.unknown_declared_steps(dict.fromkeys(NAMES + (\"scoreboard\",), 1), NAMES) == set()", ""]`` | ``["    assert steps.unknown_declared_steps(dict.fromkeys(NAMES + (\"scoreboard\", \"history\"), 1), NAMES) == set()"]`` |
| test_paper_night_steps.py blank-only edits | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c); LOC limit | ``[["13:13/13:12", [""], []], ["17:17/16:15", [""], []], ["20:20/18:17", [""], []], ["28:28/25:24", [""], []], ["33:33/29:28", [""], []], ["36:36/31:30", [""], []], ["50:50/44:43", [""], []], ["101:101/108:107", [""], []], ["104:104/110:109", [""], []], ["113:113/118:117", [""], []], ["120:120/124:123", [""], []], ["139:139/142:141", [""], []], ["150:150/152:151", [""], []], ["156:156/157:156", [""], []], ["165:165/165:164", [""], []], ["171:171/170:169", [""], []], ["180:180/178:177", [""], []], ["184:184/181:180", [""], []], ["194:194/189:188", [""], []], ["200:200/194:193", [""], []], ["204:204/197:196", [""], []], ["210:210/202:201", [""], []], ["223:223/214:213", [""], []], ["228:228/218:217", [""], []], ["240:240/229:228", [""], []], ["244:244/232:231", [""], []], ["255:255/242:241", [""], []], ["259:259/245:244", [""], []], ["271:271/256:255", [""], []], ["279:279/263:262", [""], []]]`` | Coordinates, before and after are recorded together. |
| test_paper_night_scoreboard_step.py 16:15/16:18 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``[]`` | ``["# These pre-amendment constructs pin the legacy table while running the real entry point.", "LEGACY_NIGHT_CHILD = (\"from scripts.platformkit.execution import ingame_scoreboard_night as m; \"", "                      \"m.SEALS=(m.LEGACY_POLICY,); raise SystemExit(m.main())\")"]`` |
| test_paper_night_scoreboard_step.py 55:55/58:58 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``["    return b"]`` | ``["    b[\"deadline_s\"] = {k: v for k, v in b[\"deadline_s\"].items() if k in b[\"ceiling_bytes\"]}; return b"]`` |
| test_paper_night_scoreboard_step.py 63:64/66:66 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``["    # Case 1/2: Popen spied + redirected to a cheap stub; scoreboard's own", "    # call gets fake_scoreboard's schema-compliant one (AMENDMENT 4(a))."]`` | ``["    # Popen redirects scoreboard and history children to construct-only stubs."]`` |
| test_paper_night_scoreboard_step.py 69:69/71:72 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``["        out = argv[argv.index(\"--out\") + 1]"]`` | ``["        out = (\"docs/evidence/forward/scoreboard/training/\" + argv[argv.index(\"--for-night\") + 1] + \".manifest.json\"", "               if \"scripts.platformkit.execution.scoreboard_history\" in argv else argv[argv.index(\"--out\") + 1])"]`` |
| test_paper_night_scoreboard_step.py 122:123/123:124 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``["    assert code == 0 and payload[\"status\"] == \"COMPLETE\" and len(calls) == 4", "    assert [s[\"name\"] for s in payload[\"steps\"]] == FROZEN_LEGACY_NAMES + [\"scoreboard\"]"]`` | ``["    assert code == 0 and payload[\"status\"] == \"COMPLETE\" and len(calls) == 5", "    assert [s[\"name\"] for s in payload[\"steps\"]] == FROZEN_LEGACY_NAMES + [\"scoreboard\", \"history\"]"]`` |
| test_paper_night_scoreboard_step.py 220:219/214:214 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``[]`` | ``["    scoreboard[\"argv\"] = [sys.executable, \"-c\", LEGACY_NIGHT_CHILD, *scoreboard[\"argv\"][3:]]"]`` |
| test_paper_night_scoreboard_step.py 241:240/235:235 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``[]`` | ``["    scoreboard[\"argv\"] = [sys.executable, \"-c\", LEGACY_NIGHT_CHILD, *scoreboard[\"argv\"][3:]]"]`` |
| test_paper_night_scoreboard_step.py blank-only edits | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c); LOC limit | ``[["84:84/87:86", [""], []], ["110:110/112:111", [""], []], ["131:131/132:131", [""], []], ["144:144/144:143", [""], []], ["159:159/158:157", [""], []], ["170:170/168:167", [""], []], ["183:183/180:179", [""], []], ["195:195/191:190", [""], []], ["206:206/201:200", [""], []], ["224:224/219:218", [""], []], ["246:246/241:240", [""], []], ["256:256/250:249", [""], []], ["271:271/264:263", [""], []], ["288:288/280:279", [""], []]]`` | Coordinates, before and after are recorded together. |
| test_paper_night_scoreboard_step_1c.py 15:15/15:15 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``["    REPO_ROOT, _low_ceiling_template, four_budget,"]`` | ``["    LEGACY_NIGHT_CHILD, REPO_ROOT, _low_ceiling_template, four_budget,"]`` |
| test_paper_night_scoreboard_step_1c.py 46:45/46:46 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``[]`` | ``["    scoreboard[\"argv\"] = [night.sys.executable, \"-c\", LEGACY_NIGHT_CHILD, *scoreboard[\"argv\"][3:]]"]`` |
| test_paper_night_inputs.py 129:129/127:127 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["def test_5_6_7_9_whole_refusal(layout, tmp_path, base, record_property, variant, reason):"]`` | ``["def test_5_6_7_9_whole_refusal(layout, tmp_path, base, record_property, variant, reason, monkeypatch):"]`` |
| test_paper_night_inputs.py 162:161/160:160 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``[]`` | ``["    monkeypatch.setattr(night, \"scoreboard_step\", lambda *a: pytest.fail(\"refused plan computed history\"))"]`` |
| test_paper_night_inputs.py 163:162/162:162 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``[]`` | ``["    assert context[\"history\"] == []"]`` |
| test_paper_night_inputs.py 252:252/252:252 | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c) | ``["    assert len(calls) == (4 if value == \"committed\" else 0)"]`` | ``["    assert len(calls) == (5 if value == \"committed\" else 0)"]`` |
| test_paper_night_inputs.py blank-only edits | CHANGE 7; AMENDMENT 1(c),(d),(f); AMENDMENT 3(a),(b),(c); LOC limit | ``[["122:123/122:121", ["", ""], []]]`` | Coordinates, before and after are recorded together. |
| test_paper_night_inputs_e2e.py 12:11/12:12 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``[]`` | ``["from tests.platformkit.execution.test_paper_night_scoreboard_step import LEGACY_NIGHT_CHILD"]`` |
| test_paper_night_inputs_e2e.py 145:146/136:138 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``["        out = argv[argv.index(\"--out\") + 1]", "        if module.endswith((\"forward_qualification_daily\", \"forward_week_report\")):"]`` | ``["        out = (\"docs/evidence/forward/scoreboard/training/\" + argv[argv.index(\"--for-night\") + 1] + \".manifest.json\"", "               if module.endswith(\"scoreboard_history\") else argv[argv.index(\"--out\") + 1])", "        if module.endswith((\"forward_qualification_daily\", \"forward_week_report\", \"scoreboard_history\")):"]`` |
| test_paper_night_inputs_e2e.py 148:147/140:141 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``[]`` | ``["        elif module == \"scripts.platformkit.execution.ingame_scoreboard_night\":", "            argv = [sys.executable, \"-c\", LEGACY_NIGHT_CHILD, *argv[3:]]"]`` |
| test_paper_night_inputs_e2e.py 289:288/277:287 | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c) | ``[]`` | ``["", "def test_history_refusal_is_written_to_night_record(tmp_path, monkeypatch):", "    budget = _budget(); write(tmp_path / \"budget.json\", budget)", "    step = dict(name=\"scoreboard\", out=\"out.json\", argv=[], skip=\"archive_absent\",", "                history_refused=1, history_refusal_reason=\"config_mismatch\")", "    code = night.main([\"--date\", DAY, \"--as-of\", AS_OF, \"--repo-root\", str(tmp_path),", "                       \"--budget\", str(tmp_path / \"budget.json\")], steps=[step])", "    record = json.loads((tmp_path / \"docs/evidence/forward/nights\" / (DAY + \".json\")).read_bytes())", "    assert code == 3 and record[\"status\"] == \"PARTIAL\"", "    assert record[\"steps\"][0][\"history_refused\"] == 1", "    assert record[\"steps\"][0][\"history_refusal_reason\"] == \"config_mismatch\""]`` |
| test_paper_night_inputs_e2e.py blank-only edits | CHANGE 7; AMENDMENT 1(a),(c),(f); AMENDMENT 3(c); LOC limit | ``[["17:17/18:17", [""], []], ["25:25/25:24", [""], []], ["28:28/27:26", [""], []], ["43:43/41:40", [""], []], ["55:55/52:51", [""], []], ["62:62/58:57", [""], []], ["86:86/81:80", [""], []], ["95:95/89:88", [""], []], ["102:102/95:94", [""], []], ["133:133/125:124", [""], []], ["156:156/150:149", [""], []], ["198:198/191:190", [""], []], ["206:206/198:197", [""], []], ["216:216/207:206", [""], []], ["232:232/222:221", [""], []], ["272:272/261:260", [""], []]]`` | Coordinates, before and after are recorded together. |

## FIX 1c
Scope: AMENDMENT 3(a)-(e); construct fixtures only. The prior verified seal and scorer behavior remain unchanged.
| Finding | Failing reproduction | Exact fix and regression |
|---|---|---|
| 3(a), window | `A: ACCEPT complete=True` for M=2026-09-28, L=4, E=3, nights=[] | Derive W(M) from config; require every expected date once, chronologically, and matching result/observation inventories. After: `A: REFUSED corrupt_artifact:schema`; missing/extra/reordered nights refuse; regression covers the original probe. |
| 3(b), join | `B: ACCEPT row_game=g census_game=DIFFERENT result_rows=1` | Join rows by (sport, game_id) to census (sport, game_key), per-game counts, producer_counts[rows], and result.rows. Refuse absent or mismatched identities/counts; producer explicitly emits rows=0 for placeholder nights. After: `B: REFUSED census_mismatch`. |
| 3(c), inventory | `c literal assertion present: False` | The literal table above records every changed edit in all 11 landed test files, including every seal shim and history_refusal_reason assertion, with authorizing amendments. After: all literal edit rows regenerated; `c newly required exact assertion: True`; `c each seal shim occurrences: 7`. |
| 3(d), base | `d BASE matches pinned dispatch: False`; the spec changed after bc104bcea7217a0559819ea92ac634127f342042 | Generator and memo now pin 737f3939b01f6dab566ec82fa46cfbc98ae103ce; no moving-ref comparison. After: `d BASE matches fixed dispatch pin: True`; spec comparison `EQUAL`; 51 input paths checked and all guards unchanged. |
| 3(e), lookback | `E old assertion: ACCEPT state=published reason=wrong` (injected wrong result) | Replace the truthy-state assertion with exact reason == invalid_lookback and state == REFUSED. Fault probe now gives `E new assertion: AssertionError state=published reason=wrong`; actual CLI regression passes. |
Before a/b edits, the new regressions reproduced `11 failed, 75 passed` with DID NOT RAISE. Integration fixture correction: test_paper_night_steps first gave `4 failed, 52 passed`; align its mutated-config inventories with W(M), preserve assertions, then `56 passed`. Final counts appear above.
The generator renders this literal inventory directly from full pinned-base blobs; supplied verified results can be rendered with write_memo(results, failures, arms) without rerunning tests.
No new JSON seal or fixture path in FIX 1c; existing LF patterns below remain unchanged.
contract_preflight: 27 candidate paths, nine checks PASS (vocab, crlf, loc, schema, head_slice, spec_threshold, proposed, removed_artifact, row_duplication); verdict file excluded.

## E1 / E2 evidence attribution
E1 construct RUN here: pinned-base equality on every pre-existing scorer key (case 12 and S475 regressions).
The original 2026-09-24 committed receipt remains the historical anchor; its real archive replay is not rerun here.
E2 RUN by independent Opus tier, as recorded in the binding verdict and AMENDMENT 1; imported evidence, not a lane measurement:
| Consuming night | Rows | Complete | Wall seconds | Peak MB |
|---|---|---|---|---|
| 2026-09-28 | 1222 | false: 09-21 schedule_absent | 48.8 | 127.5 |
| 2026-09-29 | 2648 | true | 65.9 | 136.0 |
Opus inventories: 09-22 game 823412 settled: 1346 ticks, 1000 rows; 824624 settled zero ticks; 824785 unsettled 1551 ticks.
09-23: zero rows, 672 model_state_refused. For M=09-28, 09-24 game 822842 settled: 260 ticks, 222 rows;
823411/824707/824866 unsettled: 460/388/365 ticks. For M=09-29, 09-24 has 1648 rows;
823411 settles at 2026-09-25T00:57:49.620704Z with 474 rows. On 09-25, 824220 unsettled: 770 ticks;
823491 settled zero ticks; 824544 unsettled zero ticks. tick_after_final zero throughout.
Opus append probe: rows/config/result equal, observation future_records=5. Complete rerun already_present;
incomplete rerun reproduced identical bytes. No archive read or performance measurement by this fix lane.

## LF patterns (existing attributes; .gitattributes untouched)
`tests/platformkit/execution/fixtures/s474_*.jsonl text eol=lf`
`docs/evidence/forward/scoreboard/training/*.manifest.json text eol=lf`
`docs/evidence/forward/scoreboard/*.json text eol=lf` covers the new amendment.

## Mandatory disclosures
(a) Before S475, MLB rows lacking model_prob were excluded (historical 1648 of 1648); soccer was unmeasured. S475 model_optional is retained.
(b) No per-sport minimum-history rule exists; warmup ends at the first surviving settled eligible game.
(c) Verdicts remain INSUFFICIENT below 30 games per cell; historically 3 to 6 MLB games per night, fewer postseason. NFL/NCAAF/tennis have no CORPUS entry and remain A only.
(d) model_state_refused is the same training/scoring encoding refusal (historical 09-23: 672 of 672).
(e) Own-night history replaces overlapping prior-day files; a missed night leaves its successor A only for a night.
(f) Output adds only settlement; existing output keys retain identity.
(g) Invariance assumes UTC-dated append-only shards; later receipts dated before B(M) can alter reproduction, undetectable here.
(h) Changed tick_row/settle/run semantics need a new training template or prospective seal. Replacement effective 2026-09-30; original seals and receipts preserved.
The migration interval 2026-09-29 <= night < 2026-09-30 refuses amendment_mismatch after this identity change.
That scoreboard step would have been A_ONLY because no history existed before S474; its history step still runs and produces the file consumed on 2026-09-30.
(i) History ceiling/deadline NOT PROFILED beyond the historical four-night context; no service restarted.
Policy and thresholds are unchanged. Checks use pinned full base SHAs, never moving master or live HEAD assertions.

SHA: NOT CREATED (sandbox); files ready for lane_commit

## NOT VERIFIED
No fitted arm on a real night, real consumption night/E3, or NBA/soccer real nights. Real archive E1 replay was not supplied as verified by Opus and is not claimed here.
Truncated-but-present shards remain undetectable. Runtime verification of committed replacement seal awaits lane_commit; its live identities and prospective semantics are construct-tested.
