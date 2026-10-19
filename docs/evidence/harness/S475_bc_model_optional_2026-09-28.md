# S475 model-optional B/C build

Original build PASS: 21 of 21 enumerated cases, including case 14. FIX 1b below.
The bar is 21 of 21, n = 21 (CONSTRUCT).
Eye check: n/a (S-row). No calibration claim.

Machine: local Windows worktree C:/Users/neelj/nba-harness-h129. All execution
used construct fixtures and system temporary directories. No network, pod,
captured archive scoring, or night scoring/re-scoring occurred.

## Before-condition (original build)

The orchestrator-copied fixture was opened locally; no archive was opened.
Its SHA-256 is 247e8ae4f8c5bb47347043ebe85dc83f0d6d34b6387bf0a25c49295362802fdb.
Game 822842 has no model_prob. The exact row and two construct priors produced:

```text
DEFAULT rows=0, missing_model_prob=3
ENABLED rows=1, B=0.5, C=0.5, D=None, d_eligible=False
```

Case 14 also checks the single-row selector exclusion, enabled census,
three-row predictor output, and held-out non-warmup state. Its per-file run
passed all 71 tests with zero skips; the copied fixture is now mandatory.

The single held-out row contributes one missing-model refusal; the combined
predictor input contributes three, including the two prior construct rows.
Base modules loaded from git blobs also produced these exact runtime refusals:

```text
select_rows: select_rows() got an unexpected keyword argument 'model_optional'
predict_rows: predict_rows() got an unexpected keyword argument 'model_optional'
run: run() got an unexpected keyword argument 'model_optional'
_models: _models() got an unexpected keyword argument 'optional'
```

## Import contracts read before implementation

The landed source files were read before modifying their callers. Exact relied-on
signatures below describe the original interfaces; the opt-in parameters are the
additive changes made by this row.

```python
select_rows(rows: list[dict], corpus: str) -> tuple[list[dict], dict]
predict_rows(rows: list[dict], corpus: str) -> list[dict]
_models(ticks: list, history: list, sport: str, day: str, counts: Counter) -> dict
run(books_root: Path, state_root: Path, schedule: Path, day: str, sports: list,
    prereg: Path, history: list = (), as_of: str | None = None,
    arms: tuple = ('A', 'B', 'C', 'D')) -> dict
_json(value: object) -> str
_seal(path: Path, sources: list, counts: Counter) -> dict
parse_venue_time(value: object) -> float | None
implementation_identity(root: Path, files: tuple[str, ...] = IMPLEMENTATION_FILES) -> str
scoreboard_row_updates(out: Path, before: int | None, reason: str | None) -> dict
```

The first two reside in the owned baseline modules; state helpers reside in
baseline_four_arm_features.py. Scoreboard, venue_time.py, paper_night_steps.py,
and registry_scorer_e_config.py supply the remaining interfaces. The facts
probe uses only the standard library. Existing S347 and S359 readers remain
on the default route; POLICY :28-43 and main are unchanged.

## Changes and prospective boundary

All three owned MODIFIED modules were changed. The selector and predictor gain
keyword-only `model_optional: bool = False`. The scoreboard accepts a sports
set but its main never supplies it. Default selector/predictor calls from the
scoreboard omit the keyword to preserve the landed two-argument spies.
B and C use all state-complete prior rows. D uses only model-present prior rows.
When B/C have training but D has none, optional non-NBA D is None. The original
all-arm warmup values remain unchanged on model-complete corpora, as case 6
requires. With no prior rows, D remains A with warmup=True; the scoreboard
hides D for both warmup forms (Opus note 2).

The new amendment module validates exact payload, live policy, all six file
identities, committed LF bytes, prospectivity, then effectivity, in that order.
The writer stages in the system temp directory, flushes and fsyncs, then uses
an atomic no-overwrite hard link. A concurrent destination is refused rather
than overwritten. Failed synchronization leaves no partial destination.
The facts probe atomically replaces only its marked memo section.

SEALS (binding statement, verbatim):
PREREG_2026-09-24.json, PREREG_2026-09-24_superseded_2026-09-25.json, PREREG_E_2026-09-25.json, BLOCK_CONFIG_E_2026-09-25.json and every committed night stay byte-identical; the S439 POLICY block (ingame_scoreboard.py:28-43) is not edited, so its sha stays 81f345...; the scoreboard's main never passes the keyword, so every night run under PREREG_2026-09-24 behaves exactly as today. The behaviour change exists only behind a NEW committed superseding amendment, effective strictly after landing, that no code consumes until the dependency below lands.

This row supersedes S439 AMENDMENT 1(f)'s accepted A / B_lag-only scope
prospectively and by amendment, never by reinterpreting the old seal. The
keyword is inert until S469 is amended, or a follow-up supplies night-dated
seal selection and verify_amendment wiring. That dependency must select the
greatest committed effective_from no later than the night, refuse future
seals, and regenerate this amendment against any new policy and implementation.
B is mid-only features on the state-complete population, not every tick.
The spec's 343 model_state_refused ticks stay without B; this count was not
remeasured here. No fitted number exists until S474's history producer and
activation both land. The default route retains S347's all-arm exclusion for
historical joined corpora. The spec's zero-finite census is evidence, not
permission; it was not rerun. This file and amendment remain uncommitted.

## Case table

`keyword refused` below is the measured base-signature TypeError quoted above;
it is not a claim that the unsupported enabled route ran on base.

| Case | Base result | Candidate result |
|---|---|---|
| 1 Default byte identity | Snapshot generated from base blobs | PASS, all four corpora |
| 2 Explicit False | Keyword refused | PASS, signature and output parity |
| 3 Thirteen raw boundaries | Base outputs executed for both sports | PASS, raw default parity and optional census |
| 4 Fitted opt-in | Keyword refused | PASS, all-row B/C and model-subset D training |
| 5 Zero D training | Keyword refused | PASS, D None and counted scoreboard refusal |
| 6 Complete-model parity | Default outputs executed | PASS, A/B/C/D/warmup equal |
| 7 NBA | Default outputs executed | PASS, opt-in exactly equal |
| 8 Scoreboard inert | Base run/main artifacts executed | PASS, byte equality and unchanged landed tests |
| 9 Scoreboard enabled | Keyword refused | PASS, native-shaped MLB/soccer B/C finite |
| 10 Normalisation | Keyword refused; default normaliser unchanged | PASS, tick/history string and counted refusals |
| 11 Future receipts | Enabled keyword refused | PASS, future insertion at either end |
| 12 Finals causality | Enabled keyword refused | PASS, held-out result changes do not alter B/C |
| 13 Embargo | Enabled keyword refused | PASS, equality refused and one microsecond power |
| 14 Exact real row | Default rows=0, missing_model_prob=3 | PASS, enabled B=0.5, C=0.5, D=None |
| 15 Fresh process | Inert CLI produces A_ONLY | PASS, enabled FITTED and inert no_fitted_arm |
| 16 Seals | Live POLICY and committed seal loaded | PASS, original seals and POLICY/main unchanged |
| 17 Generate | Module absent | PASS, deterministic, exclusive, prospective writes |
| 18 Verify | Module absent | PASS, tamper precedence and effective boundary |
| 19 E identity | Base identity computed | PASS, identical candidate identity |
| 20 Partial failure | Enabled keyword refused | PASS, soccer counted and MLB unchanged |
| 21 Readers | Default call sites retained | PASS, per-file reader regressions |

The snapshot is a one-time base artifact, not refreshed from candidate outputs.
It was generated by loading the three baseline base blobs into temporary
modules from commit 5ef78f53cfc319557db31e31d887e6c63757374f. The input builder
is `snapshot_inputs()` in the new baseline test. The four selections/predictions
contain respectively 10/10, 0/0, 0/0, and 10/10 rows for mlb_complete,
mlb_absent, soccer_absent, and nba_mixed. Its provenance is embedded in JSON.

## Prior FIX 1a reproduction and per-file results

Each invocation uses `python -m pytest <one file> -q -p no:cacheprovider`.
No suite was run. Files are under tests/platformkit/ingame or execution as named.

| File | Passed | Skipped |
|---|---:|---:|
| ingame/test_baseline_four_arm_model_optional.py | 71 | 0 |
| execution/test_ingame_scoreboard_model_optional.py | 16 | 0 |
| execution/test_ingame_scoreboard_amendment.py | 56 | 0 |
| execution/test_ingame_scoreboard.py | 43 | 0 |
| execution/test_ingame_scoreboard_1b.py | 16 | 0 |
| execution/test_ingame_scoreboard_1e.py | 4 | 0 |
| ingame/test_baseline_four_arm.py | 53 | 0 |
| ingame/test_baseline_four_arm_eligibility.py | 45 | 0 |
| ingame/test_baseline_four_arm_nba.py | 134 | 0 |
| ingame/test_baseline_four_arm_period.py | 72 | 0 |
| ingame/test_s359_four_arm_trial.py | 71 | 0 |
| ingame/test_nba_four_arm_trial.py | 78 | 0 |
| ingame/test_intel_prior_feature.py | 16 | 0 |
| ingame/test_four_arm_output_audit_nba.py | 30 | 0 |
| execution/test_registry_scorer_e_fit.py | 15 | 0 |
| execution/test_paper_night_scoreboard_step.py | 14 | 0 |
| tests/platform/test_ingame_scoreboard.py | 5 | 0 |

Prior FIX 1a total: 739 passed and 0 skipped across 17 separate test files.
These historical results are retained; FIX 1b reruns only the touched module tests.
The platform wrapper emitted 6 existing numerical RuntimeWarnings.
All invocations targeted a single file; two sequential command batches
briefly overlapped during the period and NBA-trial compatibility runs.

The _1b invocation additionally loaded a temporary pytest plugin outside the
worktree. For its three `test_prereg_*` cases only, an autouse fixture sets
`request.module._SCRATCH_DIR = tmp_path` and `request.module.m.__file__ =
str(tmp_path / 'scripts/platformkit/execution/ingame_scoreboard.py')` using
monkeypatch. Existing test source and assertions are unchanged. Other cases
use the real module location. This redirects their temporary seals without
editing any landed test or writing scratch inside the worktree.

CLI --help passed for baseline_four_arm, ingame_scoreboard,
ingame_scoreboard_amendment, and s475_memo_facts. The baseline self-check
also passed; the eligibility module has no CLI.
FIX 1a preflight passed nine checks with 13 candidate paths; its base was
8fbc31112288e24a28501a361a48b6cd1779dbe6. FIX 1b leaves .gitattributes unchanged.

## FIX 1a

(a) BLOCKING 1 / tier-2 CORRECTION 1: the stale `NOT VALIDATED: 20 of 21`
headline was corrected to 21/21 after `71 passed`; case 14 requires its fixture.
(b) CORRECTION 2: the original moving-ref comparison was replaced by pinned
base 8fbc31112288e24a28501a361a48b6cd1779dbe6. FIX 1b removes that E check.
(c) Both missing identity membership checks originally printed `False`.
The amendment now includes ingame_scoreboard_rules.py and eval_gate/walkforward.py;
its effective timestamp is canonical UTC midnight. The PREREG was generated
last in FIX 1a. Neither these six files nor that PREREG changes in FIX 1b.
(d) CORRECTION 3: `A9 fixture in OWNED=False` became true; facts include the fixture.
(e) Opus notes 2, 4, 5: baseline_four_arm.py:122-123 sets D=None only on the
opt-in non-NBA path without D training. The scoreboard differential now binds
base selector and predictor blobs. Future receipts now contain valid changed
state and book values, preserve as-of predictions, and add a tick without as-of.
(f) LF patterns: `tests/platformkit/ingame/fixtures/s475_*.json text eol=lf`,
`tests/platformkit/ingame/fixtures/s475_*.jsonl text eol=lf`, and the existing
`docs/evidence/forward/scoreboard/*.json text eol=lf`. The attributes are on master.
Before FIX 1a: `5 failed, 49 passed`. After FIX 1a: `56 passed`, zero skips.

## FIX 1b

Scope: exactly AMENDMENT 2(a)-(b). Only the owned facts probe, amendment test,
and this memo changed. The probe adds verify_landing, which reads committed
PREREG bytes, compares LF-normalised live identities, then calls the real verifier.
(a) BLOCKING 1 reproduced by replacing verify_amendment with sentinel_raise:
`PASS (sentinel never reached)` from the old post-landing test.
Replacement: commit the unchanged supplied PREREG and six live source files in
a temporary construct repository outside the worktree, read its committed PREREG,
and assert the six live LF hashes equal payload['implementation']. No BASE or
master comparison is used. The real verifier accepts clocks at 2026-09-29 UTC
midnight and 2026-10-05, refuses 2026-09-28 with amendment_not_effective, and
repeats after an unrelated 2026-09-30 commit. All six mutations refuse with
amendment_mismatch. The sentinel is now reached and its AssertionError asserted.
(b) Opus note 2 reproduced as `FAIL: AssertionError (unrelated registry-E identity change)`.
Removed the permanent registry-E identity comparison and its imports/base constant.
After: `PASS: original seal check ignores unrelated registry-E identity changes`.
One-off evidence command (output `<empty>`, exit 0):
`git diff 8fbc31112288e24a28501a361a48b6cd1779dbe6 -- scripts/platformkit/ingame/feature_registry.py scripts/platformkit/ingame/registry_adapters.py scripts/platformkit/ingame/registry_adapters_live_guard.py scripts/platformkit/ingame/registry_readers.py scripts/platformkit/execution/registry_scorer_e.py scripts/platformkit/execution/registry_scorer_e_fit.py scripts/platformkit/execution/registry_scorer_e_ticks.py scripts/platformkit/execution/registry_scorer_e_config.py scripts/platformkit/ingame/registry_adapters_lineup.py scripts/platformkit/ingame/mlb_lineup_registry_adapter.py`
FIX 1b per-file command: `python -m pytest tests/platformkit/execution/test_ingame_scoreboard_amendment.py -q -p no:cacheprovider`.
Result: `62 passed`, zero skips; covers the touched facts probe as well.
Contract preflight: all nine checks passed over 12 candidate paths, --base master
and --spec docs/evidence/tracking/specs/S475_spec.md; verdict file excluded.
All four row --help commands and baseline_four_arm --self-check passed again.
PREREG unchanged: payload SHA-256 171c0f5af1aff8d53b567859a24b20abb24e16e4ca72138ca8c4bccddaf358cc;
file SHA-256 6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e.
No JSON path was added. Existing LF patterns above still cover both fixtures and PREREG.

## Generated identity facts

<!-- S475 FACTS BEGIN -->
Base commit: 8fbc31112288e24a28501a361a48b6cd1779dbe6. Candidate commit: NOT CREATED (sandbox).
POLICY sha256: 81f345289874ebca07e3fe0dcf89337c19967397670399892fb18b015c7f1970.
Amendment sha256: 171c0f5af1aff8d53b567859a24b20abb24e16e4ca72138ca8c4bccddaf358cc.
Amendment effective_from: 2026-09-29T00:00:00.000000Z.

A9 identities (LF-normalised bytes and SHA-256; resolution: text, n/a).
| Full input path | Bytes | Lines | Candidate SHA-256 | Base SHA-256 | Comparison |
|---|---:|---:|---|---|---|
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/nights/2026-09-24.json | 7213 | 207 | 89010ca0ecc5af12e8d155f18da12e9f89ace1fa5a8a4472e1ac9afb4989c86e | 89010ca0ecc5af12e8d155f18da12e9f89ace1fa5a8a4472e1ac9afb4989c86e | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/nights/2026-09-25.json | 6202 | 199 | fec12c74bd26f04446c186bc38292f8bfe3af0398c28c520074d69ec947f91b6 | fec12c74bd26f04446c186bc38292f8bfe3af0398c28c520074d69ec947f91b6 | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/scoreboard/2026-09-24.json | 3443097 | 1 | 2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06 | 2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06 | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-25.json | 785 | 26 | 959ca04e325596334dc9120e509e4e1d3e6b95d68cab9af54433d0dab5add744 | 959ca04e325596334dc9120e509e4e1d3e6b95d68cab9af54433d0dab5add744 | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-29.json | 948 | 32 | cddcac1128e5318085906ff8fcf818ceb28ec3b07dc9da3c1f83184c4c47d0a9 | cddcac1128e5318085906ff8fcf818ceb28ec3b07dc9da3c1f83184c4c47d0a9 | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/scoreboard/PREREG_2026-09-24.json | 5046 | 1 | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | 6976e78aa68124fc8ca8663f215fc59a5bf6aab42c8ce54e477bbe3bf717c08b | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/scoreboard/PREREG_2026-09-24_superseded_2026-09-25.json | 4611 | 1 | 421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d | 421e080158f719296f357665b7997b4094dfc3b95717623c64e46072381dd45d | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/scoreboard/PREREG_2026-09-29.json | 2010 | 1 | 6ab00053d1f69843dc9ac118f1cb1aba86e3e98b049abae04e36329a8da1aa9e | ABSENT | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json | 1423 | 37 | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 | a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0 | EQUAL |
| C:/Users/neelj/nba-harness-h129/docs/evidence/ingame/S347_PREREG_SEALED_2026-09-21.md | 13964 | 204 | c408f17ec4f0847bec103ca7dd35e6b78ee0163cf34824e520c01fcc0c0ad5f3 | c408f17ec4f0847bec103ca7dd35e6b78ee0163cf34824e520c01fcc0c0ad5f3 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/eval_gate/walkforward.py | 8250 | 161 | 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 | 6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/ingame_scoreboard.py | 22181 | 298 | 2b1a21ac4e94cce0b30f0f04fd157c82b928b2d664fbce37008a52b48f4d352d | ba37c375ca62aee6b0eeb9b5cc502ec94c7cb6ad08f234e64990758ac2e85544 | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/ingame_scoreboard_amendment.py | 6972 | 148 | 2ccc83054d93c4eb098820c869fd66560f0990cebe318e11a8e8bf0ef0604a6b | ABSENT | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/ingame_scoreboard_rules.py | 6769 | 135 | 5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7 | 5a58a2217f19124a68d46e1c67f201d6ce051618f413ca9668cff7367bb36fc7 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/paper_night.py | 15420 | 285 | 52af33074768a030ddac06e921b6a459e3a85cb4cf82942d4a37c4ca571ed32a | 52af33074768a030ddac06e921b6a459e3a85cb4cf82942d4a37c4ca571ed32a | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/paper_night_deadline.py | 14592 | 293 | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | df800d4f9c0505bbf77b92b511ff67a66299e521133f8280fd33cc254f3ce66b | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/paper_night_lock.py | 1069 | 33 | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | 1da53a0f6a4beac259111e061e541caf780062f91002ba609a7baed2eb418ffa | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/paper_night_peak.py | 2378 | 52 | 54aa53505a688f7dac8baf45a4aed003c8919c245d908aaff1341f80e9cf77de | 54aa53505a688f7dac8baf45a4aed003c8919c245d908aaff1341f80e9cf77de | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/paper_night_steps.py | 14942 | 293 | 3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 | 3726297b7b400f016cff5f09cecf6d9c2cf3083ba552c1e2f5abbe8a1bc7c780 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/paper_sizing_inputs.py | 10882 | 233 | 33c43e8d58c50faa27a91fefd1a1bedcfff2427bf8b42196dbba002c65da5a60 | 33c43e8d58c50faa27a91fefd1a1bedcfff2427bf8b42196dbba002c65da5a60 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/registry_scorer_e.py | 17756 | 297 | 55c75aca523c2803dbc65af06a12d5192b613e284543e72d0e2daf24f6b4cdbd | 55c75aca523c2803dbc65af06a12d5192b613e284543e72d0e2daf24f6b4cdbd | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/registry_scorer_e_config.py | 10568 | 186 | a1cbff0b7ba34e20c6e61c0d66f3331be247446119ea60fc3c962888f09a2ee1 | a1cbff0b7ba34e20c6e61c0d66f3331be247446119ea60fc3c962888f09a2ee1 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/registry_scorer_e_fit.py | 10276 | 175 | b3dd16d88b82bc087ec7f4be40a931b76ac5c7fd5bffd78c6d2945a776ceb997 | b3dd16d88b82bc087ec7f4be40a931b76ac5c7fd5bffd78c6d2945a776ceb997 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/execution/registry_scorer_e_ticks.py | 12636 | 235 | fdd163cbf1455fa942ffe207a24819bd847eb746e61a43a7c48cc7c77e9ca0cf | fdd163cbf1455fa942ffe207a24819bd847eb746e61a43a7c48cc7c77e9ca0cf | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/baseline_four_arm.py | 17688 | 300 | dfa121c7e76028eb26d90b4c21746dfe6af895fcbd9aa800738d3d63bf92bdb2 | d416bbd6f1f8cceacde0f116a023b83a87090f1902bf921a33aed5a7c21666c9 | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/baseline_four_arm_eligibility.py | 11759 | 230 | d6a5fb4fd7bfbc99f7d7a93d981e0391f93fb0e62f39feb8369c31b9cd810032 | 068ddce3aec9fa89893e5dc6f329b88e824cdf91b5a9a4c3768d7dcb5c0a5228 | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/baseline_four_arm_features.py | 15466 | 300 | 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade | 8a3078627f7d57fd544af83ad1da4bdf4fa8c322f8e8bc11f2ad6b4c33154ade | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/baseline_four_arm_period.py | 16875 | 299 | 1fb9aa085c33c858a61884160706d4292ab70768500c777879b81c9d1f659791 | 1fb9aa085c33c858a61884160706d4292ab70768500c777879b81c9d1f659791 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/feature_registry.py | 11141 | 216 | 9366d847147567bfdf2e1cbe7c439ba080e665ba095a7ff0bd83703b10aeb3e9 | 9366d847147567bfdf2e1cbe7c439ba080e665ba095a7ff0bd83703b10aeb3e9 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/gate_a0_ingame_vs_market.py | 11748 | 299 | 1f917e06e92b69bebabaf0ecb6d8bfd2ffe8f7a8cc71415fbdea79c0224cfb13 | 1f917e06e92b69bebabaf0ecb6d8bfd2ffe8f7a8cc71415fbdea79c0224cfb13 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/intel_prior_arm.py | 10015 | 195 | 97c175b5fbcba46570d7943e200db9f8aab036b09e771254a71ea1bc07099d33 | 97c175b5fbcba46570d7943e200db9f8aab036b09e771254a71ea1bc07099d33 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/nba_four_arm_trial.py | 12108 | 223 | da7f0e9a6c031585571e4a2294065f76475db989028ea3fa7622f2964c953af3 | da7f0e9a6c031585571e4a2294065f76475db989028ea3fa7622f2964c953af3 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/nba_four_arm_trial_guards.py | 9711 | 220 | b933d19f1ce03cce677eaa038b4c63a81c440c23c7952af53364e0258513bc44 | b933d19f1ce03cce677eaa038b4c63a81c440c23c7952af53364e0258513bc44 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/registry_adapters.py | 14480 | 299 | 9bc35f4ae049d2707dfb57b4ffae024547d4b1a3f18233d6441b0346bac2a468 | 9bc35f4ae049d2707dfb57b4ffae024547d4b1a3f18233d6441b0346bac2a468 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/registry_adapters_lineup.py | 9631 | 202 | 6a83ce1c497d2eb0d4b716cb144274f988c71be1f91a3a07f146d318f98ed1f0 | 6a83ce1c497d2eb0d4b716cb144274f988c71be1f91a3a07f146d318f98ed1f0 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/registry_adapters_live_guard.py | 5040 | 94 | 30e70ba1f5212274747bd883395da4dcc4d121eefd298f6591e54afde31bbb1e | 30e70ba1f5212274747bd883395da4dcc4d121eefd298f6591e54afde31bbb1e | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/registry_readers.py | 3669 | 83 | 17e99577505a99c4687835b3d0812d9f90c7ca56b7406a57d72852fb47371ab3 | 17e99577505a99c4687835b3d0812d9f90c7ca56b7406a57d72852fb47371ab3 | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ingame/s359_four_arm_trial.py | 11414 | 219 | 6f7349e415cc1b3ceacfef1cadf5134a149de0dd810bf18ccb2c1c1d87edd5ee | 6f7349e415cc1b3ceacfef1cadf5134a149de0dd810bf18ccb2c1c1d87edd5ee | EQUAL |
| C:/Users/neelj/nba-harness-h129/scripts/platformkit/ops/probes/s475_memo_facts.py | 5933 | 131 | f25b048df4d651b7ed7c20d21f16ef32951b874a388d8491e95c5bc9e8e87bb9 | ABSENT | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/tests/platformkit/execution/test_ingame_scoreboard_amendment.py | 13571 | 298 | bc02dffbf19cede2443bdba399fd0664c42c1cd0e2fc0af7613938d1fe01d41c | ABSENT | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/tests/platformkit/execution/test_ingame_scoreboard_model_optional.py | 12481 | 222 | 39147ee66fe24aaeb82cea7dbf41f40d77c29f1052921bf65fa42fc8a3bce78b | ABSENT | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/tests/platformkit/ingame/fixtures/s475_default_route_snapshot.json | 41823 | 1 | ca76c0773827d9828182fa01c11cd1f89b3334c7b573dd08fdc7f91fa7c957d5 | ABSENT | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/tests/platformkit/ingame/fixtures/s475_mlb_state_row_2026-09-24.jsonl | 960 | 1 | 247e8ae4f8c5bb47347043ebe85dc83f0d6d34b6387bf0a25c49295362802fdb | ABSENT | NOT EQUAL |
| C:/Users/neelj/nba-harness-h129/tests/platformkit/ingame/test_baseline_four_arm_model_optional.py | 11093 | 238 | 3af2a9a8eb98768beec1c7c8d3ba80a8787633fc2c80f7cd6d5717dcf748ae3e | ABSENT | NOT EQUAL |
<!-- S475 FACTS END -->

## NOT VERIFIED

- The amendment's committed bytes and prospectivity against the actual landing
  commit. Construct commits used real git readers and fixed dates; actual landing
  before 2026-09-29T00:00Z remains the orchestrator's responsibility.
- S469 night-dated activation, S474 captured history, and any captured-night
  fitted output. The CLI remains inert. No calibration claim was tested.
- No real archive, network, pod, live execution, or sampled/measured corpus.
