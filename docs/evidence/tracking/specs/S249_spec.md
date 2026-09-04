GAP S249 | sport nba (in-game) | worktree a18 | log cx_s249_nba_cdn_livedata_capture
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) -- read first. S-row: eye check = n/a.
CONTEXT: S218 attempt 2 census: on_court_five and substitution_event are needed for lineup-on-floor derivation but
  no raw NBA CDN liveData boxscore/playbyplay archive exists on disk; only ESPN payloads are archived.
PREMISE (step 0): re-measure and print: data/cache/nba_pbp_wallclock_raw = 2,008 archived ESPN payloads (398
  scoreboard + 1,610 summary), 777,521,676 bytes, 2024-10-22..2026-06-23; 0 raw NBA CDN liveData/boxscore payload
  path on disk (S218's "Raw NBA CDN boxscore archive" row = 0/0); the S218 16-cell field grid: on_court_five
  ABSENT_FROM_PAYLOAD 0/2,008 ESPN and NO_PAYLOAD_ON_DISK for the CDN parser; substitution_event
  PRESENT_BUT_DROPPED 1,606/1,610 ESPN (dropped, not a CDN capture) and NO_PAYLOAD_ON_DISK for the CDN parser. If
  falsified, STOP, write the memo, commit, report FALSIFIED.
LIMIT (step 1): probe the NBA CDN liveData endpoint (boxscore + playbyplay) once from the pod egress for one live
  or most-recent game id. If the response is blocked, 403/404, or unreachable at the pod's own IP, report CLOSED
  AT LIMIT and name the failing route/status; do not retry through a different egress to force a pass.
CHANGE (step 2): smallest additive change -- one new pod-side capture script under scripts/platformkit/ingame/ that
  polls the NBA CDN liveData boxscore and playbyplay routes for live games, gzips each poll's payload to one file,
  and appends a JSONL manifest row (game_id, route, poll_ts, bytes, sha256) per file so a restart never duplicates
  or loses a poll; stops by READING a stop-flag file; reuses the existing 429/backoff pattern already used by
  ingame_book_depth_kalshi.snapshot_market; own nohup setsid nice job, unique /tmp log, no git on the pod; report
  files you would deploy and deploy nothing (B5). Rails: additive only; helper <= 300 lines
  (test_loc_rail_scope.py); never write data/ (never data/registry/); no flag on; no edits under src/ kernel/ api/
  intel/ scripts/team_system/; register and ledger untouched.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = raw CDN payloads archived with a manifest row per file; a re-run of the S218 field census over
                  the archived payloads reporting on_court_five and substitution_event KEPT counts; denominator =
                  every poll attempt the run recorded, failed/blocked polls labelled and counted separately
  before        = 0 raw NBA CDN payloads on disk; on_court_five and substitution_event have no CDN row today (S218)
  bar           = >= 30 raw CDN payloads archived across live-game poll sessions; manifest row count == archived
                  file count (0 missing, 0 duplicate (game_id,route,poll_ts)); the field census shows
                  on_court_five KEPT on at least 1 archived payload. A measured-blocked LIMIT is a valid result
  n             = >= 30 archived payloads (or the LIMIT count if blocked)
  eye check     = n/a (S-row); reproduction = the verifier recomputes the field census and duplicate count from
                  the archived gzip payloads and manifest alone
  must not move = the 2,008-payload ESPN archive byte-identical; boxscore_read.py / ingame_live_state.py unedited;
                  no flag on
NON-TAUTOLOGY: count blocked/failed polls in the denominator with their status codes; do not drop them to inflate
  the KEPT rate.
EVIDENCE: docs/evidence/harness/S249_nba_cdn_livedata_capture_2026-09-04.md -- manifest sample, field census table,
  blocked-poll tally, a NOT VERIFIED list, summary JSON.
TEST: scripts/platformkit/ingame/test_s249_nba_cdn_livedata_capture.py -- one new per-file test; run only it.
REPORT: payload count, manifest, census, LIMIT verdict, test, SHA. Commit by pathspec, no push. NEVER PARK.
