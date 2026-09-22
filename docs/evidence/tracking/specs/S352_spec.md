GAP S352 | sport mlb + nfl + soccer + nba (+ tennis if an adapter exists) | worktree MAIN tree, NEW files only (needs network + data/) | log cx_s352_local_state_capture
# Local live-STATE capture beside the S341 book capture: books without synchronized state cannot support any in-play measurement

SINGLE PROBLEM: the S341 local runner archives Kalshi books, trades and event market sets, but NO game state. Every
MEASURE-FIRST verdict in astra round 10 (state-change latency, late-game distortion, dead-time maker quoting with state-change
pulls) needs state receipts on the same clock as the book receipts ("state every 5-10 seconds").

BINDING BEFORE-CONDITION (re-run, quote): `ls data/cache/ingame_books_local/` shows venue dirs only, no state tree;
`ls scripts/platformkit/ingame/local_state_capture.py` fails.

CHANGE (NEW files only; never edit an existing adapter):
1. scripts/platformkit/ingame/local_state_capture.py (<= 300 LOC; stdlib + requests; helpers may go in
   local_state_capture_sources.py <= 300 LOC): one light process that, per sport, discovers today's games and polls live state:
   - mlb: MLB Stats API schedule + /api/v1.1/game/{game_pk}/feed/live (reuse the existing normalizer in domains/mlb by import if
     it is import-safe; otherwise keep the raw payload subset: inning, half, outs, base occupancy, balls/strikes, score, batter,
     pitcher, last play id + its timestamp).
   - nfl / ncaaf: domains/nfl/ingest_nfl_states.normalize_scoreboard if importable (row S350; optional import, skip cleanly
     if absent). ESPN returns 403 for ANY custom User-Agent; send no UA override (the requests default works).
   - soccer, nba: the existing ESPN-based normalizers under domains/soccer and domains/basketball_nba, by import, if import-safe.
   - cadence: live games every 7 s, pregame every 60 s, discovery every 5 min; AIMD back-off on 429/403; bounded concurrency.
   - every row: sport, game key (venue-native id), request_start_utc, response_end_utc, http_status, source timestamp if the
     payload carries one, normalized state dict, and a `state_changed` flag vs the previous row of the same game (so latency
     studies can find transition receipts cheaply). Append-only JSONL at
     data/cache/ingame_books_local/state/<sport>/<YYYY-MM-DD>.jsonl. Raw payloads are NOT stored whole (size); store the
     normalized row + a sha256 of the raw body.
   - heartbeat JSON with last-success time, rows written, games live per sport, 429/403 counts; stop-file
     data/cache/ingame_books_local/STOP_STATE; peak RSS target < 150 MB.
2. scripts/platformkit/ingame/game_market_link.py (<= 200 LOC, pure): map a state game key to the Kalshi event/tickers captured
   by S341 (date + team abbreviations with an explicit alias table per sport; `unmatched` is a result, never a nearest guess),
   so a later join never relies on file co-location (the multi-game contamination in the old corpus came from exactly that).
3. tests/platformkit/ingame/test_local_state_capture.py: offline fixtures only -- state_changed detection, stop-file, back-off,
   linker aliases + unmatched path, clean skip when an optional adapter import is missing.
4. Memo docs/evidence/harness/S352_local_state_capture_2026-09-21.md + the start/stop lines appended to
   C:/Users/neelj/AppData/Local/Temp/capture_runbook.txt.

CONTROLS: capture row; no model, no probability, no measured calibration number. No credentials anywhere. Hidden launch only
(pythonw + hidden_launch.py; the owner forbids console windows). Leave it running only if a bounded smoke is clean and RSS is
under the target. ACCEPTANCE: per-file test passes; a 10-minute live run shows rows for every sport that has a live or scheduled
game right now; diff = NEW files only. Vocabulary follows contract Q6; automated scan required. Memo ends with a NOT VERIFIED list.
