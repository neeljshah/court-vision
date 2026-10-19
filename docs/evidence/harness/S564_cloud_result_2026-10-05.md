# S564 cloud result -- 2026-10-05 (desk-improve one-off; PAPER ONLY; calibration language only)

Row: S564 (nba and wnba live state enrichment is empty on real live rows). Branch `cloud/S564-2026-10-05`
from trunk c5a4cdf2. Spec: `docs/evidence/harness/S564_spec_2026-10-05.md` (+ AMENDMENT 1).
Codex is not available in this box: the pre-build critique and both verifier tiers were independent Opus
sub-agents (separate contexts, none of them wrote the build).

## Verdicts

| Step | Who | Verdict |
|---|---|---|
| Pre-build critique (astra role) | independent Opus sub-agent | REVISE, 14 items, all folded as AMENDMENT 1 (pbp mapper dropped in favour of S596 item 4) |
| CONTRACT tier (A/B/Q + spec) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS (memo only: verdict cells; qualify the unarchived 57-file table). Recomputed bar (a) 242/242, sha 1594de85...33f9 on both trees, its own 5,401-construct differential identical on both trees (sha 7aca2548...293a3); B2/B10 clean |
| ADVERSARIAL tier (probes + mutants) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS: 16 mutants, 12 red, 4 survived (M7 code out of the malformed-lastPlay guard, M13 duplicate refusal drops the code key from missing_reason, M14 code without the receipt gate, M15 legacy_unnamed renamed); four assertions added (test 20 cases), each survivor re-run and now red. 22 hostile shapes x 3 receipts plus both pollers: 0 raises, pre-S564 keys identical to trunk on all 110 outputs |

## What changed (additive only)

- `domains/basketball_nba/live_state_nba.py` (236 -> 278 lines): `enrich_nba_event` adds three keys to the
  block, nothing else: `missing_reason` ({field: named reason or None} over the ten S414 fields plus
  `last_play_code`), `last_play_code` and `last_play_code_present` (situation.lastPlay.type.id when it is an
  ASCII digit string 1..6 long; the frozen 92-99 list, `last_play_type` and the 10-entry census are
  untouched). `refuse_duplicate_enrichments` also nulls the code and names every field `duplicate_event`.
  `S564_KEYS` and `without_s564_keys(row)` let the older full-output pins project out exactly these keys.
- `domains/basketball_nba/live_state_census.py` (new, 25 lines): `enrichment_reason_counts(blocks)`, the
  counted roll-up {field: {reason: n}}; a pre-S564 block counts as `legacy_unnamed`.
- Tests: new `tests/platformkit/ingame/test_nba_state_enrichment_s564.py` (19 cases); two older pins
  (`test_schedule_instant_e2e.py`, `test_espn_play_clock_realrow.py`) now project out S564_KEYS only and
  keep their trunk values (the e2e test also asserts the added key set equals S564_KEYS).
- Not edited: src/, every seal-pinned file, `local_state_capture_sources.py`, `nba_pbp_source.py`,
  `nba_state_enrichment.py`, the register, DESK_STATE.md. No flag flipped; the pbp source is unchanged.

Named reasons (`MISSING_REASONS`): not_in_scoreboard_feed, competitor_absent, event_not_live,
situation_absent, possession_not_in_situation, last_play_absent, missing_receipt, invalid,
duplicate_competitor, play_code_unlisted, duplicate_event.

## Measurements (before -> after)

| Metric | Before (trunk c5a4cdf2) | After (branch) | n |
|---|---|---|---|
| Premise: committed ESPN basketball scoreboard events / competitors / live / target keys | 22 / 44 / 0 / 0 | same (fixtures unchanged) | 7 files, 2 empty (nba_20261019, wnba_20260928) |
| (a) named-missing cells, receipt 2026-10-05T00:00:00Z | 0 of 242 (every cell census reason `missing`, no name) | 242 of 242: not_in_scoreboard_feed 176 (22 x 8 lineup/fouls/bonus/timeouts), event_not_live 66 (22 x 3 possession/last play) | 242 (CONSTRUCT, exhaustive) |
| (a') same, receipt None | 0 of 242 named | 242 of 242 missing_receipt | 242 (CONSTRUCT) |
| reason vocabulary reached | - | 11 of 11 MISSING_REASONS reached by the construct list | 11 (CONSTRUCT) |
| (b) last-play code survives on live constructs | 1 of 4 well-formed codes kept, and only '92' via last_play_type ('558', '1', '123456' lost as play_code_unlisted) | 4 of 4 kept in last_play_code; 6 of 6 malformed (bool, int, '9a', '1234567', '', Arabic-Indic digit) refused | 10 (CONSTRUCT) |
| pre-S564 block keys, 23 events x 2 receipts | sha256 1594de85...33f9 | sha256 1594de85...33f9 (identical) | 46 blocks |

Reproduce (a): `PYTHONPATH=. python3 -c "import glob,json; from domains.basketball_nba.live_state_nba import enrich_nba_event as f; from domains.basketball_nba.live_state_census import enrichment_reason_counts as c; ev=[e for p in sorted(glob.glob('tests/platformkit/ingame/fixtures/s481_espn_*ba_*.json')) for e in json.load(open(p))['events']]; print(len(ev), c([f(e,'2026-10-05T00:00:00Z') for e in ev]))"`

## Tests (one file per process, `python3 -m pytest <file> -q -p no:cacheprovider`)

57 test files that import the capture or enrichment path were run on trunk and on the branch, one per
process, and the pass/fail counts matched file for file. Those tables are scratch output and NOT archived.
The 13 files below were reproduced independently by the CONTRACT tier (state_capture_sources 240 = 240,
local_state_capture 19 = 19 as well), with identical failing test ids on both trees:

| File (tests/platformkit/ingame/) | Trunk | Branch |
|---|---|---|
| test_nba_state_enrichment_s564.py | collection error (new names absent) | 20 passed (19 at verification + 1 correction case) |
| test_nba_state_enrichment.py | 80 passed | 80 passed |
| test_nba_state_enrichment_archive.py | 10 passed | 10 passed |
| test_schedule_instant_e2e.py | 13 passed | 13 passed |
| test_espn_play_clock_realrow.py | 9 passed | 9 passed |
| test_nba_pbp_source.py / _1c.py | 68 / 20 passed | 68 / 20 passed |
| test_nba_season_type.py | 45 passed | 45 passed |
| test_wnba_registration.py | 4 failed, 41 passed | 4 failed, 41 passed |
| test_wnba_registration_e2e.py | 6 failed, 6 passed | 6 failed, 6 passed |
| test_local_state_recovery.py | 12 failed, 6 passed | 12 failed, 6 passed |

The 22 red cases are pre-existing and clone-specific: each is `git show <sha>:<path>` of a commit the
shallow cloud clone does not hold (exit 128). Without the S564 projection, the build first turned 3 cases
red (2 in test_schedule_instant_e2e.py, 1 in test_espn_play_clock_realrow.py: full-output pins); with
the projection both keep their trunk values.

## Semantics a consumer must know

- `enrichment_changed` (nba_state_enrichment.py, not edited) compares the whole block minus the receipt,
  so it now also flips when a named reason changes (e.g. event_not_live -> situation_absent at tip-off)
  and on every new `last_play_code`. Pinned by test; any consumer counting change events must expect it.
- `last_play_code` is the raw ESPN play-type id. No vocabulary is claimed, learned or expanded; the
  `nba_enriched` feature set (seal-pinned) still reads only `last_play_type` 92-99, and parse_state output
  is asserted equal with and without the new keys.

## Fields that remain unfillable from the ESPN scoreboard event alone

lineup_home/away, team_fouls_home/away, bonus_home/away, timeouts_home/away: no committed ESPN
basketball scoreboard payload carries these keys (0 of 44 competitors), and the S414 memo already marked
them UNSOURCED (C1). After this build they read `not_in_scoreboard_feed` instead of an unnamed
`missing`. possession: no committed live event exists, so whether ESPN's live basketball `situation`
carries `possession` is NOT VERIFIED. last play: the register records well-formed codes outside 92-99 on
the six live WNBA 401918018 rows; on such rows `last_play_code` now carries the code (construct-tested
only; no real live row is committed). Usable fouls/bonus/lineups/timeouts therefore need a play-by-play
source.

## Enabling the play-by-play source on the Windows recorder (NOT VERIFIED there; not done)

The S433 `nba_pbp` source (cdn.nba.com liveData, opt-in via `OPT_IN_SOURCES`, not in the state2 argv)
is unchanged and stays OFF. Enabling it takes a **state2 capture restart**: a new dated relaunch script
cloned from `docs/operations/relaunch_state2_s502_2026-10-01.ps1` with `--sports
mlb,nba,nba_pbp,soccer,tennis,nfl,ncaaf,wnba` (optionally `--nba-pbp-player`), run by the owner or a
session in the 06:00Z-16:00Z window with no game live, with STOP_state2 and the RAM preflight. Before
that: one probe GET of the cdn.nba.com scoreboard from the recorder, because S433 recorded cdn.nba.com as
403 from that host (nba_pbp_player_state.py:25; DESK_STATE lane NBA "cdn.nba.com 403"). If it is still 403,
enabling it fills nothing and the next candidate is the ESPN summary/plays endpoint (same host as the
working scoreboard; not built, not probed here). Neither route fills WNBA rows from cdn.nba.com
(cdn.wnba.com unverified). The S596 measurement gate (>= 5 live games, request cost, RSS against the
state2 budget, 403 share) decides adoption; S596 item 4 owns mapping the pbp fields onto the enrichment
names, with these semantics: team fouls = personal fouls in the current period (a proxy), bonus only 1
or None, timeouts always not_in_feed, receipt carried.

The S564 code itself also reaches real rows only after a state2 restart (it runs inside the capture).

## NEW GAP lines from the tiers (not fixed here; for the orchestrator to row)

- A competitor key that is present but null (e.g. `"fouls": null`) is named not_in_scoreboard_feed, while
  the spec defines that name as "key absent" (live_state_nba.py `_named_reason`).
- The register row asks for a source to be chosen and enabled with a RAM and request-rate measurement.
  This build names the missing cells and keeps the raw code. S564 should NOT be closed as fixed; the
  source choice and enablement remain open (S596 gate).
- The 4 + 6 `git show` failures in test_wnba_registration*.py hide their base-bytes comparisons in every
  shallow cloud clone. They need a run in a full-history clone (the Windows landing step).
- Bar (a) on the committed fixtures can reach only 2 reason values. Live behaviour rests on constructs
  until a real live basketball scoreboard fixture is committed.
- Pre-existing, not S564's: no test pins the team_fouls upper bound (20); a mutant to 25 survives on trunk.

## NOT VERIFIED

- Any real live NBA or WNBA row: the ESPN host is blocked here and no data/ archive exists; no committed
  fixture holds a live basketball event.
- Whether ESPN's live basketball `situation` carries `possession`, and the real distribution of
  last-play codes.
- cdn.nba.com reachability from the recorder; ESPN summary/plays payload shape on a live game; RAM and
  request rate of either play-by-play route.
- Windows per-file test runs on the composed tree (landing step).

PORTABLE: yes (code and tests run on Ubuntu). Adoption is WINDOWS (state2 restart), so the row is MIXED.
