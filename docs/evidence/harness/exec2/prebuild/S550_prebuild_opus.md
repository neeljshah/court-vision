# S550 pre-build design critique (Opus, sole critic; astra unavailable) -- 2026-09-29

VERDICT: REVISE (7 BLOCKING, 11 NOTE). The design is sound and small; the blockers are all
places where the spec text, read literally, computes a DIFFERENT number than the probe it must
reproduce exactly, plus one input-drift problem that makes the bar unattainable as written.

Evidence gathered this session (read-only):
- Probe rerun NOW (19:57Z, master tree, peak_wset 88.7 MB): the three headline blocks still equal
  the spec's quoted values exactly, BUT `source_receipt_lag_s` is now p10 12.954 / p50 21.325 /
  p90 33.393 (spec quotes 12.92 / 21.327 / 33.492; committed r2 json 12.977 / 21.388 / 33.54).
  The 09-29 shards are being appended right now (mtime 14:57:37 CDT = 19:57Z, state/mlb 14,176,393
  bytes); 09-29 PHI@ATL live_min is 102.6 now (spec 89.6, commit 84.7); 09-29 CWS@HOU is still
  NO_LIVE_STATE and will go live tonight; 2026-09-30 shards do not exist yet and will appear at the
  UTC roll (the probe reads day+1).
- Import closure of quote_engine + venue_time (measured via sys.modules diff): project modules =
  scripts, scripts.platformkit, scripts.platformkit.execution, .position_decimal, .quote_engine,
  .thresholds, .venue_fees, .venue_time, scripts.platformkit.ingame, .ingame.quote_freshness, plus
  the LAZY function-level import .venue_fees_decimal (quote_engine.py:83-84). `scripts`,
  `scripts.platformkit`, `scripts.platformkit.execution` are NAMESPACE packages (`__file__` None).
  Stdlib leaves: bisect, datetime, decimal, enum, math, numbers, re, typing (+ json/hashlib/random/
  zlib the new modules add). No forbidden name reachable. `import psutil` pulls in socket, _socket,
  select, selectors (measured). tempfile/shutil/hashlib/subprocess pull in nothing forbidden.
- quote_freshness.py:60 parses `now`/`src_ts` with datetime.fromisoformat (inside the engine path).
- Fixture (h221 s550_real): 0 CR bytes in all three files, trailing LF; books = 574 `trade` +
  74 `snapshot`, zero duplicate trade_ids, zero None ids, taker_outcome_side == taker_side on all
  574, created_time fractions 6 digits x537, 5 digits x36, 4 digits x1. Source shard for the
  ticker holds 6912 trade / 706 snapshot / 13 snapshot_bulk / 81 trade_backfill_closed / 1
  trade_gap lines; 0 snapshot_bulk inside the fixture window, 4 non-trade/non-snapshot rows inside
  it (omitted by the fixture). State = 9 live rows 18:36:36Z..18:43:43Z + real final 21:07:29.857Z.
- Probe run ON the fixture (globals patched: P.BOOKS, P.STATE, M.SCHED): 1 game, status OK,
  window 150.0 live min, 561 in-window prints, 7 events (all `play`, all source clock), 13 grid
  instants, engine reasons quoted 12 / stale_book 1 (no state_change), all fills `through`
  (touch|60s through_share 16/16, eng|60s 8/8: zero depletion fills), 50 stat keys, every pool
  INSUFFICIENT (games 1). So generating s550_expected.json from the probe on this fixture WORKS.

## BLOCKING

B1. Censoring rule contradicts the probe (item 4). Probe `first_move` checks the gap BEFORE the
move at each snapshot and returns "moved" at the first move without looking further; a gap AFTER
the first move never censors. The spec's "if ANY gap ... (starting from t, ending at t+h) exceeds
10 s the instant is CENSORED" censors moved instants followed by a gap -> ev_*/ctl numbers change
-> exact reproduction fails. Replace item 4's second sentence with:
"Walk the in-window snapshots s in (t, t+h] in time order with last = t: if s - last > 10 the
instant is CENSORED; else if |mid(s) - m0| >= 1 it is MOVED; else last = s. After the walk, if
t + h - last > 10 it is CENSORED, else NONE. A gap after the first move does not censor (example:
move at t+4, no snapshot until t+60, h = 60 -> MOVED). Exactly 10 is not a gap. The before-receipt
test uses the same walk with h = lag and only when lag > 0."

B2. Event definitions and windows are missing (items 1, 5), so `ev_play|before_receipt` cannot be
rebuilt. Add a new item 5a:
"EVENTS: state rows with a parseable response_end_ts, stably sorted by it. Walk rows: a `final`
row ends the walk only after >= 1 event; rows whose status != live or whose state is empty are
skipped; a live row whose state dict != the previous live non-empty state (whole-dict comparison)
is an event, typed `score` if (score_home|home_score, score_away|away_score) changed, else
`period` if (inning, half, period) changed, else `play`; the previous state updates on every live
non-empty row. Source clock = parse_venue_time(state.last_play_ts) accepted iff receipt - 900 <
src <= receipt; otherwise the event uses the receipt as its time and is counted
`source_clock_absent_or_rejected`. ev_* statistics and the event lag list use SOURCE-clock events
only; the window start and seconds_since_change use the receipts of ALL events. Event windows
EV_WIN = (5, 15, 30, 60, 120) s; markout horizons stay (5, 30, 60, 120, 300)."

B3. Seeds and draw order contradict the probe (item 5). The probe uses THREE streams: joins/engine
grid = Random(seed), event-control grid = Random(seed + 1), control lags = Random(seed + 2), with
seed = zlib.crc32(ticker.encode()) % 100000, and draws one `choice` per control instant in grid
order INCLUDING instants later skipped for no prior book. The spec says the control grid uses
Random(seed) -> different ctl numbers. Replace item 5's first sentence with:
"Two clock grids per game, both every 30 s from first_in_window_snapshot_time + rng.uniform(0, 30)
while t < last_in_window_snapshot_time (strict): the JOIN/ENGINE grid uses Random(seed), the
EVENT-CONTROL grid uses Random(seed + 1), seed = zlib.crc32(ticker.encode()) % 100000. Control
lags: rng = Random(seed + 2); for EVERY event-control instant in grid order draw
rng.choice(source_event_lags) (drawn even when that instant is later skipped); an empty lag list
gives lag None for every instant (skipped, counted `control_lag_absent`)."

B4. Pool membership and game order are unstated but decide `games`, `n` and the bootstrap draws
(item 11). The probe drops per-game rows whose weight is 0 (tape_mo_print|60s has games 7 while
touch|60s|fill has 8), and the bootstrap resamples rows in insertion order. Replace item 11 with:
"POOLING: per-game sufficient statistics {key: [sum, weight]} are accumulated UNROUNDED in the
probe's loop order and persisted rounded to 4 dp under games[i].stats. A pool for (sport, key)
takes the per-game rows whose weight > 0, in game order = requested days sorted ascending, then
schedule-file order of the entries of that sport. Fewer than 3 such rows ->
{status: INSUFFICIENT, games: k}; else mean = sum/weight, 2000 draws with ONE random.Random(7)
per pool, each draw picks len(rows) rows with rng.randrange, ci90 = sorted draws [100] and [1899];
mean and ci90 rounded 4 dp, n rounded 2 dp, games int. The pool key set per sport is the union of
keys any game of that sport emitted (so NFL carries only ev_*/ctl keys). Exact equality with the
probe is NUMERIC equality after json.loads (982 == 982.0)."

B5. The bar is unattainable against the spec's frozen numbers: the inputs are growing (see
evidence; census lag has already drifted, and CWS@HOU going live will move the ev/ctl pools).
Replace the bar's reproduction clause with:
"AND a bracketed real-week run reproduces the probe: module run A, then the probe (the command in
BINDING BEFORE-CONDITION), then module run B, back to back over the same six days; receipts A and
B are byte-identical (which also proves the `inputs` identity block unchanged across the bracket)
and every pool entry of A equals the probe's pool entry numerically (all keys, not only the three
headline blocks). Run it only after every requested day's games have a final row or have passed
the 6 h cap and the day+1 shards have rolled; the spec's quoted numbers are the 19:xxZ 09-29
snapshot and are expected to change (09-29 CWS@HOU)."
Also restate the census/lag numbers in BINDING BEFORE-CONDITION as "at 2026-09-29 ~19:5xZ, inputs
still growing" (fresh rerun: source-to-receipt lag p10 12.954 / p50 21.325 / p90 33.393).

B6. CLI has no output-directory flag, so the subprocess tests would write into
docs/evidence/forward/exec_quality/ and the two fresh runs would overwrite each other (item 13/14,
CASES). Add to item 14: "`--out-dir` (default docs/evidence/forward/exec_quality); the
PYTHONHASHSEED test runs the CLI twice (PYTHONHASHSEED=1 and =2, env = a copy of os.environ plus
the seed, cwd = repo root) into two separate tmp out dirs and compares receipt bytes; the sidecar
must exist in both with keys peak_wset_mb, elapsed_s, python, platform (not 'differing-or-present')."

B7. The 300-LOC cap is not feasible for the pure core as specified. Probe logic without loaders is
~215 lines; the spec adds definitions, census builder, per-h censored counters, refusal counters,
the non-dict guard, depth_unknown counting and the paired difference -> ~300-320. A 301-line core
is an automatic reject with no legal place to split. Add to OWNED: "optional
scripts/platformkit/execution/exec_quality_audit_pool.py (<= 300 LOC, pure: pooling, bootstrap,
paired difference, the definitions table)". Keep the status ladder/census builder in the pure core
(testable without I/O); the day/sport loop, loaders, identity, writer and CLI stay in _io.

## NOTE

N1. Import-closure test design (item 15). Measured closure above. Use a STATIC AST walk: resolve
dotted names starting `scripts.` to files under the repo root (namespace packages have no
__init__/origin, so importlib find_spec().origin is None for them -- do not open it), follow
function-level imports (quote_engine.py:83-84 venue_fees_decimal is lazy and a runtime sys.modules
test would miss it), treat every other name as a leaf. Assert: project closure == the 7 modules
listed in the evidence plus the two new ones; no leaf in {requests, urllib, urllib3, http, socket,
websocket, ssl}; no project module name containing kalshi_client/auth/order/executor; the only
non-stdlib leaf (sys.stdlib_module_names) is psutil. psutil imports socket (measured): import it
ONLY inside the sidecar function and say so in item 15 ("psutil: measurement-only leaf, imported
lazily in the sidecar writer, not walked"). No temp git graph (landing lesson 2026-09-28).

N2. Item 2 "every timestamp goes through parse_venue_time and NOTHING else" is false for the engine
arm (quote_freshness.py:60 uses fromisoformat on the iso strings the probe builds). Replace with
"every timestamp READ FROM AN INPUT ROW goes through parse_venue_time; the engine arm formats
instants with datetime.fromtimestamp(t, timezone.utc).isoformat() exactly as the probe does."
Also `date.fromisoformat` is a parser that the grep test forbids: day keys must match
^\d{4}-\d{2}-\d{2}$ and next day = date(*map(int, d.split("-"))) + timedelta(1); a day not matching
is refused exit 2.

N3. Hidden fourth definition change (item 6): the probe puts None into `seen`, so a second
None-id trade is a duplicate and a first None-id trade is USED. The spec refuses None ids. Real
data has zero None ids for the fixture ticker; add to the change list "(iv) a None trade_id is
refused (probe used the first one); zero on the real week, verified by the refusal counter". Also
state: dedupe runs BEFORE field validation (a malformed first copy consumes the id, as in the
probe) and its scope is one (sport, day-pair) load across all served tickers and both day files.
Items (ii) and (iii) change no pooled value: (ii) keeps the print (counter only); (iii) only
affects rows on which the probe would raise (non-dict truthy state). So "both hold" is true once
B1-B4 are fixed.

N4. Marks and prior books use IN-WINDOW snapshots only (the probe's Game holds the window slice);
a mark past the window end is `mark_missing`. `vs_mid_at_fill` uses the prior-book rule at the fill
time; signs: long (resting bid) = mid - price and mark - price; short = price - mid and
price - mark. Engine reasons and the behind-touch table are counted over OK games only (game_stats
runs only when prints exist). Say all four in items 8-10.

N5. Item 10 "time since the last state RECEIPT" -> "time since the last EVENT receipt at or before
t (10**6 when none)" (the probe's ev_rec, not any state row).

N6. Item 5's paired difference is a NEW estimand, undefined. Either cut it (ponytail: the receipt
already carries both per-game stats, Q9 satisfied) or define: "`before_excess` = pooled
ev_play|before_receipt minus pooled ctl|before_matched_lag over games with both weights > 0; the
bootstrap uses one Random(7) and the SAME resampled game indices for both arms; INSUFFICIENT under
3 games." Recommend define (the plan's 7.5-point excess needs a receipted interval).

N7. Input identity (item 12): `path` must be relative to its root with forward slashes (tmp fixture
copies and Windows backslashes would otherwise change receipt bytes), and a requested shard that
does not exist is recorded {path, exists: false} (the fixture has no 2026-09-25 shards; the real
run's 09-30 shards do not exist yet). Schedules are CRLF in the main checkout (core.autocrlf=true;
09-24 schedule has 37 CR): hash LF-normalised bytes or the receipt differs between main and a
worktree. Delete the garbled "git-independent git_sha is NOT included" -> "no git sha".

N8. Writer (item 14): write bytes (`open(tmp, "wb")` with the encoded text) or newline="\n";
text mode on Windows emits CRLF. Empty inputs -> `pools {}` (not "every pool INSUFFICIENT": with
no games there are no keys). Schedule refusal must also cover an entry without `sport`. Books are
prefiltered by ticker bytes and state by game_key bytes (not "ticker or game_key" for both);
counters only, no pooled effect.

N9. Cut: the "changing a definition string changes the receipt sha" assertion (tautological:
definitions are inside the receipt). Replace with the one useful check: every emitted key in
games[*].stats and pools resolves in `definitions` (definitions keyed by the probe's literal key
strings, e.g. `touch|60s|fill`, generated from templates; 50 MLB keys). Keep the probe's key
strings verbatim (the spec's `join_touch_fill` style ids would break the orchestrator's key-by-key
diff against the probe).

N10. Census `q` is not nearest-rank: write it as "v[min(n-1, int(p/100*n))] of the sorted values,
rounded 3 dp" (the probe's q). Stable sorts: snapshots by response_end_ts, trades by created_time,
ties keep file order.

N11. Tests: 22 construct cases fit in one <= 300-line file only if items 2-11 boundaries are
table-driven (one parametrized function per item); put fixture + closure + subprocess in the
_real file. Commit the expected-file generator (patches exec2_audit_probe.BOOKS/STATE and
exec2_audit_measure.SCHED, calls main(["2026-09-24"])) as
tests/platformkit/execution/fixtures/s550_make_expected.py (not collected: no test_ prefix) so
s550_expected.json is reproducible; the 3-game renamed-ticker variant must be generated by the
same script into s550_expected.json, otherwise the >= 3-game path has no pinned oracle.

## EVIDENCE line: what it must say instead (the fixture as actually built)

"EVIDENCE (real-row fixture, orchestrator-built, byte-verbatim, archive already LF, 0 CR):
SOURCE 1 data/cache/ingame_books_local/kalshi/mlb/2026-09-24.jsonl, lines containing
KXMLBGAME-26SEP241435NYMTEX-TEX: 74 `snapshot` lines with response_end_ts in
[18:37:11Z, 18:44:11Z] (first 18:37:15.881438Z, last 18:44:08.528274Z) and 574 `trade` lines
selected by created_time in [18:37:11Z, 18:50:11Z] (NOT by response_end_ts: in-game prints arrive
by backfill minutes later), file order. Of the source's 13 snapshot_bulk / 81
trade_backfill_closed / 1 trade_gap lines, [NONE are included | ADD the 4 non-trade rows inside the
window plus one real snapshot_bulk line so `bulk_rows_ignored`/other-type counters see real bytes].
SOURCE 2 data/cache/ingame_state_local_v2/state/mlb/2026-09-24.jsonl, game_key 822842: 9 rows
18:36:36Z..18:43:43Z plus the real first final row 21:07:29.857231Z. SOURCE 3 the one schedule
entry (game_key 822842, sport mlb) as a 1-entry list. Probe on this fixture: status OK, window
18:37:31.751755Z..21:07:29.857231Z (150.0 min, under the cap), 561 in-window prints, 7 source-clock
`play` events, 13 join-grid instants, engine quoted 12 / stale_book 1, all simulated fills
`through`, every pool INSUFFICIENT (1 game). Real-row cases: (a) per-game stats and census equal
s550_expected.json; (b) the renamed 3-ticker variant's pools equal the pinned probe pools;
(c) all 574 created_time values parse including 36 five-digit and 1 four-digit fractions (zero
timestamp_rejected); (d) a print with lag > 0 keeps its receipt lag. NOT exercised by real rows
(construct only): duplicate trade_id, None trade_id, taker_side_conflict, depletion fills,
state_change pulls, score/period events, no_final_row, NO_DEPTH, TAPE_MISSING, the 6 h cap."
