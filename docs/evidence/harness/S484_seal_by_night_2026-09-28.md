# S484 seal selection by night

FIX 1b complete locally: the five requested test files pass individually
(196 tests, zero failures), including all 23 enumerated CONSTRUCT cases.
The four other per-file counts below are retained FIX 1a results (131 tests),
not rerun in FIX 1b. Landing remains pending.

Local machine: Windows, C:/Users/neelj/nba-harness-h135. Generated nights and git
repositories use system temporary directories. No archive, network, pod or
scored comparison was used. Q1/Q2/Q4/Q5/Q9 are not applicable to this prepare-only
row. Denominator and bar remain all 23 enumerated constructs.

## FIX 1a

The binding AMENDMENT 1 supersedes the earlier proposed test-date migration.
Each finding was reproduced before its correction; exact relevant output follows.

(a) Sol blocking 1 / Opus blocking 1: the unedited two real-child regressions
reported `2 failed, 12 passed`, including
`assert 'prereg_absent' in 'ValueError: seal_not_effective'` and `assert 1 == 0`.
The exact first legacy tuple now has unbounded applicability (date.min for
selection), while declared per-kind ordering and other policy dates are unchanged.
Earlier legacy nights also retain run()'s own prereg validation, preserving the
original prereg_absent refusal instead of intercepting it with prereg_not_selected.
Dated nights retain the existing cross-check. The two original tests are unedited
and now report `14 passed`. Selection checks include 0001-01-01, 09-22 and 09-23;
the 09-23 fresh-process report is byte-identical to the legacy scorer's output.
Empty tables still refuse seal_not_effective. Case 21 retains the real supervisor
amendment_mismatch refusal with the existing output bytes and mtime preserved.

(b) Opus blocking 2: the original canonical-path comparison reported
`1 failed, 39 passed` at `assert all(steps[name] == old[name] ... scoreboard)`.
The authorized regression now compares argv[:2] + argv[3:] against the immutable
base 8fbc31112288e24a28501a361a48b6cd1779dbe6, asserts argv[2] == NIGHT_MODULE,
and preserves equality of every other scoreboard field. Result: `40 passed`.
The file is included in the generated inventory and required regression list.

(c) Opus correction 1: the original positive path probe returned
`docs/ok.json seal_index_invalid cause=non_increasing_dates` at date 09-24.
The in-memory mutant deleting the empty/dot/parent component guard survived:
`104 passed`. All path-shape entries, including Windows forms, now use 10-05
with the construct commit seam on 09-23. The identical mutant now reports
`6 failed, 98 passed`, each `Failed: DID NOT RAISE <class 'ValueError'>` for
a/../b, a/./b and a//b on both query dates. The unmodified validator reports
`104 passed`; docs/ok.json is accepted and each malformed path refuses with
`cause=invalid_entry`. Production path validation is unchanged.
Mutation reproduction: import the night module, replace only the source text
`or any(p in ('', '.', '..') for p in path.split('/')) or path in paths`
with `or path in paths`, exec the compiled source into that module's dictionary,
then pytest.main the table file alone with `-q -p no:cacheprovider`.
No mutated source or scratch file is written in the worktree.

(d) Opus notes 4-5, made binding by AMENDMENT 1: the root mismatch probe with
compile(..., optimize=2) reported `optimized_root: MISMATCH ACCEPTED`.
The module now uses an explicit if/raise. The same probe reports
`optimized_root: scorer_root_mismatch`; regression tests cover optimization
levels 0 and 2 by substituting the scorer module's __file__ in memory.
The NIGHT_MODULE constant now has the required two blank lines before def.
The entry-point test file, including memo self-checks, reports `30 passed`.

(e) Sol correction 2: both old memo revision lines contained
`4dbef8509590172b254b98b1c9cbe09751174ad5`. The verifier's later captured
`8a434bdb5c4ec6dfcd25079ed877bbf4aec5d9d3` is also superseded by the authorized
fast-forward. During FIX 1b, master advanced again. Candidate HEAD is
`1dfce38cfac814af528cddac0924ab7c7889dfe7`; current master verification base is
`72c5472aaf7ba79ca8de0d7880ad7ebec98ffdfb`. The generator receives these separate
literals; the worktree HEAD was not moved. Tests and memo checks never resolve moving refs. The
idempotence/pinned-reference regression passes; inventory includes the added
canonical-path regression. File sizes are observations, never pinned assertions.
The lander records the eventual landing SHA. NOT VERIFIED remains the last section.

## FIX 1b

Restored master's fill-realism normalization/comparison exactly and the two
blank lines before the next test. Only the AMENDMENT 1(b) import and
scoreboard argv[2] exclusion plus NIGHT_MODULE assertion differ from master.
The inventory uses the current master full SHA recorded above.

Fresh per-file runs with `python -m pytest <file> -q -p no:cacheprovider`:

- test_paper_night_inputs.py: 40 passed.
- test_paper_night_scoreboard_step.py: 14 passed.
- test_ingame_scoreboard_night.py: 30 passed.
- test_ingame_scoreboard_night_table.py: 104 passed.
- test_ingame_scoreboard_night_e2e.py: 8 passed.

Total: 196 passed, zero failures. The other four counts in the generated
table are historical FIX 1a results.

Contract preflight was run after the five test files, over all nine owned
paths with `--base master --spec docs/evidence/tracking/specs/S484_spec.md`.
Eight checks passed; LOC failed after restoring the exact requested lines.
No LOC exemption or additional code edit was applied. Output:

```text
PASS vocab clean over 9 files
PASS crlf no index-side CRLF over 9 file(s); 6 untracked, core.autocrlf normalizes on add
FAIL loc tests/platformkit/execution/test_paper_night_inputs.py=303
PASS schema additive over checked artifacts
PASS head_slice no head slices
PASS spec_threshold 5 literal(s) matched
PASS proposed no --proposed given
PASS removed_artifact no removed/renamed artifacts under 5 dir(s)
PASS row_duplication no row duplication over checked artifacts
```

`git diff master -- tests/platformkit/execution/test_paper_night_inputs.py`:

```diff
diff --git a/tests/platformkit/execution/test_paper_night_inputs.py b/tests/platformkit/execution/test_paper_night_inputs.py
index 45b520ced..2c6f01a4b 100644
--- a/tests/platformkit/execution/test_paper_night_inputs.py
+++ b/tests/platformkit/execution/test_paper_night_inputs.py
@@ -7,7 +7,7 @@ import subprocess
 
 import pytest
 from scripts.platformkit.execution import paper_night as night
-from scripts.platformkit.execution.paper_night_inputs import record_inputs
+from scripts.platformkit.execution.paper_night_inputs import NIGHT_MODULE, record_inputs
 
 DAY, NEXT, AS_OF = "2026-09-24", "2026-09-25", "2026-09-28T15:07:55Z"
 # Verbatim quoted distribution; this is a constructed shape, not archive bytes.
@@ -116,7 +116,10 @@ def test_3_4_canonical_paths(layout, base, record_property, kind):
         argv = steps["fill_realism"]["argv"][:]
         del argv[argv.index("--as-of"):argv.index("--out")]
         assert argv == old["fill_realism"]["argv"]
-        assert all(steps[name] == old[name] for name in ("qualification", "week", "scoreboard"))
+        assert all(steps[name] == old[name] for name in ("qualification", "week"))
+        argv, before = steps["scoreboard"]["argv"], old["scoreboard"]["argv"]
+        assert argv[2] == NIGHT_MODULE and argv[:2] + argv[3:] == before[:2] + before[3:]
+        assert {**steps["scoreboard"], "argv": before} == old["scoreboard"]
     else:
         assert all(path.lower().startswith("live_") for path in context["books"] + context["states"])
```

## Reproduction and contract checks

Run each generated-table test file separately:
`python -m pytest <one file> -q -p no:cacheprovider`.
The mutation run above is an intentional negative control, not a candidate failure.
Both `python -m scripts.platformkit.execution.ingame_scoreboard_night --help`
and `python -m scripts.platformkit.ops.probes.s484_memo_facts --help` exit 0.
Neither CLI declares a --self-check option; the per-file entry-point tests cover
memo generation, strict counts, idempotence, frozen revisions and output recovery.
Contract preflight uses the nine owned paths, --base master and the binding spec;
this explicitly required preflight is separate from immutable identity checks.
No new JSON seal or fixture exists. Existing .gitattributes patterns used are
`tests/platformkit/ingame/fixtures/s475_*.jsonl text eol=lf` and
`docs/evidence/forward/scoreboard/*.json text eol=lf`; .gitattributes is unchanged.

## Mandatory disclosures

- B and C stay None and the label A_ONLY on every real night until S474's training
  rows exist: _models returns {} on empty accepted history.
- EVERY later change to ANY of the six identity files requires a NEW amendment
  from ingame_scoreboard_amendment.main --write and a SEALS entry in the same
  landing. E is at least max(commit UTC day + 1, latest amendment day + 1).
  Nights before 09-29 are policy-only; 09-29 <= D < E refuse amendment_mismatch
  and have no scoreboard; D >= E selects the replacement. Receipts are preserved.
- LEGACY POLICY EXCEPTION: only the exact first tuple lacks prospectivity proof.
  Its reseal is 3d638de8e62d088837620f2ff0763544a3eb6108, dated 2026-09-25.
  AMENDMENT 1 gives it no lower bound; code does not establish prospectivity.
  Every other policy date remains later than its commit UTC day.
- Runtime validation cannot detect committed retroactive SEALS edits. The
  append-only rule, pinned tuple regression and SEALS digest are controls;
  git history is the record.
- Refusals use ValueError / exit 1 under child_nonzero_exit. Selection failures
  precede shard reads and writes; output-path refusal follows run().
- The night module is outside the six-file identity and passes exactly the sports
  verify_amendment returns. Production root equality uses an explicit if/raise.
- Receipt byte identity holds only until another row changes run() output;
  S474 adds settlement. Construct policy-night parity is verified here.
- paper_night._steps retains its SCOREBOARD_MODULE not_landed probe; both modules
  land together. The actual child argv token is NIGHT_MODULE.
- The supervisor construct doubles available RAM to admit its real subprocess;
  execution and polling are real. No production resources or settings change.

<!-- S484 GENERATED FACTS START -->
## Generated candidate inventories

Candidate HEAD supplied by orchestrator: `1dfce38cfac814af528cddac0924ab7c7889dfe7`.
Pinned verification base supplied by orchestrator: `72c5472aaf7ba79ca8de0d7880ad7ebec98ffdfb`.
Revision strings: **NOT EQUAL**. No moving revision is queried.
Uncommitted candidate changes are identified by the file digests below.

SEALS sha256(_json(SEALS)): `c13a22da05779e3cece5f6d50101c791a6cc9c3b470a095cd51f9af73fb7cd1f`.
Selector LF sha256: `abd7b61f4aa5f0c6946a490db21f7ec857392ac95b81db7379cf2f1e7c6f456f`.

### Cases and supplied per-file passes

Counts and case statuses are supplied by the orchestrator; this generator does not run pytest.

| File | Passed | Failed |
| --- | ---: | ---: |
| `tests/platformkit/execution/test_ingame_scoreboard.py` | 43 | 0 |
| `tests/platformkit/execution/test_ingame_scoreboard_amendment.py` | 62 | 0 |
| `tests/platformkit/execution/test_ingame_scoreboard_model_optional.py` | 16 | 0 |
| `tests/platformkit/execution/test_ingame_scoreboard_night.py` | 30 | 0 |
| `tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | 8 | 0 |
| `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | 104 | 0 |
| `tests/platformkit/execution/test_paper_night_inputs.py` | 40 | 0 |
| `tests/platformkit/execution/test_paper_night_inputs_e2e.py` | 10 | 0 |
| `tests/platformkit/execution/test_paper_night_scoreboard_step.py` | 14 | 0 |

| Case | Construct test file | Status |
| ---: | --- | --- |
| 1 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 2 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 3 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 4 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 5 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 6 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 7 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 8 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 9 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 10 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 11 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 12 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 13 | `tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | PASS |
| 14 | `tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | PASS |
| 15 | `tests/platformkit/execution/test_ingame_scoreboard_night.py` | PASS |
| 16 | `tests/platformkit/execution/test_ingame_scoreboard_night.py` | PASS |
| 17 | `tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | PASS |
| 18 | `tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | PASS |
| 19 | `tests/platformkit/execution/test_ingame_scoreboard_night.py` | PASS |
| 20 | `tests/platformkit/execution/test_ingame_scoreboard_night.py` | PASS |
| 21 | `tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | PASS |
| 22 | `tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | PASS |
| 23 | `tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | PASS |

Cases passing / cases enumerated: 23 / 23 (CONSTRUCT).

### E2: local seal checks, no archive

| Operation | Day | Result |
| --- | --- | --- |
| select | 2026-09-23 | `{"amendment": null, "model_optional": [], "policy": "docs/evidence/forward/scoreboard/PREREG_2026-09-24.json"}` |
| select | 2026-09-24 | `{"amendment": null, "model_optional": [], "policy": "docs/evidence/forward/scoreboard/PREREG_2026-09-24.json"}` |
| select | 2026-09-28 | `{"amendment": null, "model_optional": [], "policy": "docs/evidence/forward/scoreboard/PREREG_2026-09-24.json"}` |
| select | 2026-09-29 | `{"amendment": {"effective_from": "2026-09-29T00:00:00.000000Z", "model_optional_sports": ["mlb", "soccer"], "path": "docs/evidence/forward/scoreboard/PREREG_2026-09-29.json", "payload_sha256": "171c0f5af1aff8d53b567859a24b20abb24e16e4ca72138ca8c4bccddaf358cc", "sha256": "6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e"}, "model_optional": ["mlb", "soccer"], "policy": "docs/evidence/forward/scoreboard/PREREG_2026-09-24.json"}` |
| verify_amendment | 2026-09-28 | `refused amendment_not_effective` |
| verify_amendment | 2026-09-29 | `["mlb", "soccer"]` |
| verify_amendment | 2026-10-05 | `["mlb", "soccer"]` |

Named refusals recorded: 1.
Committed bytes and commit times above use the supplied candidate revision.

### Protected files against the immutable verification base

| Path | LF sha256 | Equal to base blob |
| --- | --- | --- |
| `scripts/platformkit/ingame/baseline_four_arm.py` | `dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2` | True |
| `scripts/platformkit/ingame/baseline_four_arm_eligibility.py` | `d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032` | True |
| `scripts/platformkit/ingame/baseline_four_arm_features.py` | `8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade` | True |
| `scripts/platformkit/execution/ingame_scoreboard.py` | `2b1a21ac4e94cce0b30f0f04fd157c82b928b2d664fbce37008a52b48f4d352d` | True |
| `scripts/platformkit/execution/ingame_scoreboard_rules.py` | `5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7` | True |
| `scripts/platformkit/eval_gate/walkforward.py` | `6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9` | True |
| `scripts/platformkit/execution/ingame_scoreboard_amendment.py` | `2ccc83054d93c4eb098820c869fd66560f0990cebe318e11a8e8bf0ef0604a6b` | True |
| `scripts/platformkit/execution/paper_night.py` | `4416bdefb76c8253eef887c34d609a68c6e9289b9d0125010ca5a50f8d69583c` | True |
| `scripts/platformkit/execution/paper_night_steps.py` | `3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780` | True |
| `scripts/platformkit/execution/paper_night_budget.json` | `83d2eb3defef596eaf16bbb9caa5befedcf74b8ab543dafc97e330bf94e3d03b` | True |
| `scripts/platformkit/execution/paper_night_deadline.py` | `df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b` | True |
| `scripts/platformkit/execution/paper_night_lock.py` | `1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa` | True |
| `.gitattributes` | `e747b3d00b62b9677772f645bd13ab8bb79ad3c381100f3ba1ee42176101344d` | True |
| `tests/platformkit/execution/fixtures/s465_case1_legacy_snapshot.json` | `46ecb1acd3217028e74de5fc48c984e276d115b57c0382c8d27edcefb98b52c3` | True |
| `tests/platformkit/execution/fixtures/s470_case1_legacy_snapshot.json` | `5e3b709129048a9279bddbbb4184025fd282db6e823c7f39298739c585ff8084` | True |

### A9 input inventory: bytes and sha256 are LF-normalised

Sizes describe this generation only; they are not pinned test expectations.

| Full path | LF bytes | LF sha256 | Resolution |
| --- | ---: | --- | --- |
| `C:/Users/neelj/nba-harness-h135/.gitattributes` | 1202 | `e747b3d00b62b9677772f645bd13ab8bb79ad3c381100f3ba1ee42176101344d` | text |
| `C:/Users/neelj/nba-harness-h135/docs/evidence/forward/schedules/2026-09-24_maker_forward.json` | 1094 | `ae92f7cf5369940317db0beb9beb137481c51286c5ab90b368b0329106159c22` | JSON text |
| `C:/Users/neelj/nba-harness-h135/docs/evidence/forward/scoreboard/PREREG_2026-09-24.json` | 5046 | `6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b` | JSON text |
| `C:/Users/neelj/nba-harness-h135/docs/evidence/forward/scoreboard/PREREG_2026-09-29.json` | 2010 | `6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e` | JSON text |
| `C:/Users/neelj/nba-harness-h135/docs/evidence/tracking/specs/S484_spec.md` | 27798 | `0e35cbeec128d2928a57f5bb146c99be1ce4da0340200ebc5565c33b73cd4e39` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/eval_gate/walkforward.py` | 8250 | `6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/ingame_scoreboard.py` | 22181 | `2b1a21ac4e94cce0b30f0f04fd157c82b928b2d664fbce37008a52b48f4d352d` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/ingame_scoreboard_amendment.py` | 6972 | `2ccc83054d93c4eb098820c869fd66560f0990cebe318e11a8e8bf0ef0604a6b` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/ingame_scoreboard_night.py` | 8315 | `abd7b61f4aa5f0c6946a490db21f7ec857392ac95b81db7379cf2f1e7c6f456f` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/ingame_scoreboard_rules.py` | 6769 | `5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/paper_night.py` | 15507 | `4416bdefb76c8253eef887c34d609a68c6e9289b9d0125010ca5a50f8d69583c` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/paper_night_budget.json` | 1505 | `83d2eb3defef596eaf16bbb9caa5befedcf74b8ab543dafc97e330bf94e3d03b` | JSON text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/paper_night_deadline.py` | 14592 | `df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/paper_night_inputs.py` | 9358 | `4163a4ed8217b9eedb67965cb0b49161594b0b1ab7078bc182b110638d159da9` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/paper_night_lock.py` | 1069 | `1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/execution/paper_night_steps.py` | 14942 | `3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/ingame/baseline_four_arm.py` | 17688 | `dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/ingame/baseline_four_arm_eligibility.py` | 11759 | `d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/ingame/baseline_four_arm_features.py` | 15466 | `8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade` | text |
| `C:/Users/neelj/nba-harness-h135/scripts/platformkit/ops/probes/s484_memo_facts.py` | 10447 | `dcbb88daaba77597314daff7e278a0268fcea7b20a8d56ff64c05e6f54fbd2c4` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/fixtures/s465_case1_legacy_snapshot.json` | 4274 | `46ecb1acd3217028e74de5fc48c984e276d115b57c0382c8d27edcefb98b52c3` | JSON text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/fixtures/s470_case1_legacy_snapshot.json` | 3312 | `5e3b709129048a9279bddbbb4184025fd282db6e823c7f39298739c585ff8084` | JSON text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_ingame_scoreboard.py` | 18140 | `201ce74642cc080276787c0dfd5b4a556bfdfb5865a1b592bca0735d34743f94` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_ingame_scoreboard_amendment.py` | 13571 | `bc02dffbf19cede2443bdba399fd0664c42c1cd0e2fc0af7613938d1fe01d41c` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_ingame_scoreboard_model_optional.py` | 12481 | `39147ee66fe24aaeb82cea7dbf41f40d77c29f1052921bf65fa42fc8a3bce78b` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_ingame_scoreboard_night.py` | 10335 | `2ea4ac7a29f642f642479907605041a6270706e186587e2f61c2007b7bcdecbb` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_ingame_scoreboard_night_e2e.py` | 13402 | `068956bf85dd703a1c1bae6f849efaf9685e4eed5cb59e2d9dd2d700fe5d0a31` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_ingame_scoreboard_night_table.py` | 10170 | `8b9705b846a3b0ee5757dae9f976a59fed4b04f5bf2d4a6000a500eee2557daf` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_paper_night_inputs.py` | 15921 | `81570211db12155ecdf86a8a37ee941b7464a7723b3883db6f14946cde4f26f7` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_paper_night_inputs_e2e.py` | 14481 | `b94a1404fffb95d86a84262056fac535e65f7990afc30fd556434c5047f15bde` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/execution/test_paper_night_scoreboard_step.py` | 16306 | `a5636df45bccae6375a9fe936e63f8f5a8d38519d803352c91881b03a6eac8f1` | text |
| `C:/Users/neelj/nba-harness-h135/tests/platformkit/ingame/fixtures/s475_mlb_state_row_2026-09-24.jsonl` | 960 | `247e8ae4f8c5bb47347043ebe85dc83f0d6d34b6387bf0a25c49295362802fdb` | JSON text |
| `C:/Users/neelj/nba-harness-h135/.pytest_cache/s484_fix1b_results.json` | 3908 | `5f8e95e21191eb2852c13328b8791ec64ab3a4a6255762db87fcbde92e6e1604` | JSON text |

New JSON seal/fixture patterns: none. Existing .gitattributes is unchanged.
<!-- S484 GENERATED FACTS END -->

- ORCHESTRATOR LANDING EDIT (2026-09-28 18:5xZ): the authorized scoreboard argv[2] assertion in test_paper_night_inputs.py folded onto the replaced line (walrus) so the file stays at 300 lines; semantics unchanged (qualification/week equal; argv[2] == NIGHT_MODULE; the rest of the scoreboard step equal to base with argv[2] excluded).
## NOT VERIFIED

No real amendment night yet; no fitted arm on a real night. No archive replay
E1/E3, first production-night E4, network or pod execution. E2 below the generated
header uses local seals only. Python 3.12 parsing is covered by round-trip cases,
not by execution on a Python 3.12 interpreter. Independent verification and landing
are not complete. No commit was created in this sandbox.
