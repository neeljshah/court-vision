# S467 build memo: MLB lineup, batting order, pitcher hand, appearance ledger

BUILD RESULT: FIX 1h applies S467 AMENDMENT 8 (a)-(d) over round-7's combined verdict --
codex sol REJECT (one blocking, one correction, one note) and Opus tier 2 ACCEPT WITH
CORRECTIONS (five corrections, one note), combined in the host temp file
`_verdict_S467_r7_combined.md` (itself made of `cx_s467_verify7_out.md` and
`_verdict_S467_opus7.md`). All owned tests green
(18/15/4/19/16/6/7/13/8), preflight 9/9 over 18 paths, must-not-move empty, flag off clean.

Worktree `C:/Users/neelj/nba-harness-h120` (branch `harness-h120`). Construct-only; no network,
no real archive, no pod. NEW sibling test file `test_mlb_lineup_state_1h.py` (116 LOC) holds
every AMENDMENT 8 construct -- `test_mlb_lineup_state.py` (300 LOC) is at its own budget, so new
AMENDMENT 8 cases go in a new sibling, not the 1g file or inline.

## STEP 0 PREMISE CHECK (this FIX 1h session, before any edit)

`test_mlb_lineup_state.py` 18, `_1c` 15, `_1d` 4, `_1e` 19, `_1f` 16, `_1g` 6, `test_mlb_lineup_
registry_adapter.py` 13, `test_mlb_lineup_census.py` 8, `test_mlb_live_feed_state.py` 73,
`test_local_state_capture.py` 19 passed -- matches `_verdict_S467_r7_combined.md` VERDICT 2's own
host facts exactly. Reproduced the two BLOCKING/CORRECTION findings on the pre-edit candidate before
touching any file:
- VERDICT 1 item 1 (BLOCKING, `_merged_ledger`): a standalone reconstruction of the pre-edit
  function body (the candidate files are UNTRACKED, so `git stash` cannot restore them; the old
  body was taken verbatim from this session's own first read of the file) gave
  `_merged_ledger({'appearances_ledger_home': None}, [])` -> `(None, False)`, `reasons=[]` --
  matching the verdict's own `output=[null, false], reasons=[]` exactly.
- VERDICT 2 finding 6 (`path.is_file()` outside the OSError boundary): a standalone
  reconstruction of the pre-edit loop body, run with a `Path` subclass whose `is_file()` raises
  `PermissionError(13, 'denied')`, propagated the `PermissionError` out uncaught -- matching the
  verdict's own reproduction ("Output: `PermissionError [Errno 13] denied` propagates").

## FIX 1h -- verifier findings and what changed (file:line, this session)

1. **BLOCKING (VERDICT 1 item 1) -- explicit null ledger block.** `mlb_lineup_ledger.py::
   _merged_ledger` (37-72) now decides presence with `name in candidate`, not `value is not
   None`: `for name, block in (('appearances_ledger_home', home), ('appearances_ledger_away',
   away)): if name in candidate and not isinstance(block, dict): ...` (52-55). Root cause fixed
   alongside it: `recover_lineup_history`'s own `candidate = dict(...)` literal (169-178) used to
   set both ledger keys unconditionally via `block.get(name)`, which ALWAYS creates the key in
   the resulting dict even when `block` (the archived row) never had it -- that erased the exact
   presence information `_merged_ledger`'s new check depends on, and would have made every
   genuinely legacy row (no ledger key at all) misreport `lines_malformed`. Each ledger key is
   now copied onto `candidate` only `if 'appearances_ledger_home' in block` (175-178), so a
   truly-missing key stays truly missing through to `_merged_ledger`. Passing:
   `_merged_ledger({'appearances_ledger_home': None}, [])` -> `(None, True)`,
   `reasons=['lines_malformed']`; with an away `{}` partner -> `({}, True)`, same one-item
   `reasons`; a candidate with the key genuinely absent -> `(None, False)`, `reasons=[]`
   (no regression). Constructs: `test_mlb_lineup_state_1h.py::test_case_av_*` (direct, null
   alone), `::test_case_aw_*` (direct, null + dict partner), `::test_case_ax_*` (direct,
   no-regression: genuinely absent key), `::test_case_ay_*` (end-to-end through
   `recover_lineup_history`, an archived row with an explicit JSON null), `::test_case_az_*`
   (end-to-end no-regression: a genuinely legacy row with no ledger key at all stays clean).

2. **CORRECTION (VERDICT 1 item 2) -- preflight path/file count.** Superseded by this session's
   own choice: rather than reusing `_1g` (128 LOC, room enough), this session added a NEW sibling
   `test_mlb_lineup_state_1h.py` per the dispatch rail's own "1g sibling or a new 1h sibling"
   option, so the owned list grows to 18 paths this round (17 -- the count AMENDMENT 8(c) itself
   names after adding `test_mlb_live_feed_state.py` to the prior 16 -- plus this session's own
   new `_1h` file), not 17. The Preflight section below runs the required command over all 18 and
   names every path.

3. **NOTE (VERDICT 1 item 3) -- ledger-first import.** Reconfirmed this session, unchanged:
   `python -c "import scripts.platformkit.ingame.mlb_lineup_ledger"` and the reverse import order
   both succeed in fresh interpreters (STEP 2 below).

4. **CORRECTION (VERDICT 2 finding 1) -- round-6 verdict citation.** The prior memo cited the
   round-6 verdict as `_verdict_s467_1g.md` at its own lines 4 and 16; the worktree copy is a
   gitignored transient (`.gitignore:290` `/_*`), byte-identical (`cmp`) to the canonical
   `_verdict_S467_r6_combined.md` under the host temp directory -- the canonical round-6 files are
   `_verdict_S467_opus6.md`, `cx_s467_verify6_out.md` and `_verdict_S467_r6_combined.md`. This
   rewrite does not repeat that citation: the BUILD RESULT and STEP 0 sections above cite round-7's own `_verdict_s467_1h.md`
   (this round's actual input), and the Fix history entry for FIX 1g below names round-6's REJECT
   by its finding counts only, no filename.

5. **CORRECTION (VERDICT 2 finding 2) -- ac/ad/aq end-to-end construct.** The prior memo's
   AMENDMENT 7 item (e) claimed "the AMENDMENT 6(b) read-error path already had an end-to-end
   construct (`test_case_ac`/`test_case_ad`)" -- false: `ac` (`test_mlb_lineup_state_1f.py:84-
   105`) calls `mll.recover_lineup_history` directly (reader-only, no `capture_state_once`); `ad`
   passes a hand-built history straight to the seam (seam-only). The actual end-to-end construct
   through `capture_state_once` is `test_case_aq` in `test_mlb_lineup_state_1g.py`. That whole
   "AMENDMENT 7 items applied" section is superseded by this FIX 1h section (each round's memo
   carries only its own round's item detail, per the 300-line cap); the corrected fact is
   preserved in the Fix history entry for FIX 1g below instead of restated in a retired section.

6. **CORRECTION (VERDICT 2 finding 3) -- stale line citations.** Lived in the now-superseded
   AMENDMENT 7 section (finding 5 above) and are retired with it. Re-derived once more, fresh,
   for anything this session's own text cites: the legacy-fallback decision is `mlb_lineup_
   ledger.py:56-57`; the two `_get` calls are `mlb_lineup_state.py:89-90` and are counted at
   `mlb_lineup_state.py:97` (unedited this session); `test_case_ac` is `test_mlb_lineup_state_
   1f.py:84-105` with its `monkeypatch.setattr` at line 101 (unedited this session).

7. **CORRECTION (VERDICT 2 finding 4) -- `test_mlb_live_feed_state.py` missing from A9/owned.**
   `git diff --numstat master -- tests/platformkit/ingame/test_mlb_live_feed_state.py` still
   reads `5  1`, i.e. +5/-1, this session (unedited by FIX 1h, unchanged since the round this
   fixture widening actually landed). It now has its own A9 row (285 lines, 15388 bytes LF,
   matching the figures AMENDMENT 8(c) itself names) and is in the owned-path list, the preflight
   command and the landing pathspec below.

8. **CORRECTION (VERDICT 2 finding 5) -- before/after column.** The per-case table below adds a
   "before / after" column, folding in the "first built" round derived mechanically from each
   case's own "evidence" citation (a bare file name means the base `test_mlb_lineup_state.py`,
   i.e. FIX 1a; a parenthetical `(1d)`/`(1e)`/etc. names the sibling that later amended it) rather
   than a fresh git-blame pass -- this worktree's owned files are UNTRACKED, so there is no
   per-line commit history to blame against. FIX 1i round-8 correction: the header previously said
   "first built" only, not "before / after"; every row below now states its populated before and
   after state explicitly.

9. **NOTE (VERDICT 2 finding 6) -- `path.is_file()` outside the OSError boundary.** Was filed
   as a next-row NOTE in the round-7 Opus verdict; AMENDMENT 8(b) promotes it to a binding fix
   this round. `mlb_lineup_ledger.py::recover_lineup_history`'s per-offset loop (136-192) now
   wraps `if not path.is_file(): continue` (143-144) INSIDE the same `try/except OSError` that
   already covered `path.open()` (139, 189-192), so a permission fault raised by the stat itself
   is counted `read_errors` like any other read fault, never a crash. Passing: a `Path` subclass
   whose `is_file()` raises `PermissionError(13, 'denied')`, run through `recover_lineup_history`
   directly, now returns `(({'__incomplete__': True}), ['read_errors', 'read_errors',
   'appearance_history_absent'])` -- no exception. One `read_errors` is appended per day shard the
   reader attempts (the loop tries two: `for offset in (1, 0)`, `mlb_lineup_ledger.py:136`, each
   wrapped in its own `try/except OSError` at 139/189-192), so both shards denied counts two; the
   trailing `appearance_history_absent` is the separate global no-keys-seen signal fired once when
   `known_keys` stayed empty (`mlb_lineup_ledger.py:222-223`), not a second count of the same
   fault. Constructs: `test_mlb_lineup_state_1h.py::
   test_case_ba_*` (direct reader call, asserts the exact `read_errors` count), `::
   test_case_bb_*` (end-to-end through `capture_state_once` with `mlb_live=True`, matching the
   verifier's own reproduction verbatim -- asserts no exception and the row persists with
   `appearance_history_absent` refused).

## Per-case table (before / after column populated per FIX 1i, round-8 CORRECTION)

| case | acceptance criterion (short) | status | before / after | evidence (test) |
|---|---|---|---|---|
| 1 | flag off: byte-identical row/state, no mutation | MET | not built -> MET (1a) | `test_case1_flag_off_no_row_or_state_mutation` |
| 2 | battingOrder 100 -> starter slot 1; 201/305 -> current occupant | MET | not built -> MET (1a) | `test_case2_starter_and_current_occupant_slots` |
| 3 | tie on current slot -> unresolved, starting order unaffected, order-independent | MET | not built -> MET (1a) | `test_case3_*`, `test_case3b_*` |
| 4 | malformed battingOrder excluded both views, tick not dropped | MET | not built -> MET (1a) | `test_case4_malformed_batting_order_excluded_tick_not_dropped` |
| 5 | pitcher-only entry excluded from orders, present in appearances | MET | not built -> MET (1a) | `test_case5_pitcher_only_entry_excluded_from_orders_present_in_appearances` |
| 6 | inHole present/absent/malformed id | MET | not built -> MET (1a) | `test_case6_inhole_present_absent_malformed` |
| 7 | pitchHand present/absent/malformed | MET | not built -> MET (1a) | `test_case7_pitcher_hand_present_absent_malformed` |
| 8 | duplicate identity (batting slot + pitchers) handling | MET (amended: legitimate two-way recorded once, never refused; a genuinely CONFLICTING duplicate record is `player_record_conflict`) | MET (1a) -> amended MET (1d) | `test_case8_two_way_player_recorded_once_never_refused`, `test_case_g_*`/`test_case_h_*` (1d) |
| 9 | two ids on one starting slot -> `lineup_slot_conflict` | MET | not built -> MET (1a) | `test_case9_two_ids_same_starting_slot_conflict` |
| 10 | `first_seen_receipt` carried forward / reset for a new id | MET | not built -> MET (1a) | `test_case10_first_seen_carried_forward_and_reset_for_new_id` |
| 11 | `prior_receipt_after_current` dropped, history unchanged | MET | not built -> MET (1a) | `test_case11_prior_receipt_after_current_dropped_history_unchanged` |
| 12 | two interleaved games, no cross-game bleed | MET | not built -> MET (1a) | `test_case12_interleaved_games_no_cross_game_bleed` |
| 13 | writer-commit failure leaves `mlb_lineup_history` unchanged | MET | not built -> MET (1a) | `test_case13_commit_failure_leaves_history_unchanged` |
| 14 | restart recovers appearances from the archive alone; empty archive refuses; a partial (one-shard) read error never restamps the OTHER shard's game | MET | MET (1a) -> revised MET (1e/1f/1g) | `test_case14_*`, `test_case14b_*`, `test_case_e_*`, `test_case_l_*` (1e), `test_case_ac`/`test_case_ad` (1f), `test_case_aq` (1g) |
| 15 | inhole/pitcher_hand refusal never blocks other fields | MET | not built -> MET (1a) | `test_case15_inhole_and_hand_refusal_never_blocks_other_fields` |
| 16 | registry-adapter perturbation vs a NEW sealed S460 config version | **BLOCKED-ON-S460** -- S460's `feature_registry.py` and its seal are not on master; the perturbation test is REMOVED per AMENDMENT 1(h). Metric is **8 of 9**, never 9 of 9 | not built -> BLOCKED-ON-S460 (since 1b) | none (removed); see `test_mlb_lineup_registry_adapter.py` module docstring |
| 17 | census duplicate-identity / `batter_id` disagreement counted, never dropped | MET | not built -> MET (1a) | `test_case17_batter_id_disagreement_counted_never_dropped` (census) |

## Fix history

FIX 1a: seam split (`mlb_lineup_seam.py`) and initial build. FIX 1b: round-1 REJECT ->
AMENDMENT 1 (a)-(m). FIX 1c: round-2 REJECT -> AMENDMENT 2 (a)-(j), `mlb_lineup_parse.py`
split out. FIX 1d: round-3 REJECT -> AMENDMENT 3 (a)-(f), `test_mlb_lineup_state_1d.py` added.
FIX 1e: round-4 REJECT -> AMENDMENT 4 (a)-(g) + AMENDMENT 5 (a)-(b); `mlb_lineup_ledger.py` and
`test_mlb_lineup_state_1e.py` added. FIX 1f: round-5 REJECT -> AMENDMENT 6 (a)-(h): the reader
never crashes recovery, a read error is recovery loss not a first sighting, the rollover
construct exists, the legacy fold matches the in-memory fold, strict batting-order typing, test
hygiene, an acyclic sibling import via `mlb_lineup_time.py`. FIX 1g: round-6 REJECT (codex sol:
three blockers; Opus tier 2: one blocker, four corrections, two notes) -> AMENDMENT 7 (a)-(g)
applied: a partial read error marks every recovered key (not only the ones missing), every
present non-dict ledger block is counted regardless of a dict partner, ledger entries are
validated and a dropped entry marks its whole game `recovered_absent`, the in-memory ledger
comprehensions are guarded, test hygiene, two notes disclosed, per-case table + case-16 record
restored; `test_mlb_lineup_state_1g.py` added. Its own item (e) is corrected here: `ac`
(reader-only) and `ad` (seam-only) are NOT the end-to-end construct -- `aq` is. FIX 1h (this
session): round-7 REJECT/ACCEPT-WITH-CORRECTIONS -> AMENDMENT 8 (a)-(d) applied: an explicit
JSON null ledger block is counted `lines_malformed` exactly like any other present non-dict
value (root-caused in the reader's own candidate-construction, not only the presence check),
`path.is_file()` moved inside the OSError read boundary, `test_mlb_live_feed_state.py` joins the
owned list/A9/pathspec, the round-6 verdict citation and three stale line citations corrected,
the per-case table's before/after column restored; `test_mlb_lineup_state_1h.py` added. FIX 1i
(this session): round-8 both tiers ACCEPT WITH CORRECTIONS (codex sol: one correction, four
notes; Opus tier 2: three corrections, one note) -> memo-only corrections lane, no code or test
file touched, no new AMENDMENT: the per-case table's before/after column actually populated for
every case (round-7's "first built" column only had a stale header claim of "restored"), lines 5
and 18 now cite the canonical host-temp `_verdict_S467_r7_combined.md` instead of the worktree's
gitignored `_verdict_s467_1h.md` copy, the FIX 1g round-6 citation corrected (the worktree copy of
`_verdict_s467_1g.md` is a gitignored transient, not absent, and is byte-identical to the
canonical `_verdict_S467_r6_combined.md`), a sentence added explaining `read_errors` is counted
once per day shard attempted (two shards) versus the separate global `appearance_history_absent`
no-keys-seen signal, and the A9 table regenerated from disk as the closing edit.

## Preflight, must-not-move and pass counts (this FIX 1h session)

`python -m scripts.platformkit.tracking.contract_preflight --paths` over the 18 owned files (8
source: `mlb_lineup_state.py`, `mlb_lineup_ledger.py`, `mlb_lineup_parse.py`, `mlb_lineup_
seam.py`, `mlb_lineup_time.py`, `mlb_lineup_registry_adapter.py`, `mlb_lineup_census.py`,
`local_state_capture.py`; 10 test: `test_mlb_lineup_state.py`, `_1c`, `_1d`, `_1e`, `_1f`, `_1g`,
`_1h` NEW, `test_mlb_lineup_registry_adapter.py`, `test_mlb_lineup_census.py`, `test_mlb_live_
feed_state.py` -- joins the owned list this round per AMENDMENT 8(c)) `--base master --spec
docs/evidence/tracking/specs/S467_spec.md` -> **9/9 PASS** (vocab, crlf, loc, schema, head_slice,
spec_threshold, proposed, removed_artifact, row_duplication).

`git diff --stat master -- scripts/platformkit/ingame/mlb_live_feed_state.py
ingame_gumbo_mlb.py ingame_pitcher_mlb.py ingame_id_resolver_mlb.py inplay_capture_loop.py
local_state_capture_io.py local_capture_writer.py` -> **empty** (the seven must-not-move files).

Owned, this session: `test_mlb_lineup_state.py` **18 passed** (unchanged). `_1c` **15 passed**
(unchanged). `_1d` **4 passed** (unchanged). `_1e` **19 passed** (unchanged). `_1f` **16 passed**
(unchanged). `_1g` **6 passed** (unchanged). `_1h` (NEW) **7 passed** (AMENDMENT 8(a): `av`,
`aw`, `ax`, `ay`, `az`; AMENDMENT 8(b): `ba`, `bb`). `test_mlb_lineup_registry_adapter.py` **13
passed** (unchanged). `test_mlb_lineup_census.py` **8 passed** (unchanged). Pre-existing, re-run
this session, genuinely unedited by FIX 1h but now bookkept as owned (AMENDMENT 8(c)):
`test_mlb_live_feed_state.py` **73 passed**; `test_local_state_capture.py` **19 passed** --
identical to the STEP 0 baseline. `python -c "import scripts.platformkit.ingame.mlb_lineup_
ledger"` and `python -c "import scripts.platformkit.ingame.mlb_lineup_state"` both succeed in
fresh interpreters (both import orders).

LOC per owned file (this session's final values): `mlb_lineup_state.py` 239 (untouched this
session), `mlb_lineup_ledger.py` 238 (+13: the presence-aware candidate construction and the
`is_file()` boundary move, AMENDMENT 8(a)/(b)), `mlb_lineup_parse.py` 204 (untouched),
`mlb_lineup_seam.py` 62 (untouched), `mlb_lineup_time.py` 29 (untouched), `mlb_lineup_registry_
adapter.py` 146 (untouched), `mlb_lineup_census.py` 152 (untouched), `local_state_capture.py`
300 (untouched), `test_mlb_lineup_state.py` 300 (untouched), `test_mlb_lineup_state_1c.py` 176
(untouched), `test_mlb_lineup_state_1d.py` 85 (untouched), `test_mlb_lineup_state_1e.py` 277
(untouched), `test_mlb_lineup_state_1f.py` 297 (untouched), `test_mlb_lineup_state_1g.py` 128
(untouched), `test_mlb_lineup_state_1h.py` 116 (NEW), `test_mlb_lineup_registry_adapter.py` 124
(untouched), `test_mlb_lineup_census.py` 102 (untouched), `test_mlb_live_feed_state.py` 285
(untouched this session; +5/-1 against master from an earlier round). All <= 300.

## A9 identities (regenerated from disk, this FIX 1i session's closing edit)

LF-normalised (`\r\n` -> `\n`) bytes and sha256, computed identically for both columns.

| path | LOC | bytes (LF) | sha256 (LF-normalised) |
|---|---|---|---|
| scripts/platformkit/ingame/mlb_lineup_state.py | 239 | 14570 | 1ba4d5076c5e4386e2e4b07008146dc43c536457451d01f1ec86a07359c4b3a0 |
| scripts/platformkit/ingame/mlb_lineup_ledger.py | 238 | 13511 | 3e6045ebc18f2f9a0a13ebd33d8c67ce025dc5a1405017ce64a12fc3293bb46f |
| scripts/platformkit/ingame/mlb_lineup_parse.py | 204 | 10558 | c3001543a5e132417fd5e017dafc10e161d156a9aff8c45bc6278db3d9df6923 |
| scripts/platformkit/ingame/mlb_lineup_seam.py | 62 | 3270 | 1c313e6e0093f78a7470cde0b8b820dbb391098efcdab249a57398d321277e04 |
| scripts/platformkit/ingame/mlb_lineup_time.py | 29 | 1383 | 9c7ff2a1c5ef39f8f6b707f020efacdfe9dd5066d69f7ed23375e8ef1c42e2c2 |
| scripts/platformkit/ingame/mlb_lineup_registry_adapter.py | 146 | 9201 | a05a40762f83bc0f6af73f319ea818a7651a917d1d5bbdee6c1cbd8943fc1900 |
| scripts/platformkit/ingame/mlb_lineup_census.py | 152 | 7053 | 6e802cca43f7d115c01a38b3f45e1fd3be89324a4d289a109fe15653368fad0e |
| scripts/platformkit/ingame/local_state_capture.py | 300 | 17636 | 459441325233b619f45b2775fc4899fe41cfa573fdc21352522bb4f4c49c845f |
| tests/platformkit/ingame/test_mlb_lineup_state.py | 300 | 16079 | 062ee69f8c5ed2b122907c5fb2341af7763a585b5cda5d1a150a9452715b8974 |
| tests/platformkit/ingame/test_mlb_lineup_state_1c.py | 176 | 10164 | 38dfb08328403d91f057863e9a32573df2e0585076a7743d9fb4d2c6d5370892 |
| tests/platformkit/ingame/test_mlb_lineup_state_1d.py | 85 | 5015 | fa37af9ff4b080b20b24f61b2c37152532eddad3438d5bb97772787a87b0dc7d |
| tests/platformkit/ingame/test_mlb_lineup_state_1e.py | 277 | 14800 | 9e35d989910cfc70d918f36d88f167a7e25592e43f4436a264aa201544de4f3a |
| tests/platformkit/ingame/test_mlb_lineup_state_1f.py | 297 | 15404 | 1f94aac7821a9764c1d925803a6e2be7a74b0c0191247493b472b4cfe30b139c |
| tests/platformkit/ingame/test_mlb_lineup_state_1g.py | 128 | 6874 | 1cdde74d9777407fb451f979010cf4c8f52ee35290d1eec68940c6f8a28bd76e |
| tests/platformkit/ingame/test_mlb_lineup_state_1h.py | 116 | 5674 | 04f05f3f78d4361e2612c44140eff03adda84cd2d0f7bf2cf166d40d9104eb5c |
| tests/platformkit/ingame/test_mlb_lineup_registry_adapter.py | 124 | 6329 | 0a98c58fbe2e27ba028bb1cdf0a8ed14c8629dd514fb5ccf25ac0775a6828565 |
| tests/platformkit/ingame/test_mlb_lineup_census.py | 102 | 4811 | c38a1ce2fed5117e6876e87f3f4d0179d500d2b0c3d8cd2f2b47d3d85c4626ac |
| tests/platformkit/ingame/test_mlb_live_feed_state.py | 285 | 15388 | ba713f0cd01f7ad2e249593001dc9f39fd3c203c7b2d1fcef378ed5536359d6f |

FIX 1i (this session, memo-only corrections lane): one fast-forward at the start, `git -C
/c/Users/neelj/nba-harness-h120 merge --ff-only master`, advancing `harness-h120` from
`9b47d6426abbd67b20ed04de6a2e2f8599c76756` to `d0c21a5f2731fa204461023d9a48a8e4998a51ce` (one
commit: `docs/evidence/tracking/specs/S470_spec.md`). `git rev-parse HEAD` =
`d0c21a5f2731fa204461023d9a48a8e4998a51ce`. `git rev-parse master` =
`d0c21a5f2731fa204461023d9a48a8e4998a51ce`. **EQUAL**. `git diff --stat 9b47d6426 d0c21a5f2 --
scripts/platformkit/ingame/ tests/platformkit/ingame/` is empty: the one commit that landed
touched only a spec file, disjoint from every owned path. This FIX 1i lane made no git operation
beyond that one fast-forward merge -- no commit, no `--force`; files are left on disk for
`lane_commit`. No source or test file changed this session; the 18-row A9 table below was
regenerated from disk as the closing edit and is unchanged from FIX 1h's own values.

SHA: NOT CREATED (sandbox); files ready for lane_commit.

## NOT VERIFIED

Everything above is construct-only. NOT VERIFIED: whether `linescore.offense.inHole` and
`gameData.players.<id>.pitchHand` actually appear in a live GUMBO payload (still deferred to the
orchestrator); whether real MLB substitution `battingOrder` values follow the assumed
`slot*100 + sequence` encoding at scale; restart/rollover recovery against a REAL multi-day
archive (only hand-built construct shards); the registry adapter's consumption once S460 actually
lands; any real-night agreement/disagreement rate between `mlb_lineup.batter_id` and landed
`state.batter_id`; whether a real GUMBO payload ever emits a non-dict `appearances`/ledger shape,
an explicit JSON null ledger block, an int-subclass id, two distinct player records for one
person id, or an unparseable `first_seen_receipt` (every AMENDMENT 6/7/8 guard is defensive/
deterministic against shapes the verifier constructed, not observed live artifacts); whether a
real filesystem read error during recovery (AV lock, permission fault on either `open()` or the
`is_file()` stat itself) has EVER actually occurred on this host -- the `PermissionError`
constructs are injected, not observed; the `lines_malformed`/`stamp_invalid`/`read_errors`/
`recovery_conflict` reader counters against a real corrupted or concurrently-written shard. No
trial charged; no ledger K read; this FIX 1h session made no network call and wrote nothing
under `data/`.
