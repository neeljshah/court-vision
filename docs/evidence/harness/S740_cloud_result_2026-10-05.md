# S740 cloud result 2026-10-05 -- tennis SERVED path (player-name link + schedule selection)

Row: S740 (ALL-SPORTS block), one-off cloud run with the owner override (row named, not picked
from DESK_STATE). Branch `cloud/S740-2026-10-05` (pushed; trunk untouched, nothing landed).
PAPER ONLY. Coverage and calibration language only; no venue or sports host was contacted.
Spec: `docs/evidence/harness/S740_spec_2026-10-05.md` (+ AMENDMENT 1 from the critic, AMENDMENT 2
from the builder). PORTABLE: yes (pure code, Ubuntu); adoption is WINDOWS.

## Verdicts

Codex is not available in this box. Every review tier was an INDEPENDENT Opus sub-agent that did
not write the code (spawned with the Agent tool):

| Tier | Agent | Verdict |
|---|---|---|
| Pre-build critique (astra role) | independent Opus sub-agent | REVISE, 15 items, all folded as AMENDMENT 1 |
| CONTRACT (VERIFIER_CONTRACT A/B/Q + amended spec) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS (2): four link cases asserted only part of event + served ticker (fixed, corrections 1, 42eb3890); the memo path was absent at its start (it was pushed in 9659a77a during its run) |
| ADVERSARIAL (mutations + probes) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS: 32 mutants, no forbidden mis-link, no crash; 4 spec-relevant survivors (M3c subset match, M20 duplicate_event, M26 None listing date, M7 live status + M21 start == selected) closed by test-only corrections 2 |

One correction round, test-only, production code unchanged since 3a346611. After corrections 2 the
builder re-ran the five surviving mutants on a scratch copy (`git archive HEAD` + the corrected
test): all five KILLED (each 1 failed, 23 passed). Neither tier returned REJECT, so no second
verification round was owed. OLD case (CONTRACT finding 7): at the test's date 2026-10-05 the
trunk linker refuses `no_kalshi_event_for_date_and_team` (premise d, listing date 10-04); at
2026-10-04 it refuses `missing_directional_team_evidence` (premise b). Old code refuses either way.

## What was built (new files only; no existing file edited)

- `scripts/platformkit/ingame/tennis_market_link.py`: indexes Kalshi rows of the series
  KXATPMATCH and KXWTAMATCH only. It keeps identity fields per event and nothing else: tour,
  listing date, ticker to `raw_market.yes_sub_title` (taken from `snapshot_bulk` rows only), and
  conflict. `link_match` links a game only when all of these hold:
  - the tour-qualified series fits the game key (`atp:` to KXATPMATCH, `wta:` to KXWTAMATCH);
  - the folded full names of BOTH players form the exact token multiset of the event's two titles;
  - the listing date is no later than match day + 1 and no more than 7 days before it;
  - the event has exactly two titled markets;
  - each ticker's suffix code agrees with its title.

  Otherwise it refuses with one named reason. The served ticker is the market of the HOME player
  in the source row.
- `scripts/platformkit/execution/tennis_schedule_select.py`: selection is pre-match and
  prospective only. It reads forward_schedule_sources-shaped rows, keeps those whose start falls
  on local day D, and emits the 7-key `schedule_entry` shape, with refusal counts. The book reader
  is bounded:
  - it opens only `kalshi/tennis/<date>.jsonl` for dates in [D-8, D+1];
  - it prefilters on a substring of the series before parsing JSON;
  - it keeps identity fields only.
- `tests/platformkit/ingame/test_tennis_market_link.py`: 24 CONSTRUCT cases.
  - Book rows are constructed in the committed s516 row shape, with the title under `raw_market`
    shaped like the Kalshi market in test_inplay_kalshi.py:257-266.
  - State rows are the committed verbatim s483 tennis fixture.
  - Doubles go through the real `domains/tennis/ingest_espn.parse_scoreboard` on the committed
    scoreboard fixture.

Refusal strings:
- Link: unsupported_tour, missing_player_name (this is how doubles arrive), placeholder_player_name,
  same_player, ambiguous_player_name, name_unmatched, tour_mismatch, outside_listing_window,
  ambiguous_multiple_kalshi_events, market_count, title_conflict, code_contradiction.
- Select: not_pregame (a pre-match walkover arrives as not_pre), not_prospective,
  missing_scheduled_start, other_local_day.

## Commands run (per file, this box, Python 3.11)

- `python3 tools/desk_bin/run_files.py . tests/platformkit/ingame/test_tennis_market_link.py`
  -> 24 passed (after corrections 2; 24 test functions, 24 CONSTRUCT cases)
- `python3 -m pytest tests/platformkit/ingame/test_tennis_market_link.py -q` -> 24 passed
- neighbours (CONTRACT tier): `tests/platformkit/ingame/test_capture_scheduler.py` -> 150 passed,
  1 failed (`test_fix1b_runner_unrelated_source_unchanged` runs `git show master:...`; this clone
  has no local master ref; unrelated to S740); `scripts/platformkit/ingame/test_tennis_outcome_resolver.py`
  -> 15 passed
- must-not-move: `git diff --name-status origin/trunk` -> only the five S740 files, all added
- s483 reproduction (CONTRACT A2): 448 rows, 448 unique game_key, 329 final -> not_pregame,
  119 pre -> missing_scheduled_start, 0 non-null scheduled_start_utc, 97 empty-name rows

## Team-sport / fixed-duration / mlb-nfl assumptions (file:line on trunk 2026-10-05)

The full inventory is in the spec (ASSUMPTION INVENTORY, corrected by A1.14). These are the ones
that block serving tennis:

- c `scripts/platformkit/ops/paper_desk_actions.py:84-86`: the inline allowlist ("mlb","nfl")
  raises invalid_sports.
- c `docs/operations/paper_desk_config.json:2-5`: sports = [mlb, nfl].
- a `scripts/platformkit/execution/forward_schedule_writer.py:135-172`: the team path. It never
  links a player-named match, because it compares names with codes (team_code_set_mismatch at :163).
- c `scripts/platformkit/ops/paper_desk_issue_capture.py:97`: shard scan ("mlb","nfl").
- b `scripts/platformkit/ops/paper_desk_issue_capture.py:16,48`: tennis gets the 10800 s default window.
- b `scripts/platformkit/execution/forward_replay_qualification.py:16`: WINDOW_S = 3600 for every sport.
- b `scripts/platformkit/ingame/capture_scheduler.py:123`: focus [start-120, start+3600).
- b `scripts/platformkit/ingame/capture_scheduler.py:113` and
  `scripts/platformkit/execution/schedule_d1.py:119`: at most two starts per rolling hour,
  POOLED across all sports.
- a `scripts/platformkit/ingame/local_state_capture_sources.py:249-250`: state home/away follows
  competitor ORDER, while the schedule source (forward_schedule_sources.py:75-81) uses homeAway.
  The link matches by names in both directions, so this does not mis-orient a served ticker.
- c `scripts/platformkit/execution/forward_schedule_sources.py:121`,
  `scripts/platformkit/ingame/local_state_capture_sources.py:26`: tours are atp and wta only.
  There is no Challenger state source.

Already fine:
- families_maker_forward.json:26-37 declares maker_forward_tennis.
- kalshi_series_scope.py:49-50 and the books runner's default sport list (local_capture_runner.py:239)
  already capture tennis.
- capture_scheduler.py:116,230 expects a two-market pair, which fits tennis.

## PROPOSED diffs (not applied; seal or S515-memo pinned, or adoption-only)

Pin grep (run first):
- No PREREG names any of the touched or proposed files except game_market_link.py (S490 addendum
  PREREG_2026-09-30_S490_DEPENDENCY_ADDENDUM.json), which this row does not edit.
- `docs/operations/paper_desk_config.json` appears in the S515 memo (line 37, as an eol rule).
  It is treated as memo-pinned, so its change is PROPOSED only.

P1 `scripts/platformkit/ops/paper_desk_actions.py:85`
```
-                or any(s not in ("mlb", "nfl") for s in sports)):
+                or any(s not in ("mlb", "nfl", "tennis") for s in sports)):
```
P2 `docs/operations/paper_desk_config.json:2-5`
```
-  "sports": ["mlb", "nfl"],
+  "sports": ["mlb", "nfl", "tennis"],
```
P3 (SKETCH, not a literal patch) `scripts/platformkit/execution/forward_schedule_writer.py` (build_schedule, before the team
path): route tennis away from `_latest`/`index_kalshi_events`. Today the team path reads every
book row, which blew the 512 MiB cap in the S493 measurement.
```
+    if sport == "tennis":
+        from scripts.platformkit.execution.tennis_schedule_select import select_from_archive
+        result = select_from_archive(games, Path(books_root), day, selected, local_tz=local_date_tz)
+        entries.extend(result["entries"]); refusals["tennis"] = result["refusals"]
+        continue
```
(The exact insertion point and variable names must be fitted to the writer on the laptop. The
writer is not seal-pinned, but its D1 output is evidence, so the change goes in with its own
verifier pair.)

P4 `scripts/platformkit/ops/paper_desk_issue_capture.py:97`
```
-    sports = ("mlb",) if name == "polymarket" else ("mlb", "nfl")
+    sports = ("mlb",) if name == "polymarket" else ("mlb", "nfl", "tennis")
```
Leave `WINDOWS` (:16) without a tennis entry for now. Tennis then uses the 10800 s default, and
a measured window is a follow-up (NOT VERIFIED).

NOT proposed, on purpose:
- `forward_replay_qualification.py:16` WINDOW_S and `capture_scheduler.py:123` are evidentiary
  windows. Moving them per sport is a moved bar (B10/Q3). Tennis is qualified on the same first
  hour as every other sport until a new row seals a match-length window.

## NOT VERIFIED (needs the Windows recorder, live captures or data/ the clone lacks)

- The archive link rate. No tennis link was run on a real books shard.
- That archive `snapshot_bulk` rows for KXATPMATCH and KXWTAMATCH carry
  `raw_market.yes_sub_title`, and that the suffix codes agree with surname_codes. The 2026-07-03
  resolver check (92 of 100) used the code-to-name route, not titles.
- The listing-date window constants: LISTING_GRACE_DAYS = 1 and MAX_LISTING_LEAD_DAYS = 7 are
  unmeasured.
- That forward_schedule_sources tennis rows carry a usable `scheduled_start_utc`. ESPN tennis comp
  dates may be order-of-play placeholders.
- That the committed s483 state rows' null start is still the case after the S502 adoption.
- schedule_d1 RSS with tennis wired. The reader is bounded in a construct case (tracemalloc peak
  under 8 MiB on 50,000 non-match rows), but the 9-day window on the real 2.5 GB/day archive was
  not timed.
- How many tennis matches the pooled two-starts-per-hour cap leaves for tennis. No served count
  is quoted.
- Retirement settlement, which stays with S493. Challenger coverage, which has no state source.

NEW GAP (no id allocated here; the S746-S749 block is the dispatcher's):
- STALE EVENT (adversarial): the link ignores market status, so a finalized event for the same
  pair inside the 7-day lead window links instead of refusing (capture later refuses it as
  scheduled_market_unavailable, but the row takes a capacity slot). Filter on
  `raw_market.status` before wiring (ADOPTION step 4a).
- POOLED HOURLY CAP (adversarial): the selector emits every linked start; 3 starts inside one
  hour make capture_scheduler.schedule_rows void the WHOLE schedule unless schedule_d1's capacity
  subset runs after it (ADOPTION step 4).
- CODE FOLD (adversarial): surname_codes reads the raw title, so accented or curly-apostrophe
  surnames (Coric with accent, O'Connell with U+2019) refuse code_contradiction: coverage loss,
  not a mis-link.
- PLACEHOLDER VARIANTS (adversarial): "Q", "Winner of R1" refuse name_unmatched, not
  placeholder_player_name (still refused).
- HOMONYM SCOPE (contract): ambiguous_player_name looks at every indexed event, inside or outside
  the listing window; coverage effect unmeasured.
- duplicate_event (contract): a selector refusal outside the A1.13 table; now asserted by a case.
- SERIES CROSS-CHECK (adversarial): the index trusts the row's series field without checking the
  event ticker prefix; the recorder sets series from the series it queried, so implausible.
- CHALLENGER: KXATPCHALLENGERMATCH has no state or schedule source (tours atp, wta only), so it
  cannot be served by this path.

## ADOPTION LIST (Windows recorder, in this order)

1. Land `cloud/S740-2026-10-05` on trunk after the Windows per-file re-test:
   `python -m pytest tests/platformkit/ingame/test_tennis_market_link.py -q` (expect 24 passed).
   No capture restart is needed; the modules have zero callers.
2. Copy verbatim archive rows into a fixture directory `tests/platformkit/ingame/fixtures/s740_real/`
   on the laptop, using a strict row-copy script with no edits:
   a. From `data/cache/ingame_books_local/kalshi/tennis/<D>.jsonl` (D = a recent full day):
      - every `record_type == "snapshot_bulk"` row for 3 KXATPMATCH events and 3 KXWTAMATCH
        events, both tickers of each;
      - one `record_type == "snapshot"` row per ticker;
      - one snapshot_bulk pair from KXATPCHALLENGERMATCH;
      - one pair from a derivative series (KXATPSETWINNER).
   b. From `data/cache/ingame_state_local_v2/state/tennis/<D>.jsonl`, the rows for the same
      matches, plus one each of:
      - a pre row and a live row;
      - a final row whose winner has no more sets than the loser (a retirement);
      - a final row with 0-0 sets (a walkover);
      - an empty-name (doubles) row;
      - a TBD row.
   c. The forward_schedule_sources tennis output for D (the `tour_receipts` and game rows the D1
      run records), so the start-time field is a verbatim row.
   Then add one real-row test that asserts each linked event equals the event the copy script
   recorded by hand. The fixture must pass contract_preflight; the owner ruling on the fixture
   rule (DESK_STATE section 6 item 3) applies.
3. Measure on the archive (laptop, read-only, under the RAM guard):
   - the listing-lead distribution: ticker listing date vs ESPN match day for every
     KXATPMATCH/KXWTAMATCH event of 7 days;
   - the link rate with refusal reasons over the same days;
   - the peak RSS of `select_from_archive` on one day.

   Set or confirm LISTING_GRACE_DAYS and MAX_LISTING_LEAD_DAYS from that distribution, in their
   own commit with the measurement.
4. Before wiring, a small code row: (a) refuse events whose `raw_market.status` is not open
   (STALE EVENT gap; verbatim status values come from step 2a); (b) make sure schedule_d1's
   capacity subset runs AFTER the tennis entries are merged, so the pooled two-per-hour rule
   never voids the schedule. Then apply P3 (writer routes tennis to the bounded selector) with
   its own verifier pair. Run
   `schedule_d1 --sports mlb,nfl,tennis` once by hand for a past day and check that the peak RSS
   stays under the 512 MiB schedule cap. No capture restart.
5. Owner decision: under the pooled two-per-hour cap, which sport keeps a contested hour.
   schedule_d1's capacity subset decides today.
6. Apply P1 + P2 + P4 in one commit (allowlist, config sports, issue-capture shard scan).
   - These are read by the tick at its next run. NO capture restart.
   - paper_desk_schedule.py:28,58-59 and paper_desk_evidence.py:269 then expect census and run
     per_sport keys for tennis. Check the first tick's status.json for run_scope_mismatch.
7. Books capture: NO restart needed for served rows. The runner already captures every tennis
   series (default sport list) and reads the schedule pointer each tick. Confirm one scheduled
   tennis focus in the books heartbeat after the first D1 with tennis. If the focus does not
   appear, a books relaunch between games (06:00Z-16:00Z) is the fallback.
8. State capture: NO restart. state2 already runs `--sports ...,tennis,...`.
9. First night with tennis: read `docs/evidence/forward/qualification/<D>.json` for tennis per
   game. The fixed 3600 s window is expected to report coverage on the first hour only.
