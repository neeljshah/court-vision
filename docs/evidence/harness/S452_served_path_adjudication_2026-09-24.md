# S452 -- served-path player-props adjudication (REPORT ONLY)

STATUS: REPORT ONLY, nothing served changes; must-not-move (`src/**`,
`kernel/**`, `api/**`, `intel/**`, `scripts/team_system/**`,
`data/rest_travel.parquet`, `data/domains/**`, `docs/JOB_EVIDENCE_PACKET.md`)
diff vs master is empty (case 6). Worktree HEAD after FIX 1c's fast-forward
`f5f2a59320dbdb3c80317bcb0d994a8dfc459cc0` equals the main repo `master`
(FIX 1c) -- no drift.

Built: `served_path_adjudication.py` (`classify_trainer_synthetic`,
`rest_travel_statements`, `stitch_router_binding_proof`) and its test file
(15 tests, CONSTRUCT-only). No production loader is imported/executed;
every check reads source text, AST, or parquet footer metadata only.

## Before-condition (S2: re-verified this session, all facts OBS, no drift)

`player_props.py:2587-2591 _maybe_flag_fallback`; `:2649 _build_prop_training_frame` (RNG `:2692,:2706,:2713,:2729`, constant `:2732`); `prop_pergame.py:5232 build_prediction_row` (`_get_opponent_defense` `:5269`, `_REST_TRAVEL_DEFAULTS` unconditional `:5271`); `:1425` defaults, `:1446 build_rest_travel`; `api/stitch_router.py:134 predict_props(player_id, season)`; `player_props.py:2235-2242 def predict_props(player_name, opp_team, season="2025-26", n_games=10, ref_names=None, game_id=None)`.

## The 6 enumerated CONSTRUCT cases (ACCEPTANCE RULE, n = 6)

All 6 pass; 9 supporting/regression tests also pass (15/15 total,
`python -m pytest tests/platformkit/eval_gate/test_served_path_adjudication.py
-q -p no:cacheprovider`).

1. `classify_trainer_synthetic(player_props.py, 2690, 2731)` -> `synthetic=True`, 21 tokens (>= 3 required); full list in `case1_trainer_synthetic` below.
2. `classify_trainer_synthetic(prop_pergame.py, 5266, 5341)` -> `synthetic=False`, 0 tokens (`case2_pergame_real` below).
3. `rest_travel_statements` (AMENDMENT 1a): fixture proves `is_b2b`/`miles_traveled`/`altitude_ft` MISMATCH on a nonzero value vs the served zero default, `is_b3b` MATCH at zero range, joined 2024-25 shift always `INSUFFICIENT` -- never passing. A 2nd fixture: all-zero always MATCH.
4. `stitch_router_binding_proof` (AMENDMENT 2a/c): call SELECTED inside `get_player_props` only (not first-matched file-wide); 0/>1 candidates refuse `duplicate_call_sites`. Parameters via `inspect.signature` on a loader-safe stub from ONLY the parsed def node (no `src.prediction` import ever runs, proven by a raising-import test). `stub_params`/`ast_params` agree; full result in `binding_proof` below. A reordered-decoy construct selects the same call regardless of position.
5. PREMISE (c)/AMENDMENT 1b packet-grep reproduces byte-for-byte: `docs/JOB_EVIDENCE_PACKET.md` (321 lines) has exactly 2 "synthetic" hits (line 59 court-test, line 96 in-game fixture, neither props); 0 hits for trainer/season-grain/season_avg/per-game-feature; `KNOWN_LIMITATIONS.md` (235 lines) has 0 "synthetic" hits.
6. `git diff --stat master -- src api kernel intel scripts/team_system docs/JOB_EVIDENCE_PACKET.md` is empty, reproduced as a pytest case and on the command line.

## Real-featured is NOT as-of-safe (AMENDMENT 1d/2b, stated separately)

Case 2's real-featured finding proves NOTHING about as-of safety:
`player_props.py:1034-1061` and `prop_pergame.py:5232`/`:5260` take no
target-date argument -- listed under NOT VERIFIED, no claim made.

## PROPOSED packet wording change (item v) -- none needed

Case 5 found no live overbroad sentence in either checked file, so none is
proposed per item (v)'s own condition.

## A9 -- exact source identities (regenerated last, base sha f5f2a59320dbdb3c80317bcb0d994a8dfc459cc0)

SHA-256 of LF-normalised bytes, recomputed fresh as this memo's last edit
(FIX 1c, after the fast-forward to `f5f2a59320dbdb3c80317bcb0d994a8dfc459cc0`).
All five are byte-identical across every round -- none of these files
changed; only the spec moved at the tip.

| path | bytes | sha256 (LF-normalised) |
|---|---|---|
| `C:\Users\neelj\nba-harness-h106\src\prediction\player_props.py` | 144670 | a4a2dea55282575696767560dec0c13d0b99a1a0b6864cfb3fe9b56bd96740a3 |
| `C:\Users\neelj\nba-harness-h106\src\prediction\prop_pergame.py` | 257053 | ef0f18f375a5b075228494d31ce6f054a37dbd8885ccac191513237d91d53421 |
| `C:\Users\neelj\nba-harness-h106\api\stitch_router.py` | 10823 | ecb84687dc080b6c980d294929aa6beae8c73739b4fe78e30a35a49e53f86646 |
| `C:\Users\neelj\nba-harness-h106\docs\JOB_EVIDENCE_PACKET.md` | 67898 | 3bdcaa0b7d38bce8420c0bfd25a2c036cccf8c2dae633e40a70deada3ef7ad46 |
| `C:\Users\neelj\nba-harness-h106\docs\KNOWN_LIMITATIONS.md` | 11751 | 9b0bf88d67119f1f0e6560bf8cb69b7b779977e4ca7c017fb0d43605df838cee |

`data/rest_travel.parquet`: NOT VERIFIED at landing (absent in the worktree); REAL RUN 1 (main tree, 2026-09-25, orchestrator): sha256 `20ba8ffbc78bd0e1131677ffbc3ab261df18810fbb1a6f7dd554cd23f58d57ba`, 95060 bytes, 12156 rows, one row group, seven columns -- artifact `docs/evidence/forward/served_path/2026-09-25_rest_travel_statements.json`
(harness worktrees don't carry the main repo's gitignored `data/`; per
worktree isolation, no old git blob or main-repo read was attempted). Real
per-column statement + A9 sha256 both NOT VERIFIED; correctness proven on
CONSTRUCT fixtures instead (case 3); joined shift is INSUFFICIENT by design.

## Reproduction: canonical CLI payload (AMENDMENT 3b)

`json.dumps(run_all(), indent=1, sort_keys=True, allow_nan=False)`, UTF-8
encoded, is **3666 bytes**, sha256
`645b57c827feaa34e7ee1887a0ce85343bd7e335381b590656fbc7d96efcfb3a`, recorded
verbatim below (no trailing newline); two independent runs matched.

```json
{
 "binding_proof": {
  "ast_params": [
   "player_name",
   "opp_team",
   "season",
   "n_games",
   "ref_names",
   "game_id"
  ],
  "bindings": [
   {
    "call_arg": "player_id",
    "param": "player_name",
    "position": 0
   },
   {
    "call_arg": "season",
    "param": "opp_team",
    "position": 1
   }
  ],
  "call_line": 134,
  "call_positional_args": [
   "player_id",
   "season"
  ],
  "callee_line": 2235,
  "callee_path": "C:\\Users\\neelj\\nba-harness-h106\\src\\prediction\\player_props.py",
  "caller_name": "get_player_props",
  "func_name": "predict_props",
  "mismatch": true,
  "numerical_impact": "NOT VERIFIED -- not measurable without executing a production loader; the opponent-defence factors may return identical neutral values across differing inputs in that slot",
  "params_agree": true,
  "router_path": "C:\\Users\\neelj\\nba-harness-h106\\api\\stitch_router.py",
  "stub_error": null,
  "stub_params": [
   "player_name",
   "opp_team",
   "season",
   "n_games",
   "ref_names",
   "game_id"
  ]
 },
 "case1_trainer_synthetic": {
  "line_hi": 2731,
  "line_lo": 2690,
  "matched_tokens": [
   {
    "line": 2690,
    "text": "simulate",
    "token": "word"
   },
   {
    "line": 2690,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2691,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2692,
    "text": "np.random.default_rng",
    "token": "default_rng"
   },
   {
    "line": 2697,
    "text": ".normal(",
    "token": "normal_call"
   },
   {
    "line": 2697,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2698,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2705,
    "text": "simulate",
    "token": "word"
   },
   {
    "line": 2705,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2706,
    "text": "np.random.default_rng",
    "token": "default_rng"
   },
   {
    "line": 2709,
    "text": ".normal(",
    "token": "normal_call"
   },
   {
    "line": 2709,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2710,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2712,
    "text": "simulate",
    "token": "word"
   },
   {
    "line": 2712,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2713,
    "text": "np.random.default_rng",
    "token": "default_rng"
   },
   {
    "line": 2715,
    "text": ".normal(",
    "token": "normal_call"
   },
   {
    "line": 2715,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2716,
    "text": "noise",
    "token": "word"
   },
   {
    "line": 2729,
    "text": "np.random.default_rng",
    "token": "default_rng"
   },
   {
    "line": 2730,
    "text": ".choice(",
    "token": "choice_call"
   }
  ],
  "path": "C:\\Users\\neelj\\nba-harness-h106\\src\\prediction\\player_props.py",
  "synthetic": true,
  "token_count": 21
 },
 "case2_pergame_real": {
  "line_hi": 5341,
  "line_lo": 5266,
  "matched_tokens": [],
  "path": "C:\\Users\\neelj\\nba-harness-h106\\src\\prediction\\prop_pergame.py",
  "synthetic": false,
  "token_count": 0
 },
 "rest_travel": {
  "reason": "data/rest_travel.parquet not present in this worktree: [WinError 2] Failed to open local file 'C:/Users/neelj/nba-harness-h106/data/rest_travel.parquet'. Detail: [Windows error 2] The system cannot find the file specified.",
  "status": "INSUFFICIENT"
 },
 "rest_travel_sha256": {
  "reason": "data/rest_travel.parquet not present in this worktree: [WinError 2] Failed to open local file 'C:/Users/neelj/nba-harness-h106/data/rest_travel.parquet'. Detail: [Windows error 2] The system cannot find the file specified.",
  "status": "INSUFFICIENT"
 }
}
```

Extraction + diff, pure Python so it needs no OS temp dir and never goes
through a text-mode pipe/redirect (the CRLF/trailing-newline trap that broke
an earlier sed-based draft of this same recipe -- self-tested this session):

```
python -c "import re,json,pathlib; from scripts.platformkit.eval_gate.served_path_adjudication import run_all; m=pathlib.Path('docs/evidence/harness/S452_served_path_adjudication_2026-09-24.md').read_text(encoding='utf-8'); recorded=re.search(r'```json\n(.*?)\n```', m, re.S).group(1); fresh=json.dumps(run_all(), indent=1, sort_keys=True, allow_nan=False); print('BYTE_IDENTICAL' if recorded==fresh else 'MISMATCH len_recorded=%d len_fresh=%d'%(len(recorded),len(fresh)))"
```

## FIX 1b (AMENDMENT 2) -- round 1 (2 blocking, 2 correction), fixed

(a) proof was AST-only, rejected `inspect.signature` -> loader-safe stub
from the parsed def node, `stub_params`/`ast_params` agree; (b) no separate
as-of-safety disclosure -> dedicated section above + NOT VERIFIED; (c)
order-independence test compared identical output to itself -> selection
scoped inside `get_player_props`, refuses `duplicate_call_sites` on 0/>1
candidates, a reordered-decoy construct now varies the input (case 4); (d)
float/bool line bounds were truncated via `int()` -> `_require_int_bound`
refuses them with a reason.

## FIX 1c (AMENDMENT 3) -- round 2 (1 blocking, 1 correction), memo only

No `.py` changed. (a) NOT VERIFIED wasn't the final section -> every FIX
section now precedes it. (b) no canonical payload was recorded -> the
payload section above has the exact 3666-byte string, sha256, and
extraction/diff one-liner; FIX 1b's prose was trimmed to fit under 300
lines. (c) worktree HEAD and `git -C .../nba-ai-system rev-parse master`
both read this session: `f5f2a59320dbdb3c80317bcb0d994a8dfc459cc0` -- EQUAL,
recorded as fact, not a claim that master moved.

## NOT VERIFIED (honest list, final section)

- Real per-column `rest_travel.parquet` statistics and its A9 sha256 -- absent in the
  worktree at landing; RESOLVED by REAL RUN 1 from the main tree (2026-09-25, orchestrator,
  metadata-only, no column payload decoded): is_b2b MISMATCH (max 1.0), miles_traveled
  MISMATCH (max 2704.4), altitude_ft MISMATCH (min 3.0, max 5183.0) against the served
  all-zero default; is_b3b MATCH (all zero). Every other run_all key agrees with the recorded
  payload except the two absolute path fields. Artifact:
  `docs/evidence/forward/served_path/2026-09-25_rest_travel_statements.json`.
- The joined 2024-25 row-level shift (real, decoded) -- metadata-only scope
  by design; holdout corpus location never identified.
- Numerical impact of the season-as-opponent mis-binding on actual
  predictions -- opponent-defence factors may return identical values.
- Whether the alleged "props trainer is synthetic" packet sentence exists
  outside the two files checked.
- Whether `player_id`->`player_name` mis-binding (position 0) has any
  measurable effect -- out of scope by NON-TAUTOLOGY.
- Historical as-of safety of `build_prediction_row`/`_build_player_features`
  -- real-featured is not as-of-safe; neither takes a target-date argument.
- Any real corpus, production loader, network access, or trial-record run --
  all prohibited, none attempted.
