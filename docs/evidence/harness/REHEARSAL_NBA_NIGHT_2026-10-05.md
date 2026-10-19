# Rehearsal: a paper night over a day with an nba served row (2026-10-05, all-games coverage lead)

VERDICT: PASS. All six night steps ran clean (night status COMPLETE, exit 0) on a day whose
served schedule held the real mlb/nfl rows PLUS one real nba row, and every mlb/nfl per-game
output is byte-identical (after JSON load) to the same night run without the nba row.
No code change needed. PAPER ONLY; nothing here is a scored result or an edge claim.

## Setup (scratch only; nothing written to the live roots)

- Code: scratch worktree C:/Users/neelj/cv-rehearse, branch adopt/all-games-2026-10-06-r5
  = master 3a78a91b5 + cherry-pick of switch 1 (5ca3dad7f) -> 8b5e11099. The night code is
  exactly master's (switch 1 touches only paper_desk_config.json + a test pin).
- Day: 2026-10-04, as_of 2026-10-05T06:00:00Z (the real night 10-04 shape; live receipt COMPLETE).
- Inputs: books/state shards for days <= 10-04 hard-linked read-only from the live archive (the
  19:35Z rehearsal's links); the 10-05 shards (still being appended live) replaced in scratch by
  static copies trimmed to the last full line. Capture view
  data/cache/ingame_capture_view_v2/{kalshi,state} = junctions to the scratch input roots.
  capture_supervisor, scoreboard training rows 09-30..10-04 + manifests, registry_e inputs
  09-30/10-02 and all live schedules copied in. Night-10-04 outputs removed from the scratch tree
  before each run. Scratch vault/S362 ledger (forward_replay TARGET_LEDGER resolves under the
  scratch worktree) reset to empty before each run; scratch night_attempts reset, so both runs
  use nonce paper-night-2026-10-04 in their own scratch ledgers.
- Variant A: live served schedule 10-04 (5 rows, mlb and nfl) + live full selection (13 rows).
- Variant B: A plus one real nba row in BOTH files:
  {"family":"maker_forward","game_id":"KXNBAGAME-26OCT04GSWLAC","game_key":"401918010",
   "scheduled_start":"2026-10-04T23:00:00.000000Z","sport":"nba","ticker":"KXNBAGAME-26OCT04GSWLAC-LAC"}
  (GS at LAC preseason; state shard nba/2026-10-04 has 36 rows, status pre; books have 2 rows per
  ticker 18:36Z-18:59Z, i.e. NO book rows inside the focus hour: the box slept ~19:00Z 10-04.
  What is rehearsed for nba is therefore the refusal / empty-window paths, not a scored game.)

## Command (each variant)

    cd C:/Users/neelj/cv-rehearse && python -m scripts.platformkit.execution.paper_night \
      --date 2026-10-04 --as-of 2026-10-05T06:00:00Z --repo-root C:/Users/neelj/cv-rehearse

(the real night entry point with the shipped budget; it builds and runs qualification,
fill_realism, week, scoreboard, history, e exactly as the 06:05Z night does.)

## Results

| step | A (no nba) | B (+nba) |
|---|---|---|
| qualification | RAN exit 0, 13 scheduled, refused 0 | RAN exit 0, 14 scheduled, refused 0 |
| fill_realism | RAN exit 0, row_count 142,618 | RAN exit 0, row_count 158,587 (nba shards read) |
| week | RAN exit 3 INCOMPLETE (accepted, as live) | same |
| scoreboard | RAN exit 0, 5 games / 416 ticks | RAN exit 0, 6 games / 439 ticks |
| history | RAN exit 0, 7,069 rows for night 10-05 | RAN exit 0, 7,069 rows (identical; 0 nba lines) |
| e | RAN exit 0, produced, 36 rows | RAN exit 0, produced, 36 rows |
| night | COMPLETE, receipt sha 722d8e9a... | COMPLETE, receipt sha 176701f0... |

No traceback, no uncaught exception, no 0-byte artifact in either run.

## Same-day mlb/nfl invariance (A vs B, nba items filtered out of B)

- qualification games: 13 non-nba entries equal; nba entry = verdict FAIL with counted reasons
  BOOK_CADENCE 1, COVERAGE_LOW 1, DECISIONS_LOW 1, LINKAGE_INVALID 2, STATE_GAP 1, TAPE_INCOMPLETE 1
  (family maker_forward_nba, served true). Pooled diagnostics counters grow by the nba rows.
- scoreboard: games, ticks, cells, paired_losses, settlement equal for the non-nba items;
  contrasts mlb and nfl equal, new nba contrast n_games 0 INSUFFICIENT; nba game unsettled, 23
  pre-live ticks, arm A only (B/C/D not reconstructible, counted).
- registry_e: rows, summary, full_population, selected_blocks, window equal; counts.unsupported_sport
  4 -> 5 (e does not score nba; counted refusal, not an error).
- history training rows 2026-10-05.jsonl and its manifest: identical (manifest nba_season_policy
  regular_only_v1; preseason not taken into training).
- fill_realism: COUNTS ONLY and pooled across sports (no per-game breakdown), so it cannot be split;
  B adds the nba shard counts (quotes_placed 1,566 -> 1,606, fills 0 in both). Not a per-game diff.
- week: only source hashes / daily artifact sizes change (qualification file grew);
  families_without_scheduled_games 3 -> 2 (nba family now has a scheduled game).

## NOT rehearsed / not verified

- An nba game with book rows inside its focus hour (none exists yet; first preseason tip under
  the live books capture is the first real one). Scored nba ticks are therefore unexercised.
- Soccer rows (none listed for this day). Tennis / ncaaf (switch 2/3) out of scope.
- The live vault/S362 ledger size effect (scratch ledger started empty, so step wall times
  here are lower than live).
- contract_preflight not run (owner-only).

Artifacts: scratchpad res A / res B copies (session scratch), compare script cmp.py; the scratch
tree C:/Users/neelj/cv-rehearse keeps run B's outputs until the next reset.
