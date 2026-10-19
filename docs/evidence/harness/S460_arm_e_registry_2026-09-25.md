# S460 Arm E Registry Construct Memo (FIX 1k)

Verdict: NOT VALIDATED. Local construct build only; no scored night, no real
corpus, no charged trial. This round applies AMENDMENT 12 (round 10 on fix
1j: codex sol REJECT, one blocker, one correction, one note; Opus tier 2
ACCEPT WITH CORRECTIONS, one correction, two notes -- reconciled by the
amendment, which wins on any difference). BOTH tiers confirm AMENDMENT 11
(a)-(e) CLOSED by probe, so **the row's CODE is verified and unchanged this
round** -- only this memo and four sibling-import test modules change: (a)
the condensed memo restores every AMENDMENT 9(c)/10(c) disclosure the FIX
1j condensation dropped; (b) the guard-vs-`select_causal` disagreement on
`strict_earlier` blocks is disclosed with its reproduction, not hidden, and
the test comments overclaiming "S431 would count it" are corrected; (c) the
four bare sibling test imports become full `tests.platformkit.execution.*`
imports; (d) two memo citations corrected; (e) no reseal -- no sealed file
or production module changed this round. Prior-round detail (FIX 1c-1j) is
condensed below; the full narrative is in `docs/evidence/tracking/specs/
S460_spec.md`'s AMENDMENT 4-12 blocks, not repeated here.

## A9: candidate HEAD and verification base

FIX 1k (this round): `git merge --ff-only master`, re-run at lane start per
the worktree rule, reported "Already up to date". HEAD:
`9340b0e34b88984f84153b532f936a3f283d455f`. Master:
`9340b0e34b88984f84153b532f936a3f283d455f`. EQUAL -- master advanced past
FIX 1j's HEAD by unrelated register commits since (drift, not a finding);
this row's own code is UNCHANGED this round, so the diff over the owned and
must-not-move paths is still empty.

Historical: FIX 1j HEAD and master were both
`f378ae6c69a7dd7e8920e4687c764e0ce6193ed2` -- EQUAL; FIX 1i both
`ec0e3fd097d0d798ea2897ea22e20533f548e161` -- EQUAL; FIX 1h both
`d0c21a5f2731fa204461023d9a48a8e4998a51ce` -- EQUAL.

## A9: owned files (LF-normalised sha256, disk bytes, lines) -- regenerated LAST

Every hash below is `sha256` of the file's bytes with `\r\n` normalised to
`\n` before hashing. Every one of the 22 rows is LF on disk already (no `\r`
byte anywhere this session), so for every row the LF-normalised hash equals
a sha256 of the file's raw bytes: no row here is ambiguous.

| File | LF-norm sha256 | Bytes | Lines |
|---|---|---|---|
| `scripts/platformkit/ingame/feature_registry.py` (unedited) | `406b551979...c1ebb23` | 8476 | 173 |
| `scripts/platformkit/ingame/registry_adapters.py` (unedited, 298/300) | `56a6494a38...50f19de` | 14319 | 298 |
| `scripts/platformkit/ingame/registry_adapters_live_guard.py` (unedited this round) | `30e70ba1f5...31bbb1e` | 5040 | 94 |
| `scripts/platformkit/ingame/registry_readers.py` (unedited) | `17e9957750...7371ab3` | 3669 | 83 |
| `scripts/platformkit/execution/registry_scorer_e.py` (unedited) | `5b025668f8...d89802f` | 15421 | 260 |
| `scripts/platformkit/execution/registry_scorer_e_fit.py` (unedited this round) | `b3dd16d88b...6ceb997` | 10276 | 175 |
| `scripts/platformkit/execution/registry_scorer_e_ticks.py` (unedited) | `25cde64305...b41631b` | 11719 | 219 |
| `scripts/platformkit/execution/registry_scorer_e_config.py` (unedited) | `36b3e1de41...7180267` | 5498 | 97 |
| `tests/platformkit/ingame/test_feature_registry.py` (unedited) | `ea56cadd81...23bc980` | 5760 | 135 |
| `tests/platformkit/ingame/test_registry_adapters.py` (unedited) | `47c2d4bd64...764d38c` | 17612 | 298 |
| `tests/platformkit/ingame/test_registry_adapters_1d.py` (unedited) | `ff2f7d46bd...1dacffe` | 6891 | 124 |
| `tests/platformkit/ingame/test_registry_adapters_1g.py` (FIX 1k: docstring + comment corrected, no assertions changed) | `c6f0765a9f...c80811e` | 13295 | 240 |
| `tests/platformkit/ingame/test_registry_readers.py` (unedited) | `d11dcd96df...5b2ea17` | 7405 | 166 |
| `tests/platformkit/execution/test_registry_scorer_e.py` (unedited) | `b849047d4d...112c9c5` | 15644 | 300 |
| `tests/platformkit/execution/test_registry_scorer_e_1d.py` (FIX 1k: bare import -> full path, no assertions changed) | `8e9c822c41...783ddf5` | 12584 | 243 |
| `tests/platformkit/execution/test_registry_scorer_e_1e.py` (FIX 1k: bare import -> full path, no assertions changed) | `1a664524da...c17f678` | 14382 | 270 |
| `tests/platformkit/execution/test_registry_scorer_e_1f.py` (FIX 1k: bare imports -> full path, no assertions changed) | `ad28122551...92163f1` | 12322 | 231 |
| `tests/platformkit/execution/test_registry_scorer_e_1g.py` (FIX 1k: bare imports -> full path, no assertions changed) | `572b0d323c...0edf77a` | 3867 | 71 |
| `tests/platformkit/execution/test_registry_scorer_e_fit.py` (unedited this round) | `07c7a39a8d...7d4ee80` | 15598 | 273 |
| `tests/platformkit/ingame/fixtures/s460_real_row.json` (unedited) | `a828c163d5...ae993f8` | 1782 | 49 |
| `docs/evidence/forward/scoreboard/PREREG_E_2026-09-25.json` (byte-identical, unedited) | `a747aab248...c8744a0` | 1423 | 37 |
| `docs/evidence/forward/scoreboard/BLOCK_CONFIG_E_2026-09-25.json` (byte-identical, unedited this round) | `959ca04e32...5add744` | 785 | 26 |

Full 64-char hexdigests are on disk; this table truncates for rendering
only. Regenerated as the LAST edit this round, after every text change
above; re-read once more after regeneration to confirm every row equals
the file on disk. No sealed file changed this round, so the two seal rows
above are byte-identical to FIX 1j, not merely hash-identical by luck.

Spec measured against: `docs/evidence/tracking/specs/S460_spec.md`, 78
lines on disk this session, ending in **AMENDMENT 12**.

## Registry seals: PREREG_E + BLOCK_CONFIG_E (both byte-identical, no reseal this round)

PREREG_E: byte-identical this round (unchanged since round 4). Its own
INNER seal field (the `sha256` key inside the JSON body) stays
`2430c81e4c6cf52afd16e88963a03e8c2bdbbe97af5d167177175d70053d7416` -- that
is NOT the file's own hash. The FILE's own sha256 (matching the A9 table
row above) is
`a747aab2489afbdc823e8f28d49ca28520f50ccd8ea3f72bf44976f0ec8744a0`,
unchanged since round 9.

BLOCK_CONFIG_E: `selected_blocks`, `selected_block_versions`,
`manifest_hash` (`6a94c03bf7385b63ecb15d3241a5205f99bc711fabfc84a04b2ec012
a4447f4b`), `effective_from` (`2026-09-25T00:00:00.000000Z`),
`implementation_identity` (`a2e279f65b4891bf41dc3930d53cf7dc0f35c686d8ae
b0dfc642b6f26df49218`) and the outer seal
(`26a4657b39bf186e9748218cdfa50869414c5a19f802e73386369f5b34812267`) are
ALL UNCHANGED from FIX 1j: this round edits no `IMPLEMENTATION_FILES`
member, so there is nothing to reseal. FIX 1j's own reseal history
(before/after identities, the reason, the round-tripped
`load_block_config` check) is unchanged and not repeated here. Both seals
verified via `load_prereg`/`load_block_config` with `git_committed`
monkeypatched (real git-backed verification is NOT VERIFIED until landing,
this sandbox has no committed seal to check against).

## FIX 1c-1j (prior rounds, condensed -- full detail in spec AMENDMENT 4-11)

- FIX 1c (round 2, AMENDMENT 4): case-19 completeness, C's fields/training
  support, the raw shard reader, freshness per block, full policy
  validation, `out_of_order` ordering, per-receipt dedup, a
  retracted-figure token, a `role=='train'` label-poisoning guard.
- FIX 1d (round 3, AMENDMENT 5): tick-stream S431 dedup, `(game_key,
  ticker)` collapse, sealed-policy validation, ticker identity, `PREREG_E`
  split into two seals.
- FIX 1e (round 4, AMENDMENT 6): settlement derived ONLY from a game's own
  `final` receipts, complete sealed-policy typing, no look-ahead in
  `_any_mlb_live_ever`, `BLOCK_CONFIG_E` version map + seven-module
  identity, Decimal `paired_losses`, a >=5-game reconstruction.
- FIX 1f (round 5, AMENDMENT 7): the real perturbation construct;
  numeric-epoch timestamps refused; `selected_blocks` typed exactly;
  malformed seal files map to a named refusal; `clusters`/`train_games`
  keyed by `game_key`.
- FIX 1g (round 6, AMENDMENT 8): every non-string live-feed timestamp
  refuses via the new sibling `registry_adapters_live_guard.py`; the
  first-scorable-night finding first stated (resolved 1i/1k below).
- FIX 1h (round 7, AMENDMENT 9): the `BLOCK_CONFIG_E` seal covers the WHOLE
  implementation (AST import-closure regression); the numeric-final
  regression asserts the exact census refusal; every owned file made LF.
- FIX 1i (round 8, AMENDMENT 10): an absent E-only field never erases C;
  the guard's `_causal_prefix` bounded to the max at-or-before-event index
  over the WHOLE list (round 9 found this still wrong, see FIX 1j);
  AMENDMENT 10(c) first stated the disclosures restored in full below.
- FIX 1j (round 9, AMENDMENT 11): `_causal_prefix` returns EMPTY (never
  include-all) when no well-formed row is at-or-before the event; the scan
  runs in FILE ORDER and stops at the first well-formed row past the event
  (round 10 found this right for the guard but in disagreement with
  `select_causal`, see FIX 1k); the malformed-tail regression asserts the
  EXACT census difference; the C refit refuses `c_field_not_e_field` by
  name; reseal (identity `a2e279f6...`, outer seal `26a4657b...`, both
  unchanged this round).

### Prospective run status (AMENDMENT 9(c)/10(c) disclosures, restored)

The first-scorable-night paragraph CHOOSES this row's own path rather than
listing both, per AMENDMENT 8(c)'s "declared before the run" rule: this row
waits for the sealed `PREREG_E`'s **n_games floor of 30 post-seal games**
under the COMMITTED `BLOCK_CONFIG_E` seal (the honest prospective path) --
the real run is **BLOCKED-ON-FLOOR** until 30 post-seal games exist under
that committed seal (the count of post-seal games available right now is
NOT VERIFIED in this construct-only sandbox; see NOT VERIFIED below). A NEW
committed config is declared ONLY if the scored-night selector (S469/S470,
register-wide) lands first, and NEVER as a backdated seal against games
already played -- no-backdating is a hard rule, not a preference. The
out-of-order earlier-row case (a row stamped 10s arriving in the file
before one stamped 08s, with `effective_from` at 09s) is disclosed: the
S431 dedup stream drops the 08s row as `out_of_order` and the run is still
accepted, consistent with "deduplicated" because nothing before
`effective_from` is scored regardless of dedup order. Register gap (not
this row): `effective_from` (`2026-09-25T00:00:00.000000Z`) precedes the
seal file's own write time, and `git_committed()` only checks that the seal
bytes are committed, not WHEN -- a commit-time floor for `effective_from`
is not enforced anywhere in this row's path; carried to the scored-night
selector (S469/S470) register-wide, not fixed here.

## FIX 1k: this round's verifier findings and what changed

Round 10 (AMENDMENT 12) found the row's CODE verified and unchanged; every
finding below is a MEMO or TEST-MODULE fix only -- no production module and
neither seal file was edited this round.

**(a) condensed memo restores every AMENDMENT 9(c)/10(c) disclosure (codex
sol BLOCKING)** -- a search of the FIX 1j memo for `post-seal`, `declared
before the run`, `backdat`, `scored-night selector`, `commit-time` and
`30-game` returned nothing: the FIX 1j condensation pass dropped the whole
paragraph. Restored above under "Prospective run status", in substance,
within the 300-line cap. This memo is measured at its own disk line count:
**300 lines**.

**(b) guard-vs-`select_causal` disagreement disclosed, not hidden (Opus
tier 2, CORRECTION)** -- every guard caller (`live_feed`,
`player_encounter_count`, `team_bullpen_usage`) is a `strict_earlier`
block. `select_causal`'s strict branch (`registry_adapters.py:104-125`, the
S434 policy) sorts by `(instant, canonical JSON)` and KEEPS every row whose
own instant is before the event in `prior`, only COUNTING a late,
out-of-order row `out_of_order` as a diagnostic -- it never drops the row.
This guard's `_causal_prefix` (`registry_adapters_live_guard.py:46-69`)
instead scans in FILE ORDER and STOPS at the first well-formed row past the
event, DROPPING that same late row from its own prefix: the two
causal-prefix definitions disagree on which rows are in scope for a
`strict_earlier` block. Reproduction (constructs, this session): `[T5,
T30, T6-with-mlb_live, T7]` -> `select_causal` selects `T7` while the guard
returns `False` and `player_encounter_count` counts
`model_not_reconstructible`; `[T30, T10-live]` refuses
`block_absent:live_feed` while the SAME rows reordered `[T10-live, T30]`
refuse `feature_receipt_after_tick` instead (the label depends on file
order); `[T5, T30]` plus an appended `T6` live row makes `live_feed`
return OK with census `{out_of_order: 1, present: 3}` while the guard
still returns `False`. NOT BLOCKING: the guard keeps its own AMENDMENT
10(b) append-invariance, and the scorer never branches on the three
refusal/counter labels above -- only a diagnostic moves, never a scored
value. Fixed: `test_registry_adapters_1g.py`'s
`test_amendment11b_out_of_order_late_row_never_extends_the_boundary`
docstring and closing comment both wrongly claimed "S431 would count it
out_of_order" (wrong policy -- S431 is the unused non-strict
`at_or_before` -- and wrong claim: S434 counts AND KEEPS the row); both
now name `select_causal`'s `strict_earlier` (S434) branch and say it
keeps the row. Escalated to NEW GAPS below.

**(c) test modules import by full path (codex sol CORRECTION)** --
`test_registry_scorer_e_1d.py:22`, `_1e.py:21`, `_1f.py:24-25` and
`_1g.py:18-19` used bare sibling imports. Reproduced verbatim before the
fix: `python -c "from tests.platformkit.execution.test_registry_scorer_e_1e
import _policy"` raised `ModuleNotFoundError: No module named
'test_registry_scorer_e'`. All four now import via
`tests.platformkit.execution.test_registry_scorer_e[...]`; passing after:
`python -c "import tests.platformkit.execution.test_registry_scorer_e_1e"`
exits 0.

**(d) two citations corrected (Opus tier 2, NOTEs)** -- "Registry seals"
named `2430c81e...` a bare "sha256" without saying it is PREREG_E's INNER
seal field, not the file's own hash (now stated above, with the file's own
sha256 `a747aab2...` alongside it); the FIX 1j history above no longer
cites `registry_adapters_live_guard.py`'s line range at all -- the only
citation of that range is item (b) above, correctly `:46-69` (the FIX 1j
draft had cited `:30-52`).

## NEW GAPS (register, not this row)

- `NEW GAP:` one shared causal-prefix helper for `select_causal` and the
  live guard, so a `strict_earlier` block's causal window is defined once,
  not twice with different semantics (item (b) above; reproduction there).
- `NEW GAP:` whether `strict_earlier` should KEEP an out-of-order receipt
  at all, given the AMENDMENT 10(b) append-invariance rule the guard
  already obeys -- today `select_causal` keeps it and the guard drops it,
  and neither has been declared the intended behaviour.
- `NEW GAP:` a whole-night append-invariance test exercising a real
  out-of-order, well-formed live row through both `select_causal` and the
  guard end to end (today only the constructs above cover it).
- Carried from AMENDMENT 9/10/11 (register-wide, not this row): a
  commit-time floor for `effective_from`; the scored-night selector
  (S469/S470); settlement derivation as one shared helper; `select_causal`
  re-implementing `dedupe_first`; a real multi-game CLI replay with
  `reader_census`; the numeric-epoch refusal in one shared instant parser.

## Case coverage / test counts

130 `def test_` functions in 150 collected pytest items across the ELEVEN
owned test files -- UNCHANGED this round (FIX 1k edits comments, docstrings
and import paths only, never an assertion or a test's existence), re-run
individually this session after the FIX 1k edits: `test_feature_registry.py`
16/16 + `test_registry_adapters.py` 19/21 + `test_registry_adapters_1d.py`
5/5 + `test_registry_adapters_1g.py` 9/12 + `test_registry_readers.py`
12/12 + `test_registry_scorer_e.py` 17/17 + `test_registry_scorer_e_1d.py`
12/20 + `test_registry_scorer_e_1e.py` 11/13 + `test_registry_scorer_e_1f.py`
11/16 + `test_registry_scorer_e_1g.py` 3/3 + `test_registry_scorer_e_fit.py`
15/15 -- identical to FIX 1j's own counts. Functions via `ast.walk`;
collected via `pytest --collect-only`; gap is `@pytest.mark.parametrize`
expansion. Neighbour suites `test_baseline_four_arm.py` (53) and
`test_ingame_scoreboard.py` (43) NOT re-run (neither file touched); `git
diff --stat master` over both and their five source modules plus
`eval_gate/walkforward.py` and `eval_gate/state_key_guard.py` confirms
byte-identical (empty diff, exit 0). `contract_preflight` 9/9 PASS over the
full 23-path owned set (22 owned files plus this memo), re-run after every
edit and again after this memo's final edit. The must-not-move diff is
empty against master. `git status --porcelain`: identical to the pre-round
status (23 untracked owned paths, zero tracked modifications).

## NOT VERIFIED

- No real archive, network, pod, or production caller was exercised; every
  test is a construct or the single real state-shard row fixture.
- No book/tape shard rows were read from a real captured shard end to end
  through `registry_readers.read_jsonl`.
- `freshness_seconds` (21248.002449s) remains declared sealed-only; the
  VALUE itself was not re-derived this round.
- The FIX 1f perturbation construct is a local, monkeypatched-git
  construct over in-memory games; never run against a real multi-night
  corpus or a committed `BLOCK_CONFIG_E`. Its 0.1 delta threshold is this
  lane's own choice, not spec-numeric.
- No prospective sealed-night run, ledger charge, second corpus, FWER
  interaction, or FWER budget draw was exercised.
- Filesystem interruption recovery for the atomic CLI write was not
  exercised (the `os.replace` pattern is reused unedited).
- The `reader_census` construct uses tmp-file shards, not a real captured
  archive line beyond the one mirrored fixture.
- `block_config_not_effective` counts into `block_census["_stream"]`
  before raising, but since the refusal aborts `score()` before any value
  is returned, that count is only verified by the raise itself in this
  session's construct -- never observed in a written/returned census.
- The count of real post-seal games available right now is NOT VERIFIED in
  this construct-only sandbox (no real shard archive access); the
  BLOCKED-ON-FLOOR statement (restored this round, unchanged in substance
  since FIX 1h/1i) is a policy/derivation fact, not a fresh corpus scan.
- `git_committed()` against the real, on-disk seal files still returns
  False in this sandbox; real git-backed verification of
  `implementation_identity` is NOT VERIFIED until landing.
- `c_field_not_e_field` is unreachable under the sealed config (all seven
  blocks selected pins `e_fields` as a superset of `C_FIELDS`); this round
  never exercised it against a real, narrower selected-block set.
- The FIX 1k guard-vs-`select_causal` disagreement (item (b) above) was
  reproduced only via in-memory constructs (2-4 row lists), never against
  a real multi-game night's full receipt stream.
- `git` itself was NOT denied in this sandbox this round (`git merge
  --ff-only master` and `git status --porcelain` both ran); no commit was
  made regardless, per the lane rule (files left on disk for
  `lane_commit`).
