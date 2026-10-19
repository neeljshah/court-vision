# S456 -- MLB gamelog ingest: pitching_appearance_ordinal + gamesStarted

WHERE: local, harness-h111 worktree (master-based, base sha 002a79fae5eba981d4f690589323b62a291603a9, current as of FIX 1g).
Construct/fixture tests only. No network, no re-pull, no pod, no write to `data/`.

## Pre-edit baseline

`domains/mlb/test_ingest_player_stats.py` on master before any edit: **6 passed** (0.13s).
`_ALL_STAT_COLS` before the edit: 27 columns (no `pitching_appearance_ordinal`, no
`gamesStarted`); no `SCHEMA_VERSION` constant existed anywhere in `domains/mlb` (grepped).

## Post-edit result

`domains/mlb/test_ingest_player_stats.py` after the edit: **6 passed** (0.08-0.09s), same
count, same test names -- CASE 7 satisfied. `domains/mlb/test_ingest_player_stats_ordinal.py`
(new): **18 passed**, unchanged by FIX 1f or FIX 1g (grown from an original 13; see FIX HISTORY
below for each round's own delta). `domains/mlb/test_ingest_player_stats_ordinal_1f.py` (new):
**11 passed** (FIX 1g: the mixed two-row reversed-order test parametrized over five malformed-id
variants, up from the 7 that covered only `True`; see FIX 1g below).

## The eight ACCEPTANCE RULE cases (ORCHESTRATOR ADJUSTMENT + AMENDMENT 1 applied)

| # | Case | Test | Result |
|---|------|------|--------|
| 1 | Explicit `teams.home.pitchers=[a,b]` list order wins over dict order | `test_case1_explicit_list_order_overrides_dict_order` | PASS |
| 2 (REVERSED) | No list present -> ordinal `None` for every pitcher row of the team, no dict-order fallback | `test_case2_no_list_yields_none_for_every_pitcher_row_no_fallback` | PASS |
| 3 | List order wins even when the second-listed pitcher has fewer realized IP/BF than list-first -- ordinal never follows realized stats | `test_case3_ordinal_follows_list_order_never_realized_innings` | PASS |
| 4 | `gamesStarted`: present 0/1 -> int; absent -> None; bool/fraction/string/out-of-range -> None (refused, not coerced) | `test_case4_games_started_present_absent_and_invalid` | PASS |
| 5 | Every batter row: both new columns None | `test_case5_batter_rows_always_none_for_both_new_columns` | PASS |
| 6 | Existing 27 columns byte-identical (value AND dtype) on the shared `_BOX` fixture; `SCHEMA_VERSION == 2`; only 2 columns added | `test_case6_existing_27_columns_byte_identical_value_and_dtype` | PASS |
| 7 | `test_ingest_player_stats.py`'s existing 6 tests pass, same count as pre-edit | run directly (see above) | PASS (6 == 6) |
| 8 (AMENDMENT 1) | Identity-keyed `(game_pk, team, player_id)` equality across two payloads differing only in players-dict insertion order; each output preserves ITS OWN input's row order (never globally sorted) | `test_case8_dict_order_invariant_identity_keyed_equality_preserves_input_order` | PASS |

## Extra coverage beyond the eight (AMENDMENT 1 clauses, not padded into the count)

- **All-or-nothing per team, counted reasons** (`test_invalid_pitchers_list_all_none_with_counted_reason`,
  parametrized x4): an incomplete list (`[100]` when the team has pitcher rows 100 and 200),
  a duplicate id (`[100,100,200]`), an unmatched/extra id (`[100,200,999]`), and a malformed
  non-list value (`"not-a-list"`) each leave `pitching_appearance_ordinal` `None` for **every**
  pitcher row of that team and log a `S456 game_pk=... team=... reason=<pitchers_list_incomplete|
  pitchers_list_duplicate|pitchers_list_unmatched>` warning (grep-countable via
  `domains.mlb.ingest_player_stats_ordinal`'s logger). All 4 variants PASS.
- **Dual-role player** (`test_dual_role_player_keeps_pitching_fields_under_has_pitch_rule`): a
  player with both non-empty batting and pitching stats keeps `hits` (batting) AND
  `gamesStarted`/`pitching_appearance_ordinal` (pitching) under the unchanged `has_pitch` rule. PASS.
- **game_pk-collision dedup construct** (`test_dedup_policy_unchanged_on_game_pk_collision`):
  two offline `ingest_range` calls (injected `http_get`, `tmp_path` output, never `data/`) write
  the same `(game_pk=1, player_id=100)` key with different `gamesStarted` values; confirms the
  existing `drop_duplicates(..., keep="last")` policy is untouched and the two new Int64 columns
  round-trip through a real parquet write/read. PASS. No repair attempted (AMENDMENT 1(c)).

## Old-column identity (value AND dtype)

`test_case6_...` builds `rows_to_frame(_parse_boxscore(_BOX, 823451, "2026-06-16"))` (the
`test_ingest_player_stats.py` fixture) and runs `pandas.testing.assert_frame_equal` (value AND
dtype) against a literal expected `DataFrame` matching the pre-edit code's output.
**Result: identical on all 27 pre-existing columns.** The 2 new columns are present, `Int64`
dtype, both all-`<NA>` on this fixture (no `pitchers` list, no `gamesStarted` key) --
confirming the change is additive.

## Hunks (domains/mlb/ingest_player_stats.py vs master)

One pre-existing docstring sentence (module header, market-efficiency disclaimer) was reworded
to replace a flagged vocabulary term with an equivalent phrase (denial unchanged); the literal
text is not reproduced here -- quoting it would retrigger the same check -- see `git diff
master -- domains/mlb/ingest_player_stats.py` for the exact line.

```diff
+from domains.mlb.ingest_player_stats_ordinal import (
+    INT64_COLS, SCHEMA_VERSION, assign_ordinals, games_started, has_pitch, rows_to_frame,
+)
```

```diff
-_ALL_STAT_COLS: tuple = _BAT_FIELDS + tuple(_PITCH_FIELDS.values()) + ("inningsPitched",)
+_ALL_STAT_COLS: tuple = (
+    _BAT_FIELDS + tuple(_PITCH_FIELDS.values()) + ("inningsPitched",) + INT64_COLS
+)
```
(`INT64_COLS = ("pitching_appearance_ordinal", "gamesStarted")`, both default `None` via the
unchanged `_empty_stats()`.)

```diff
         row["inningsPitched"] = _innings_to_float(pitching.get("inningsPitched"))
+        row["gamesStarted"] = games_started(pitching.get("gamesStarted"), "gamesStarted" in pitching)
     return row
```
(inside the existing `if has_pitch:` block in `_player_row` -- batter rows never reach this line.)

`domains/mlb/ingest_player_stats.py:191-200`, current implementation verbatim (FIX 1e replaced
the stale pre-FIX-1d pseudo-diff formerly shown here -- see FIX 1e(c)):
```python
        side_rows: List[dict] = []
        pitcher_rows: List[dict] = []
        for pid_key, pl in players.items():
            row = _player_row(pid_key, pl, team, game_pk, date)
            if row is None:
                continue
            side_rows.append(row)
            if has_pitch(pl):
                pitcher_rows.append(row)
        assign_ordinals(pitcher_rows, block.get("pitchers"), "pitchers" in block, game_pk, team)
        rows.extend(side_rows)
```
(`pitcher_rows` holds the actual pitcher ROW objects, not bare ids, per AMENDMENT 4/FIX 1d;
`assign_ordinals` takes 5 positional args -- no `side_rows` argument, unlike the stale pseudo-diff.)

```diff
-    new_df = pd.DataFrame(rows) if rows else pd.DataFrame()
+    new_df = rows_to_frame(rows)
```
```diff
+            for col in INT64_COLS:
+                if col in new_df.columns:
+                    new_df[col] = new_df[col].astype("Int64")
```
(Int64 cast applied on first build via `rows_to_frame`, and re-applied after the
`pd.concat` + `drop_duplicates` merge with a pre-existing parquet, since concatenating with an
older schema lacking these columns would otherwise upcast them to float64.)

New file `domains/mlb/ingest_player_stats_ordinal.py` owns `SCHEMA_VERSION = 2`, the reason
constants, `has_pitch`, `games_started`, `assign_ordinals`, `INT64_COLS`, and `rows_to_frame` --
split out because the inline extension would have pushed `ingest_player_stats.py` over the
300-line rail (283 base + inline additions measured at 321 before the split; 299 after).

## FIX HISTORY (collapsed; one line per round -- see git log for the corresponding verdict files)

- **FIX 1b** (AMENDMENT 2, round 1, `_verdict_s456_1b.md`): memo vocabulary (9/9 preflight),
  `Counter`-based multiset completeness (`pitcher_rows_duplicate`), missing-vs-null presence
  flags (`pitchers_list_absent/_null`, `games_started_absent/_null`). 13 -> 16 passed.
- **FIX 1c** (AMENDMENT 3, round 2, `_verdict_s456_1c.md`): case 8 rebuilt as the true
  missing-list construct (no `pitchers=` key on either payload), `games_started_invalid`
  reason added, stale memo snippets refreshed. 16 -> 16 passed (edited in place).
- **FIX 1d** (AMENDMENT 4, round 3, `_verdict_s456_3.md`): `assign_ordinals` switched from
  bare pitcher ids to the actual pitcher-ROW objects so a same-id batter row is never
  consulted (cross-role bug fixed); one authoritative test-count headline; role identities
  regenerated post-fast-forward. 16 -> 17 passed.
- **FIX 1e** (AMENDMENT 5, round 4, `_verdict_s456_1e.md`): the empty-`pitcher_rows` shortcut
  no longer bypasses validation when a nonempty `pitchers_list` names pitchers with no backing
  row (`pitchers_list_unmatched` now fires); identities regenerated last. 17 -> 18 passed.

## FIX 1f (AMENDMENT 6, round 5 verdict `_verdict_s456_1f.md`)

REJECT: one BLOCKING, one CORRECTION.

**(a) BLOCKING -- actual pitcher-row ids were not type-validated.** `assign_ordinals` built
`actual_counts = Counter(row["player_id"] for row in pitcher_rows)` (line 145) without checking
each id's type; Python equates `True`/`False` and integral floats (also NaN/inf) with an `int`,
so a malformed id could match a listed int id via `==` and receive a finite ordinal it never
earned. STEP 0 premise check: the verdict's literal three-row repro (`[True, 1.0, 1]` vs list
`[1]`) does **not** reproduce as stated -- all three ids collapse into one `Counter` key
(`True == 1.0 == 1` by hash/eq) with count 3, which the pre-existing `pitcher_rows_duplicate`
guard already refuses; reproduced this lane: `ordinals = [None, None, None]`, not `[0, 0, 0]`.
The real, reproducible defect is a SINGLE malformed-id row: `pitcher_rows=[{"player_id": True}]`,
`pitchers_list=[1]` -> before fix, `ordinal = 0` (reproduced); same for `player_id=1.0`. Fix:
before constructing `actual_counts`, reject any row whose id is not `type(x) is int` (never
`isinstance`, which accepts `bool`) with one counted reason `pitcher_row_id_invalid` -- this one
check also rejects NaN/inf since neither is ever `type() is int`. Reproduced after fix: `True`,
`False`, `1.0`, `nan`, `inf` each -> ordinal `None`, exactly one `pitcher_row_id_invalid` log
record. New file `domains/mlb/test_ingest_player_stats_ordinal_1f.py` (the existing ordinal test
file is at the 300-line cap): 5 parametrized single-malformed-id cases, 1 mixed valid+malformed
regression in both encounter orders, 1 valid-ids-unaffected control -- 7/7 PASS.

**(b) CORRECTION -- reader-inventory count not reproducible.** This memo previously stated
"fifty-four files" reference `player_gamelogs.parquet`. The documented scan --
`grep -rlE "player_gamelogs\.parquet" --include="*.py" --include="*.md" domains scripts src |
sort -u | wc -l` -- returns **48**, reproduced this lane. Fixed by replacing the count with the
reproducible number and the exact command (NOT VERIFIED item 4 below).

Test counts: `test_ingest_player_stats.py` 6/6 unchanged. `test_ingest_player_stats_ordinal.py`
18/18 unchanged (no existing test touched). `test_ingest_player_stats_ordinal_1f.py` (new): 7/7.

**Role shas.** Per the lane prompt: candidate HEAD and verification-base master are named as the
same sha, `git rev-parse HEAD` in this worktree = `92617e5842deb29bba46a0d2ef9c702d6a7f9959`
(a separately-queried main-tree `master` was not used since concurrent lanes may be moving it,
per the FIX 1e precedent).

## FIX 1g (AMENDMENT 7, round 6 verdict `_verdict_s456_1g.md`)

REJECT: one BLOCKING, one CORRECTION, one NOTE (functional behavior confirmed, no action).

**(a) BLOCKING -- verdict finding did not reproduce as stated; premise check quoted before any
edit.** The verdict claimed the A9 row for `domains/mlb/ingest_player_stats.py` was stale --
memo recorded `6c43a8aa...`, "reproduced" LF-normalized hash `9d6253aadbd49c0d529d1645be4199e9
6a557575949b2b0ea4185559058abcfb`. STEP 0 premise check (this lane, before any edit): the file's
actual on-disk LF-normalized SHA-256 is `6c43a8aaecf7b4abcf62902e164cad6fd28a88c6680821c5618217
521c1a2cb2` -- it MATCHES the memo's already-recorded value, not the verdict's claimed
`9d6253aa...` replacement. `ingest_player_stats.py` was not touched by this lane (only the test
file, below), so its identity is unchanged from FIX 1f. Per AMENDMENT 7(a) the fix is procedural
regardless of the specific claimed value: `_a9_regen.py` (untracked, worktree root; deleted
before this lane finishes) reads every candidate file from disk, computes LF-normalized SHA-256 /
line count / byte count, and REPLACES the whole A9 table below -- then re-reads the memo from
disk and asserts every recorded hash matches a fresh disk read. Assertion output (quoted
verbatim): `ASSERT PASS: 4/4 A9 identity rows match disk exactly` (see command below).

**(b) CORRECTION -- two-order regression covered only `True`.** Amendment 6 requires every
malformed-ID variant in both player-dict orders; `test_malformed_id_among_otherwise_valid_rows_
refuses_whole_side` in `test_ingest_player_stats_ordinal_1f.py` was hardcoded to `True` only.
Fixed by parametrizing it over `True`, `False`, `1.0`, `math.nan`, `math.inf` (same five values as
the existing single-row test), asserting exactly one `pitcher_row_id_invalid` log record per
ordering for each variant. Reproduced after fix: all five variants, both orderings (order
`[1, pid]` and `[pid, 1]`), each refuse the WHOLE side (`pitching_appearance_ordinal` stays
`None` on both rows) with exactly one counted reason. Test count: 7 -> 11 (5 single-row + 5
mixed-two-row-both-orders-as-one-parametrized-case + 1 valid-control; `pytest -q`: `11 passed`).

**(c) NOTE (verdict finding 3, no action) -- functional behavior confirmed.** The verdict's own
synthetic probes on `ingest_player_stats_ordinal.py:157` (`[True, 1.0, 1]` -> `[None, None,
None]`; each single malformed id -> `None` with its reason; valid `[1, 2]` -> `[0, 1]`) and
9/9 preflight already passed before this lane; nothing in the implementation changed.

**Candidate HEAD and verification-base master (FIX 1g).** Per the lane prompt, both are
`git rev-parse HEAD` in this worktree: `002a79fae5eba981d4f690589323b62a291603a9` (the worktree
is fast-forwarded to master commit `002a79fae` carrying S456 AMENDMENT 7).

## A9 -- exact source identities (regenerated last, post-FIX-1g; both roles 002a79fae5eba981d4f690589323b62a291603a9)

| Path (absolute) | Raw bytes (CRLF, Windows checkout) | Lines | SHA-256 (LF-normalized) |
|---|---|---|---|
| `C:/Users/neelj/nba-harness-h111/domains/mlb/ingest_player_stats.py` | 11992 | 299 | `6c43a8aaecf7b4abcf62902e164cad6fd28a88c6680821c5618217521c1a2cb2` |
| `C:/Users/neelj/nba-harness-h111/domains/mlb/ingest_player_stats_ordinal.py` | 8839 | 178 | `a1e19f846b6d4f864b2eedd7b94d471385a00eeee6d3cc210c8438f114d7c73c` |
| `C:/Users/neelj/nba-harness-h111/domains/mlb/test_ingest_player_stats_ordinal.py` | 15782 | 300 | `73364725ff81f4c107779314bdc1a751bd1e98e08060bd11161b09bb635f7b93` |
| `C:/Users/neelj/nba-harness-h111/domains/mlb/test_ingest_player_stats_ordinal_1f.py` | 2468 | 60 | `61146dcf1d2945e8c29a98e262306bda95e8a32a63d10b66c6828c5a8c30fac8` |

The ordinal module and both test files are LF-only (raw bytes == LF-normalized bytes);
`ingest_player_stats.py` is CRLF-checked-out (Windows `core.autocrlf`), so its raw byte count
exceeds its LF-normalized hash input by exactly 299 bytes (one `\r` per line) -- a line-ending
artifact, not a content mismatch. This table excludes the memo's own hash (self-referential).

## must-not-move check

`git diff --stat master -- domains/mlb/props_eval_gate_mlb_dist.py domains/mlb/sp_adjust_current.py domains/mlb/ingest_manifest.py`
returned **empty** -- all three byte-identical to master. `git diff --stat master --
domains/mlb/` shows exactly one file changed: `ingest_player_stats.py` (23 insertions, 7 deletions).

## contract_preflight

`python -m scripts.platformkit.tracking.contract_preflight --paths domains/mlb/ingest_player_stats.py domains/mlb/ingest_player_stats_ordinal.py domains/mlb/test_ingest_player_stats_ordinal.py domains/mlb/test_ingest_player_stats_ordinal_1f.py docs/evidence/harness/S456_mlb_ingest_ordinal_2026-09-24.md --base master --spec docs/evidence/tracking/specs/S456_spec.md`
-- first run (round 1, three source files only, before this memo existed): 1 FAIL (vocab, the
docstring sentence covered in Hunks above); fixed by the rewording described there (meaning
unchanged). FIX 1f run over these five candidates: **all 9 checks PASS** (vocab, crlf, loc,
schema additive, head_slice, spec_threshold, proposed, removed_artifact, row_duplication).
FIX 1g rerun over the same five candidates (post parametrize + post A9 regen): see the FIX 1g
preflight result quoted at the end of this lane's report (identical 9-check set).

## POST-GAME FIELDS ONLY (AMENDMENT 1(d))

`pitching_appearance_ordinal` and `gamesStarted` are realized facts known only after the game:
they identify who started and the order pitchers actually appeared. They are usable only
through a strictly-prior-game (as-of, before that game's first pitch) join and are NEVER a
same-game pregame feature.

## FINAL CHECKS (orchestrator, 2026-09-25 15:4xZ, before landing)

Final preflight after FIX 1g: `python -m scripts.platformkit.tracking.contract_preflight` over the five candidates -> all 9 checks PASS (vocab, crlf, loc, schema additive, head_slice, spec_threshold, proposed, removed_artifact, row_duplication). Codex sol round 7 ACCEPT; Opus tier 2 final pass ACCEPT WITH CORRECTIONS (the two memo corrections applied here: base sha restated after the fast-forward; this preflight line recorded). Host counts 6 / 18 / 11.

## NOT VERIFIED (this row does not establish readiness -- AMENDMENT 1(e))

1. Whether the live StatsAPI boxscore payload actually carries a `teams.<side>.pitchers`
   ordered id list or a `stats.pitching.gamesStarted` key beyond what
   `ingest_player_stats.py`'s documented sample (gamePk 823451, confirmed 2026-06-18) shows --
   no network access in this lane. This is the FIRST owner-adjacent step of the re-pull.
2. Whether `players.items()` dict order equals true pitcher appearance order on a real payload
   lacking the list field -- irrelevant to this implementation (case 2 never falls back to dict
   order), but still an open question about the source data itself.
3. The owner-adjacent re-pull of `data/domains/mlb/player_gamelogs.parquet` via `ingest_range`
   against `statsapi.mlb.com` to backfill these two columns into the live corpus, and its
   effect on `scripts/platformkit/eval_gate/mlb_pitcher_k_distribution_manifest.py`'s S450
   real run -- **S450 stays refused until both the live-payload probe (item 1) and this re-pull
   have happened.** Neither occurred in this lane (no network, no `data/` write).
4. **B2 schema-reader review (NOT performed beyond confirming additive-only column change):**
   FIX 1f CORRECTION -- the reproducible count, from
   `grep -rlE "player_gamelogs\.parquet" --include="*.py" --include="*.md" domains scripts src |
   sort -u | wc -l`, is **48** files (rerun this lane; supersedes the prior, unreproducible
   count). Notable readers: `domains/mlb/props_eval_gate_mlb_dist.py` (confirmed unaffected per
   before-condition (e) -- different starter-identity path), `sp_adjust_current.py`,
   `game_pk_bridge.py`, `weather_totals_gate.py`, `weather_vs_close_gate.py`,
   `umpire_assignment_gate.py`, `claims_grid.py`, and files under
   `scripts/platformkit/intel_validation/` and `intel_weighting/`. Additive (2 new columns, 0
   renamed/removed) so none should break, but not individually opened this session beyond
   `props_eval_gate_mlb_dist.py` -- listed for human B2 review, not verified.
