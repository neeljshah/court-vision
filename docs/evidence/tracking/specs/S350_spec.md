GAP S350 | sport nfl | worktree (claude sonnet, isolated) | log cx_s350_nfl_state_adapter
# NFL live-state adapter: the in-season, most liquid US sport has no state feed (astra round 10: "Add NFL next through a real adapter")

SINGLE PROBLEM: domains/nfl/ holds only feature_spec.py and ingest_manifest.py; there is no live game-state ingest, so NFL
markets cannot be paired with state for any in-play measurement, and DEFAULT_SPORTS in inplay_capture_loop.py omits nfl.

BINDING BEFORE-CONDITION (re-run, quote): `ls domains/nfl` shows no ingest_*_states module.

CHANGE (NEW files only; mirror the structure and as-of discipline of domains/soccer/ingest_soccer_states.py -- read it first):
1. domains/nfl/ingest_nfl_states.py (<= 300 LOC, stdlib + requests): poll the public ESPN NFL scoreboard JSON
   (site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard) and, per live game, normalize ONE state row:
   espn_event_id, kickoff_utc, home/away abbreviations, status (pre/in/final/delayed/postponed), period, clock_seconds_remaining
   in the period and game_seconds_remaining, home_score, away_score, possession team, down, distance, yardline_100
   (yards to the opponent end zone), is_red_zone, home/away timeouts remaining when present, last_play_id when present, plus
   receipt fields: request_start_utc, response_end_utc, http_status, source_ts if the payload carries one. Missing fields are
   None, never guessed. Pure function `normalize_scoreboard(payload, receipt) -> list[dict]` + a thin `poll_once(session)`;
   a CLI `--once --out <jsonl>` appends rows; honours REQUESTS_CA_BUNDLE (this box has TLS interception). No credentials.
   College football (ncaaf) via the same function with the league slug as a parameter.
2. domains/nfl/kalshi_nfl_ticker_map.py (<= 200 LOC): pure mapping from a Kalshi NFL game ticker/event (series KXNFLGAME; verify the
   actual series prefix from a saved sample if one exists under data/cache, else keep the prefix a parameter and say UNVERIFIED) to
   (date, away, home) and then to the ESPN event via date + team abbreviations, with an explicit alias table (e.g. LA/LAR, WSH/WAS,
   JAC/JAX) and an `unmatched` result -- never a nearest guess.
3. tests/domains/nfl/test_ingest_nfl_states.py: offline fixtures only (hand-built minimal ESPN-shaped payloads for pre, in-progress
   with possession/down/distance, halftime, overtime, final, postponed); assert normalization, clock arithmetic (15-min quarters,
   10-min OT), None-handling, the ticker map aliases and the unmatched path. NO network in tests.
4. Memo docs/evidence/harness/S350_nfl_state_adapter_2026-09-21.md with the exact finisher command for a live smoke.

CONTROLS: adapter row; no model, no probability, no measured number. ACCEPTANCE: per-file test passes; `python -m
domains.nfl.ingest_nfl_states --help` works; diff = NEW files only. Vocabulary follows contract Q6; automated scan required.
Memo ends with a NOT VERIFIED list (live endpoint shape is NOT VERIFIED unless the builder ran one --once smoke and says so).
