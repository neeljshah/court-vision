# S404 -- the native bridge reduces state metadata PER FIELD

Row S404 (docs/evidence/HARNESS_GAPS_2026-09-03.md line 546), spec
docs/evidence/tracking/specs/S404_spec.md, worktree harness-h65, REBASED for FIX 1d onto master
9103ae26e (S403 3373f4360 landed after the original base d03120a28); AMENDMENT 1 is present.
Owned files: scripts/platformkit/execution/forward_capture_bridge.py (MODIFIED, minimal),
tests/platformkit/execution/test_forward_capture_bridge.py (MODIFIED, additive),
tests/platformkit/execution/test_forward_capture_bridge_keyed.py (NEW companion, named here
because the tracked test file is at its 300-line rail), this memo.
scripts/platformkit/execution/forward_replay_qualification.py and its frozen constants are
NOT touched. Construct tests only: no network, no archive run, no measured number produced
here. This is a linkage-correctness fix; it carries no calibration claim of any kind.

## BINDING BEFORE-CONDITION

### 1. master scripts/platformkit/execution/forward_capture_bridge.py, lines 50-84 (verbatim)

```
def _links(book_rows: list, state_rows: list, schedule: list, counts: Counter) -> dict:
    metrics, grouped, links = Metrics(), defaultdict(list), {}
    index = index_kalshi_events([r for r in book_rows if not r.get("_refusal")], metrics)
    for row in state_rows:
        try:
            _common(row)
            for key in ("date", "home_abbr", "away_abbr"):
                _text(row, key)
            if row.get("scheduled_start_utc") is not None:
                stamp(row["scheduled_start_utc"])
            grouped[(_text(row, "sport"), _text(row, "game_key"))].append(row)
        except (ValueError, TypeError, ArithmeticError) as exc:
            counts[str(exc)] += 1
            row["_refusal"] = str(exc)
    candidates = defaultdict(list)
    for (sport, key), rows in sorted(grouped.items()):
        metadata = {(r.get("date"), r.get("home_abbr"), r.get("away_abbr"),
                     r.get("scheduled_start_utc")) for r in rows}
        if len(metadata) != 1:
            counts["conflicting_state_linkage"] += 1
            continue
        date, home, away, start = metadata.pop()
        linked = link_game(sport, date, home, away, index, start, metrics)
        if linked.matched:
            candidates[(sport, linked.event_ticker)].append((key, linked.tickers))
        else:
            counts[linked.reason] += 1
    for game in schedule:
        options = candidates[(game["sport"], game["game_id"])]
        key = game.get("game_key")
        if (isinstance(key, str) and key.strip() and len(options) == 1
                and game["ticker"] in options[0][1] and key == options[0][0]):
            links[(game["sport"], options[0][0])] = game["game_id"]
        else:
            counts["LINKAGE_INVALID"] += 1
```

The whole four-field tuple is one set element, so one row that omits `scheduled_start_utc`
and one row that carries it are two elements and the key is refused.

### 2. game_market_link.link_game -- its scheduled_start_utc handling (verbatim, lines 168-181)

```
    if len(candidates) > 1:
        if not scheduled_start_utc:
            return LinkResult(False, reason="ambiguous_multiple_kalshi_events")
        if any(entry.get("scheduled_start_utc") is None for entry in candidates.values()):
            return LinkResult(False, reason="missing_market_scheduled_start")
        start = _timestamp(scheduled_start_utc, metrics or LINK_METRICS, source)
        if start is None:
            return LinkResult(False, reason="invalid_scheduled_start")
        candidates = {event: entry for event, entry in candidates.items()
                      if entry.get("scheduled_start_utc") == start}
        if len(candidates) != 1:
            return LinkResult(False, reason="no_unique_scheduled_start_match")
    event, entry = next(iter(candidates.items()))
    return LinkResult(True, event_ticker=event, tickers=tuple(sorted(entry.get("tickers", ()))))
```

The start is read ONLY when more than one dated candidate event survives the team match.
A single candidate links with `scheduled_start_utc=None`; several candidates refuse with
`ambiguous_multiple_kalshi_events`. Passing None is therefore fail-closed, not optimistic.

### 3. Reproduction of the measured conflict -- two-row construct through `_links`

Construct shaped from the real shard
C:/Users/neelj/nba-ai-system/data/cache/ingame_books_local/state/mlb/2026-09-22.jsonl
(READ ONLY; the builder streamed the leading rows solely to copy the row SHAPE and makes NO
census claim from that slice -- the 4924-row measurement is the spec author's). The two shapes:
`local_state_capture_v1` rows have no `scheduled_start_utc` key at all, `v2` rows carry it.
Both rows: sport `mlb`, game_key `823169`, date `2026-09-21`, home `SF`, away `MIN`; one
Kalshi event `KXMLBGAME-26SEP21SFMIN` in the index for that date and both team codes.

BEFORE (master forward_capture_bridge.py) and AFTER (round 1 of this row), same script,
`LINK` = `{('mlb', '823169'): 'KXMLBGAME-26SEP21SFMIN'}`:

| arm | BEFORE links | BEFORE conflict / INVALID / missing_start | AFTER links | AFTER conflict / INVALID / missing_start |
|---|---|---|---|---|
| two-row construct (v2 start + v1 missing) | `{}` | 1 / 1 / 0 | `LINK` | 0 / 0 / 1 |
| the same two rows, reversed order | `{}` | 1 / 1 / 0 | `LINK` | 0 / 0 / 1 |
| v2 row alone (control) | `LINK` | 0 / 0 / 0 | `LINK` | 0 / 0 / 0 |

The two row orders give identical counts, so the result does not depend on input order.

### 4. AMENDMENT 1 -- the keyed construct with team-evidence-free book rows

The orchestrator's real-archive run of the S390 candidate showed the per-field reduction
working (conflicting_state_linkage 0, state_rows_missing_start 4891) while all six scheduled
games stayed LINKAGE_INVALID with missing_directional_team_evidence 19: the Kalshi orderbook
rows carry no team evidence, so the directional linker cannot match a state game to an event.
Shapes confirmed READ ONLY (one row each, no census claim) from
C:/Users/neelj/nba-ai-system/data/cache/ingame_books_local/kalshi/mlb/2026-09-22.jsonl --
event_ticker `KXMLBGAME-26SEP212145MINSF`, ticker `...-MIN`, NO `home_abbr` / `away_abbr` key
on the row at all -- and from the sibling state shard: `local_state_capture_v2`, game_key
`823169`, date 2026-09-21, home SF, away MIN, start 2026-09-22T01:45:00.000000Z, while the
`v1` rows omit the start. The construct is that pair of state rows, that one book row and one
schedule entry `{mlb, KXMLBGAME-26SEP212145MINSF, ...-MIN, 823169}`, through `_links`.

BEFORE = the round-1 candidate (the per-field fix alone); AFTER = the same script and the same
constructs with AMENDMENT 1 and the codex r1 finding. `LINK` = `{('mlb', '823169'):
'KXMLBGAME-26SEP212145MINSF'}`; every arm is LINKAGE_INVALID 1 BEFORE and 0 AFTER.

| arm | BEFORE links / missing_start / invalid_* | AFTER links / missing_start / invalid_* |
|---|---|---|
| A1 keyed two-row construct (v2 start + v1 missing), team-evidence-free books | `{}` / 1 / none | `LINK` / 1 / none |
| B1 empty-string `scheduled_start_utc` on one row | `{}` / 1 / `['invalid_time']` | `LINK` / 2 / none |
| B2 empty-string date / home / away / start on every row | `{}` / 0 / `['invalid_date']` | `LINK` / 2 / none |

`missing_directional_team_evidence` is 1 in A1 and B1 on both sides; B2's all-missing date
reaches `link_game` as `None` and is refused `no_game_date` 1 on the AFTER side.

The three refusal arms of the same script, before and after (each `links: {}` and
`LINKAGE_INVALID: 1` on both sides -- the AFTER side adds the named reason):

| arm | BEFORE reason | AFTER reason |
|---|---|---|
| A3 keyed entry whose game_key has no state rows | (none; directional refusal only) | `state_key_absent` 1 |
| A4 keyed entry whose game_id has no book rows | (none; directional refusal only) | `book_event_absent` 1 |
| A5 legacy entry, no game_key | (none; directional refusal only) | `keyless_candidate_absent` 1 (FIX 1c) |

The script's A2 arm (the same two rows reversed) printed output identical to A1 on both sides;
the companion asserts both orders. `missing_directional_team_evidence` is still counted in
every arm: the keyed path adds evidence, it never hides the directional shortfall.

### 5. codex gpt-5.6-sol r1 BLOCKING finding -- an empty string was refused as invalid

`_links` validated `date`, `home_abbr`, `away_abbr` with `_text` and any non-None
`scheduled_start_utc` with `stamp` BEFORE grouping, so an empty string was refused
`invalid_date` / `invalid_home_abbr` / `invalid_away_abbr` / `invalid_time` and never reached
`_metadata`. The spec treats `""` as MISSING, like `None`. Arms B1 and B2 are that
reproduction: BEFORE they carry `invalid_time` / `invalid_date` and no link; AFTER no
`invalid_*` at all, the empty values counted missing and the date refused `no_game_date`.

## CHANGE

1. `_metadata(rows, counts)` (new, 11 lines) reduces the four metadata fields INDEPENDENTLY
   over their non-missing values (`None` and `""` are missing). Two different non-missing
   values in one field return None, and the caller counts `conflicting_state_linkage` and
   excludes the game as before; a field with no non-missing value reaches `link_game` None.
2. `counts["state_rows_missing_start"]` counts the grouped state rows whose
   `scheduled_start_utc` is missing, through the landed strict-int helper
   `forward_replay_policy.count`, so the shortfall stays visible even while the game links.
   It is an ADDED key: none was renamed or removed, `conflicting_state_linkage` keeps its
   meaning, and a repo-wide grep found no reader of either counter outside this module.
3. `_links` calls `_metadata` in place of the four-field set; nothing else in the bridge,
   in the qualification module, or in its frozen constants changed.
4. AMENDMENT 1, exact identity, plus FIX 1c. `_resolve(game, present, state_keys, index,
   candidates)` (new, 20 lines) decides EVERY schedule entry. A non-empty string `game_key`
   links by EXACT IDENTITY: the `(sport, game_key)` state group must have survived grouping
   and reduction -- else `state_key_absent` when no rows carry that key at all, and
   `state_key_conflicted` when rows exist but `_metadata` refused them; the Kalshi index must
   hold the entry's `game_id` with its `ticker` in that event's ticker set, else
   `book_event_absent`; and if the SAME group also linked through `link_game` to a DIFFERENT
   event, `linkage_disagreement`. On success `links[(sport, game_key)] = game_id`, the same key
   shape the landed state-row loop reads.
5. A LEGACY entry -- no `game_key` field at all -- takes the directional path: the retained
   candidates for its `(sport, game_id)` are filtered to those whose ticker set holds its
   `ticker`, and it LINKS to the unique survivor; two survivors are
   `ambiguous_keyless_candidates` and none is `keyless_candidate_absent`. An entry that CARRIES
   `game_key` with a non-string or blank value is neither keyed nor legacy: it is
   `invalid_schedule_game_key`, so a malformed key never degrades to the weaker path, and
   `link_game` still runs for every group so its refusal reasons stay counted.
6. `_duplicated(schedule)` (new, 5 lines) counts the multiplicity of `(sport, game_id)` and of
   `(sport, game_key)` over the whole schedule BEFORE any link is written; every entry whose
   either identity is claimed twice is refused `duplicate_schedule_identity`, in any order.
7. codex r1 BLOCKING finding. The pre-grouping validation loop now runs over `_META` and
   validates a field ONLY when its value is neither `None` nor `""`: an empty string is
   missing, never invalid, and a field with no non-missing value reaches `link_game` as `None`
   (refused `no_game_date` / `no_team_codes`) while an empty start is counted by
   `state_rows_missing_start`. Every reason in items 4-6 is counted and is LINKAGE_INVALID.

## FIX 1c -- codex gpt-5.6-sol r2 REJECT (3 blocking) and the Opus r2 CORRECTIONS (3)

BEFORE is the ROUND-1 CANDIDATE, not master: its text was reconstructed and re-diffed against
master to confirm it is the candidate sol and Opus reviewed. One script, one construct set
through `_links` plus one `load_native` arm. `EVENT` = `KXMLBGAME-26SEP212145MINSF`, `OTHER` =
`KXMLBGAME-26SEP21SFMIN`, state keys 823169/823170.

| arm | BEFORE | AFTER |
|---|---|---|
| one `game_key`, two `game_id`s, order [A, B] | links `{('mlb','823169'): OTHER}`, LINKAGE_INVALID 0 | links `{}`, duplicate_schedule_identity 2, LINKAGE_INVALID 2 |
| the same two entries, order [B, A] | links `{('mlb','823169'): EVENT}`, LINKAGE_INVALID 0 | links `{}`, duplicate_schedule_identity 2, LINKAGE_INVALID 2 |
| one `game_id`, two `game_key`s, order [A, B] | both keys link to EVENT, LINKAGE_INVALID 0 | links `{}`, duplicate_schedule_identity 2, LINKAGE_INVALID 2 |
| the same two entries, order [B, A] | both keys link to EVENT, LINKAGE_INVALID 0 | links `{}`, duplicate_schedule_identity 2, LINKAGE_INVALID 2 |
| that pair through `load_native` | failures `{EVENT: []}`, 2 state rows attributed to EVENT | failures `{EVENT: ['LINKAGE_INVALID']}`, 0 attributed, unlinked_state_row 2 |
| keyless entry, directional event present | links `{}`, LINKAGE_INVALID 1 | links `{('mlb','823169'): EVENT}`, LINKAGE_INVALID 0 |
| keyless entry, team-evidence-free books | links `{}`, missing_directional_team_evidence 1, LINKAGE_INVALID 1 | unchanged, plus keyless_candidate_absent 1 |
| key present, rows disagree SF vs SEA | conflicting_state_linkage 1 AND state_key_absent 1 | conflicting_state_linkage 1, state_key_conflicted 1, state_key_absent 0 |

(1) sol BLOCKING 1 and Opus CORRECTION 1. Duplicate keyed claims on one `(sport, game_key)`
were order-dependent and failed open; and after round 1 removed the `candidates` accumulator,
two entries claiming one `(sport, game_id)` BOTH linked with zero refusals, which end to end
merged two games' state rows into one event with `failures` EMPTY -- a regression against
master, which refused it. `_duplicated` settles both halves before any link is written. NAMING:
sol asked `linkage_disagreement` for the first half; Opus r2 gave both halves one name,
`duplicate_schedule_identity`, which shipped, and `linkage_disagreement` keeps its meaning.
(2) sol BLOCKING 2 and Opus CORRECTION 2. The previous lane's judgement -- this memo's own
round-1 CHANGE item 5 -- that a keyless entry can never link was WRONG and is RETRACTED. The
directional candidates are retained again and a legacy entry links to the unique candidate
carrying its ticker; team-evidence-free books still give `missing_directional_team_evidence` 1.
(3) sol BLOCKING 3 and Opus NOTE 3. `state_key_absent` fired for a key whose rows EXIST but
conflict. Present keys (`set(grouped)`) are now tracked separately from the conflict-free
resolved keys (`state_keys`); `state_key_absent` is counted only when NO grouped state rows
exist, and the conflicted case reports `state_key_conflicted` (exact name).

## TESTS

`tests/platformkit/execution/test_forward_capture_bridge.py` (tracked, additive):
`test_state_metadata_reduces_per_field`, n = 7 (CONSTRUCT), every case through `load_native`
end to end (JSONL written, read back, linked), each also asserting NO `invalid_*` counter:

the seven cases as (conflicting_state_linkage / missing_start / LINKAGE_INVALID): start +
absent 0/1/0 (the measured construct); `None` + absent 0/2/0; start + a DIFFERENT start 1/0/1;
start + `home_abbr="SEA"` 1/1/1; start + `""` 0/1/0; `""` + absent 0/2/0; `""` + `date` `""` 0/2/0.

DISCLOSURE for the tracked file: `test_absent_or_ambiguous_or_wrong_key` is renamed
`test_absent_or_wrong_state_key`, and TWO landed parametrize cases moved to the keyed file
(the ambiguous other-key case at keyed:74 and the keyless MISSING case at keyed:134) plus
three non-semantic reflows at :41, :52, :70 for the 300-line rail. Its six surviving cases --
two keyed and four present-but-unusable keys -- keep every assertion in the body and all six
still end at LINKAGE_INVALID 1 with no state row attributed.

`tests/platformkit/execution/test_forward_capture_bridge_keyed.py` (NEW companion, 204 lines,
named here because the tracked file is at the 300-line rail), n = 34 (CONSTRUCT), on the real
row shapes of section 4: the keyed two-row construct links with team-evidence-free book rows
in BOTH row orders; an extra unrelated state key does not block it; `state_key_absent` for a
wrong key and for no state rows; `state_key_conflicted` for a key excluded by a metadata
conflict, asserting `state_key_absent` 0 in the same construct; `book_event_absent` for an
absent event and for one whose ticker set lacks the ticker; `linkage_disagreement` when the
group links directionally elsewhere; `duplicate_schedule_identity` for BOTH halves in BOTH
schedule orders and once through `load_native`; a legacy entry linking through `_links` and
through `load_native`, refusing `keyless_candidate_absent` and `ambiguous_keyless_candidates`;
`invalid_schedule_game_key` for `None`, `""`, `" "` and an int; and both missing
representations of all four fields, with `state_rows_missing_start` 2 and no `invalid_*`.

NOTE 3 (Opus r3), the keyed SUCCESS arm through `load_native`: one v2 row (start) and one v1
row (no start) under key 823169, team-evidence-free books, one keyed entry. BOTH state rows are
attributed to `EVENT`, `failures` is `{EVENT: set()}`, `state_rows_missing_start` is 1, and no
`duplicate_*` counter fires. Their receipt seconds DIFFER on purpose: `forward_replay_io.py:180,192`
keys a state row by `(kind, ticker, game_key, at)` and state rows carry no ticker, so two rows
under one key at the SAME second collide and BOTH are refused `duplicate_native_record` --
landed behaviour this row does not change, and a shape the live capture must not emit.

NOTE 4 (Opus r3), what the keyed path trusts. With no team evidence on the book rows
`link_game` matches nothing, so `state_keys[(sport, key)]` is `None` for every group and
`linkage_disagreement` CANNOT fire: the schedule's own `(game_key, game_id)` pairing is trusted
ABSOLUTELY, the book-side check reduced to "this `game_id` exists and holds this `ticker`".
Tonight's attribution rests entirely on the S403 writer's `key = _text(game.get("game_key"))`
at `forward_schedule_writer.py:232`; a wrong key there misattributes and nothing here catches it.

Line counts by `len(text.splitlines())`: bridge 298, tracked test 298, companion test 204,
memo 300. `forward_replay_qualification.py` is byte-identical to master (`git diff --name-only
master` on it is empty), so no harness bar moved (B10).

Per-file runs only; no pytest invocation without an explicit single test file was made. All
POST-REBASE on 9103ae26e:
- `.../test_forward_capture_bridge.py -q -p no:cacheprovider` -- `60 passed in 2.43s`.
- `.../test_forward_capture_bridge_keyed.py -q -p no:cacheprovider` -- `34 passed in 0.72s`.
- `.../test_forward_replay.py -q -p no:cacheprovider` -- `49 passed in 1.82s` (landed, unchanged).
- `.../test_forward_schedule_game_key.py -q -p no:cacheprovider` -- `5 passed in 0.80s` (landed by S403).
- `tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -- `1 passed in 0.93s`; the bridge at 298 needs no allowlist entry.
- `.../test_forward_replay_qualification.py` -- `79 passed in 233.45s (0:03:53)`, PRE-rebase. Not
  re-run: `git diff d03120a28..master --name-only` touches neither `forward_replay_io.py` nor
  the qualification module (its 17 files are schedule sources/writer, their tests, and docs).

## NOT VERIFIED

- No run against any real archive by this lane: every BEFORE/AFTER above is a CONSTRUCT shaped
  from real row layouts, no shard processed, no calibration claim made.
- The Opus r1 CORRECTION asked this memo to record that an empty-string `scheduled_start_utc`
  was refused `invalid_time` before grouping: round-1 behaviour, arm B1's BEFORE column, now
  SUPERSEDED by the codex r1 blocking fix.
- The round-1 statement that a keyless entry can never link is RETRACTED by FIX 1c (2).
- `invalid_schedule_game_key` is a reason this lane INVENTED: no spec line names it. It keeps
  the four landed unusable-key cases refusing; treating them as legacy is one untested branch.
- `duplicate_schedule_identity` refuses on multiplicity alone, so two entries deliberately
  naming one `game_id` can no longer link. The landed writer emits one entry per game.
- The replay CLI and the qualification report were not exercised by this lane at all.
- Untested, fail-closed or benign but asserted nowhere: an unhashable metadata value or
  `ticker` (TypeError, caught by `load_native`, which empties `links`); and several Kalshi
  candidate events for one date and team pair with the start missing (`link_game`'s own
  `ambiguous_multiple_kalshi_events`). No `NativeEvidence.counts` consumer was re-verified.
