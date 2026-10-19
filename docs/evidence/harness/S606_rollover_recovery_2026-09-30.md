# S606 -- state capture day rollover without an archive pass (2026-09-30)

Spec: docs/evidence/tracking/specs/S606_spec.md incl. AMENDMENTS 1-2. Base: master 8d1d7d7f49a1438b8ffaed41ae4a4e2e3332db33 (worktree h274). Capture plumbing only; no flag flipped, no registry write.

## Before-condition (quoted at build, on the base blob)

`grep -n "recover_states\|recover_history" scripts/platformkit/ingame/local_state_capture.py`:

    126:        state['recovered'] = writer.recover_states(now, sports)
    127:        state.update(mlb_lineup_seam.recover_history(client, writer, sports, now, mlb_live))

Both sat inside `if rolled or 'recovered' not in state:` (:124). test_local_state_capture.py:299 asserted `calls[1:] == [['nba']]` (one archive rebuild at the rollover) -- the defect.

## Change

- NEW scripts/platformkit/ingame/local_state_rollover.py (40 lines): `prepare_day(state, day, client, writer, sports, now, mlb_live)` = rollover reset list + mlb_disc_ts pop + day (verbatim :119-123); STARTUP (`'recovered' not in state`) = old :126-131 verbatim, then `rec_touch = set(recovered) | (set(mlb_lineup_history) - {'__incomplete__'})`; ROLLOVER with a map = CARRY (keep recovered and mlb_lineup_history keys in rec_touch; '__incomplete__' dropped; rec_touch reset). Same-day tick with a map: nothing.
- MODIFIED local_state_capture.py 300 -> 288 lines (net -12): the :118-131 block becomes one `prepare_day` call; the TOUCH line `state.setdefault('rec_touch', set()).update(r['sport'] + ':' + str(r['game_key']) for r in rows)` immediately before `return rows, finals, len(tasks)`; `local_state_rollover` appended to the existing import line :12. Nothing else moved.
- MODIFIED tests/platformkit/ingame/test_local_state_capture.py :290/:299 (line-neutral): the rollover case is renamed `..._none_at_rollover_...` and asserts `calls[1:] == []`.
- NEW tests/platformkit/ingame/test_state_rollover_carry.py (13 tests: cases 1-12 + the real-row check), fixtures/s606/{mlb_rollover_slice.jsonl, old_case3.json, seal.json}, `.gitattributes` line `tests/platformkit/ingame/fixtures/s606/** text eol=lf`.
- Must-not-move (local_state_recovery.py, local_state_capture_io.py, mlb_lineup_seam.py, mlb_lineup_ledger.py, mlb_lineup_state.py, local_state_capture_commit.py, local_state_capture_sources.py): `git diff master --stat` empty.

## Fixtures

- mlb_rollover_slice.jsonl: streamed line by line (RSS 25 MB) from the live archive mlb shards: the last 300 lines of 2026-09-29.jsonl (4,838 lines) plus the last 3 lines of each of 849843 / 849845 / 849849 / 849851 (union 303 lines, file order) and the first 20 lines of 2026-09-30.jsonl. Rows are verbatim.
- old_case3.json: case 3's OLD first-post-rollover rows, produced by `python -m tests.platformkit.ingame.test_state_rollover_carry old` on the PRE-change blob (before local_state_capture.py was edited), then pinned.
- seal.json pins both full sha256 (LF-normalised); the tests compare against the seal.

## Equivalence (printed by `python -m tests.platformkit.ingame.test_state_rollover_carry memo` on the final candidate)

Construct scenario (6 keys over nba / mlb / soccer / tennis + one unseen key; first row after the 2026-09-22 rollover):

| key | old baseline | old state_changed | new baseline | new state_changed | equal |
|---|---|---|---|---|---|
| mlb:pre1 | ["pre", {"i": 0}] | True | ["pre", {"i": 0}] | True | True |
| mlb:span1 | ["live", {"i": 6}] | False | ["live", {"i": 6}] | False | True |
| nba:live1 | ["live", {"s": 2}] | False | ["live", {"s": 2}] | False | True |
| nba:new1 | null | None | null | None | True |
| nba:start1 | null | None | ["live", {"s": 0}] | False | False |
| soccer:fin1 | ["final", {"g": 1}] | False | ["final", {"g": 1}] | False | True |
| tennis:pop1 | ["live", {"p": 1}] | True | null | None | False |

The two False rows are exactly disclosed differences (2) (nba:start1, startup-only key) and (1) (tennis:pop1, popped identity).

Real-row check (old = real StateWriter.recover_states at 2026-09-30T00:08:42Z over the slice laid out as 09-29 / 09-30 shards; carried = the map after replaying the 303 09-29 rows through capture ticks and one empty rollover tick at 00:08:42Z):

| real key | old (status) | carried (status) | raw equal | JSON-normalised equal |
|---|---|---|---|---|
| mlb:849843 | pre | pre | True | True |
| mlb:849845 | final | final | True | True |
| mlb:849849 | live | live | True | True |
| mlb:849851 | live | live | True | True |

09-30 rows of those keys (disk vs replay state_changed): 12 rows, equal=True (includes 849849 at 00:08:44.688926Z = True).

    mlb_rollover_slice.jsonl pinned f0d4d1bfe4f6db05b269a498cd22bc89403c43b307ae95fecdd811dee336f16b computed f0d4d1bfe4f6db05b269a498cd22bc89403c43b307ae95fecdd811dee336f16b EQUAL
    old_case3.json pinned 46c005d8d88f9a79ebb6674fb1036978478d7515e4eb187ab0a4fe6e569de392 computed 46c005d8d88f9a79ebb6674fb1036978478d7515e4eb187ab0a4fe6e569de392 EQUAL

Metric: construct cases 12/12 (+ the AMENDMENT 1(a) seeded-state assertion inside case 12) and real-row keys 4/4. Before (pre-change blob, same test file): 8 failed / 5 passed (cases 1, 2 fail on the rollover rebuild; 3, 4, 5, 8, 9, 12 fail on the rebuild or the missing rec_touch). After: 13 passed.

Test power: forcing the archive pass back at the rollover (`if rolled or 'recovered' not in state:` in prepare_day) fails 9/13 incl. case 1 (recover count) and case 2 (history count), and the owned test_local_state_capture.py case; restored file byte-identical to the candidate (git diff --no-index empty).

## Mandatory disclosures

1. Popped identity (:223 `recovered.pop`): old finds an EARLIER receipt of that key in the archive, new has none -> the key's first post-rollover row has state_changed None instead of a bool (one row).
2. Startup keys: rec_touch is seeded from the startup map, so at the FIRST rollover a key whose only rows were on D-1 is kept although old dropped it -> state_changed bool instead of None on its first D+1 row; dropped at the next rollover.
3. Foreign appends to shard D: impossible while the capture lock is held.
4. Games spanning midnight and finals: written on D, carried, identical (mlb:span1, soccer:fin1, real 849845 final).
5. Commit failure: state changes only after commit_rows succeeds; an uncommitted draft never enters the map or rec_touch (case 9).
6. mlb_lineup_history: old rollover REPLACED it with the archive read; new keeps the live ledger restricted to touched keys (the persisted ledger rows already contain it); recovered_absent refusals the old archive read could add at a rollover no longer occur; the '__incomplete__' sentinel is dropped at the carry.
7. New value = the canonical of the LAST written row of a key; old = the row with max response_end_utc per key. They are equal iff per-key response_end is monotone across ticks (it is on the real slice: 4/4 raw equal).
Value equality otherwise holds up to a JSON round trip (tuple/list, non-str keys, NaN): old reads disk, new keeps the in-memory canonical, which is what intra-day ticks already compare against.

## Resolved at build (AMENDMENT 2)

- 2(a) applied: tests/platformkit/ingame/test_nba_pbp_starters_census.py line 206 (the S472 byte pin of local_state_capture.py to blob f042695c23e1e32af4bd04f8ca66782c9f79e971) is now a comment naming the amendment; the capture-row equality below it still pins behaviour; the file passes 45.
- 2(b) applied: the verbatim real-row fixture trips the preflight vocab check only through ISO minute/second fields equal to a retracted bare integer (627 hits, all inside timestamps); it lands verbatim in its own data-only commit before land_row (sha256 pinned in fixtures/s606/seal.json). Masking ISO timestamps in the vocab check is flagged to the owner, not changed here.
- Disclosure (8): an exception between rows.append and the touch statement leaves that key's carried baseline stale across midnight, where the old archive pass would have healed it (counted in adapter_errors; only reachable if emission_reasons or remembered.update raise).
- Disclosure (9): after a startup the map holds the keys of days D-1 and D (about twice a day's keys on a tennis-heavy day) until the first rollover (difference (2)).
- Test-strength note (verify r1, non-blocking): the seeded same-day no-reset rule is pinned by test_mlb_lineup_state_1f case_aa, not by c12 of the owned file.

## NOT VERIFIED

- No live midnight was observed with this code; no state2 restart was done. Adoption = one state2 restart (orchestrator); acceptance = the 2026-10-01 00:00Z rollover with last_write_ts gap < 30 s with live games.
- Tennis volume not exercised; the carried-map size for a 1.35M-row tennis day was not measured (bounded by distinct keys touched that day, not rows).
- The STARTUP pass is unchanged: a restart at a busy hour still reads the full archive (follow-up row, out of scope).

## VERIFY ROUNDS
- r1 (2026-09-30): contract ACCEPT WITH CORRECTIONS (memo vocab line, stale open-at-build section); adversarial ACCEPT WITH CORRECTIONS (0 blocking; 6-day differential simulation matched the old code except 6 disclosed-(1) rows; recover calls = process starts). Memo corrected.
