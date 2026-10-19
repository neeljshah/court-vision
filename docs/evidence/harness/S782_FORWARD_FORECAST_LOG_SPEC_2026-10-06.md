# S782 -- Forward pregame forecast log (spec, 2026-10-06)

PAPER ONLY. Calibration and proper-score language only (Brier, log loss, intervals). Nothing in this
row states or implies that any forecaster is sharper than the market; a TRAILS or INSUFFICIENT
reading is published with the same discipline as any other. Slate row R3 of
`docs/evidence/harness/QUANT_EVIDENCE_BUILD_SLATE_2026-10-06.md`.

Deliverables of this lead (no code): this spec, the prereg DRAFT
`docs/evidence/forward/forecasts/PREREG_FORECAST_LOG_PROPOSED_2026-10-06.json`, register rows
S782 + S782a..S782d in `docs/evidence/HARNESS_GAPS_2026-09-03.md`.

## 0. Premise check (fresh reads, 2026-10-06 ~08:5xZ)

| Question | Finding | Evidence |
|---|---|---|
| Does any pregame forecaster run daily today? | **NO, for any sport.** The served producer `predict_service` is dark: heartbeat `cycle_count 0`, `note boot-beat`, newest served file 2026-07-27. | `data/frontend/predict_service/_heartbeat.json`; `data/frontend/predict_service/nba/latest.json` mtime 07-27 15:05; memory note served_stack_dark_2026_09_24 (confirmed, not re-diagnosed) |
| Which NBA pregame forecaster is MEASURED against a close? | `scripts/platformkit/proof_nba/ml_accuracy.py::_walk_forward_elo` (MOV Elo, K 20, HFA 60, init 1500, 538 MOV multiplier, NO season regression), reading `load_box` from `proof_nba/asof_box_accuracy.py`. Holdout n=372: Brier 0.1735 vs proportional close 0.1672, gap +0.0063, CI [-0.0042, +0.0168], MATCHES_CLOSE, MDE 0.0150 (Shin close: +0.0069, CI [-0.0038, +0.0175], MDE 0.0152). Underpowered: cannot tell parity from a deficit the size of MLB's. | `docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md` table + sensitivity table; `docs/evidence/CANONICAL_FIGURES.json` keys nba_ml_pregame_vs_close_shin / _proportional |
| Other sports | MLB moneyline Elo TRAILS_CLOSE (+0.0039, CI [+0.0028, +0.0051], n=13,992); soccer measured row is O/U 2.5 (TRAILS_CLOSE +0.0076), NOT the Kalshi three-way winner market; NFL has only an unmeasured baseline (`scripts/platformkit/nfl_game_model.py`, nflverse, licence not in the ledger). | DM_RECOMPUTE table; `scripts/platformkit/nfl_game_model.py:1-7` |
| Is the NBA input corpus current? | **No.** `data/domains/basketball_nba/espn_boxscores.parquet` = 1,977 rows 2024-10-22..2026-05-24, mtime 06-15, sha256 9f52c38a...2949 (= the DM_RECOMPUTE pin). 2026 playoffs after 05-24 are missing. No periodic NBA ingest caller exists (`autonomy/label_finals_refresh.py` SPECS cover soccer_intl, mlb, wnba only, :225-237). The fetcher exists: `domains/basketball_nba/ingest_espn_box.py::ingest_range(dates, out_path=...)` (no season-type column; preseason must be excluded by date). | read-only parquet read 08:5xZ (free RAM 4,665 MB) |
| The second NBA Elo (`domains/basketball_nba/ratings.py`, season regression) | Exists, NOT measured against a close in DM_RECOMPUTE. Not used: the log uses the measured function so it starts from a published number. | `ratings.py:7-9, 95-121` |
| Pre-start Kalshi mid source | `data/cache/ingame_books_local/kalshi/nba/<UTC day>.jsonl`. On 10-05 every KXNBAGAME ticker had a `snapshot_bulk` row every ~23-24 min from 13:55Z to 23:47Z (26 rows for LAL at SAC home side), with yes_bid / yes_ask; future games (including 10-20 / 10-21 events) are already listed. Kalshi `occurrence_datetime` is NOT the start (LAL at SAC: 05:00Z = start + 3 h); scheduled_start comes from ESPN via `execution/forward_schedule_sources.fetch_schedule('nba', D)`. | grep over 2026-10-05.jsonl (33,482 lines; KXNBAGAME 15,053) |
| Serving rule | S751 (landed 19f694487) sizes focus by [start-120 s, start+3600 s); it decides which games get FOCUS (5 s books), not which games get bulk snapshots. The log needs only bulk, so every listed game is in scope, served or not. | register S751 row |
| Seal discipline | PREREG JSON = {amendment, effective_from, implementation {path: sha256}, sha256 (payload), supersedes}; pinned by a test helper (`tests/platformkit/execution/s469_seal_helper.py`). DESK_STATE section 2: never two identity changes in one night; consolidated seal A 10-06, commit B 10-07, then a FREEZE of the in-game scoring identity; S644 PREREG_R2 alone before 10-20; S721 alone after commit B. | `docs/evidence/forward/scoreboard/PREREG_2026-10-03.json`; `docs/operations/DESK_STATE.md` :62-81 |
| Public allowlist | `+ docs/` already exports `docs/evidence/forward/forecasts/**` publicly. Code under a new package is NOT exported until a `+` line is added. | `scripts/hooks/public_allowlist.txt:32-40` |
| Licences | Our own p_home: ours, publishable. Kalshi per-game prices: LICENCE_LEDGER row 11 **UNREAD** -> per-game mids may NOT be published; only aggregate scores. NBA results/box: row 1 ESPN **DECIDE** -> per-game outcome bits stay private until the owner rules (a final score is a public fact checkable on any scoreboard, but the row is undecided). | `docs/evidence/LICENCE_LEDGER.md:28, 38, 351-364` |

Consequence: the log starts from a **gap**, not a running forecaster. S782a builds the daily
producer around the measured function (imported, never re-implemented).

## 1. What the log starts honest about

First line of every weekly file (fixed text, sealed):
"Prior measurement of this exact function: NBA moneyline, n=372 retrospective holdout, gap +0.0063
Brier to the proportional-devig sportsbook close, 95% CI [-0.0042, +0.0168], MATCHES_CLOSE and
underpowered (MDE 0.0150). That comparator was a sportsbook close; this log's comparator is the
devigged Kalshi mid. The model sees no injuries, rest or lineups and carries 2025-26 ratings into
2026-27 without season regression, so early-season rows are expected to read worse than the
retrospective holdout."

## 2. Daily pipeline (S782a)

- **Day D** = the ESPN listing date (US Eastern calendar day) of the NBA scoreboard.
- **Scope**: every ESPN-listed NBA game of D with season.type == 2 (regular season) or 3 (playoffs)
  per `ingame/nba_season_type.season_of`; preseason (1), All-Star / exhibitions and any game with a
  team outside the 30 canon abbreviations are excluded and counted. NBA Cup group and knockout games
  are regular season and are in scope. Every in-scope game gets a row: no selection, losers included.
- **Cut**: `cut_ts = min(D 15:00:00Z, T1 - 120 min)`, T1 = earliest scheduled_start among D's in-scope
  games in the schedule fetch made at the run. 15:00Z is at least 60 min before any NBA tip seen in
  practice (noon ET = 16:00Z under EDT) and sits after the ~13:55Z start of the daily bulk capture.
- **Inputs allowed (nothing after the cut)**: (i) the frozen base corpus
  `data/domains/basketball_nba/espn_boxscores.parquet` (sha256 pinned at seal; never written by
  this row); (ii) the frozen offseason backfill `data/cache/pregame_log/nba_box_backfill_2026-05-25_2026-06-30.parquet`
  (built once before the seal by `ingest_range(..., out_path=...)`, sha256 pinned); (iii) the season
  append file `data/cache/pregame_log/nba_box_2026_27.parquet`, fed by `ingest_range` for dates
  2026-10-20..D-1 only, rows whose ESPN status is final; (iv) the ESPN schedule response for D (its
  `response_sha256` is recorded). No odds, no Kalshi price, no injury feed is a model input.
- **Forecast**: build a scratch root with one `espn_boxscores.parquet` = concat(i, ii, iii rows with
  date < D), append D's in-scope games as placeholder rows (home_score 110, away_score 100, date D),
  call `asof_box_accuracy.load_box(root)` then `ml_accuracy._walk_forward_elo(box)` and read p for the
  appended rows. Exact because an NBA team plays at most once per listing day, so no appended row
  affects another's pre-game rating (assert it: a duplicated team on D refuses the day,
  `duplicate_team_on_day`). Placeholder scores keep the rows inside load_box's 150..350 total filter
  (assert the appended row count survives).
- **Ticker**: link each game to its KXNBAGAME home ticker with `ingame/game_market_link`
  (`index_kalshi_events`, `link_game`, `team_code_from_ticker`; seal-pinned file, imported read-only)
  over the newest `snapshot_bulk` rows at or before cut_ts, read from a bounded tail (<= 16 MiB) of
  D's and D+1's UTC nba shards. Unlinked -> `ticker: null`, `link_reason` set; the row is still
  published and the scorer re-links.
- **File** `docs/evidence/forward/forecasts/nba/<D>.jsonl`, one JSON object per line, keys sorted,
  ASCII, written once (atomic rename); a rerun that would change bytes refuses `already_written`.
  A correction is a NEW file `<D>.r<N>.jsonl`; the original rows stay the scored rows.

| field | meaning |
|---|---|
| schema | "forecast_log_v1" |
| sport | "nba" |
| family | "nba_moneyline_home_win" |
| game_key | ESPN event id |
| ticker | KXNBAGAME home-side ticker or null |
| link_reason | null or the link refusal reason |
| home_abbr, away_abbr | canon abbreviations |
| scheduled_start | ESPN start, UTC ISO-8601 Z |
| cut_ts | the day's cut, UTC |
| written_utc | wall clock at write (author-settable; NOT the witness) |
| p_home | model P(home win), 6 decimals |
| p_source_identity | {"function": "scripts.platformkit.proof_nba.ml_accuracy._walk_forward_elo", "files": {path: sha256} for ml_accuracy.py, asof_box_accuracy.py and the S782a CLI files} |
| inputs_as_of | max box date used (must be < D) |
| inputs_sha256 | sha256 of the concatenated input frame bytes (deterministic parquet write) plus the schedule response_sha256 |
| prereg_sha256 | the sealed prereg payload sha256 |

- **Resources**: one child process, peak RSS <= 300 MB, wall <= 120 s, at most ~15 ESPN requests
  (1 scoreboard + finals of D-1). It is a light step under DESK_STATE 1b (no pytest, no lane, bounded
  archive read); verifier measures the bound.

## 3. Witness (S782c)

- **Commit**: stage exactly `docs/evidence/forward/forecasts/nba/<D>.jsonl` by explicit pathspec
  (never add-all), commit "S782 forecast log <D> (PAPER ONLY)", push. Refusal semantics reuse
  `scripts/platformkit/ops/evidence_push.py` (S657: refuse a dirty index it did not create, a path
  outside the set, a rebase conflict; never force).
- **Interim witness (default, automatic)**: push to `private` `master:trunk`. GitHub records the
  server-side push time; checkable by the owner and anyone granted read access. It is NOT a public
  third-party witness and the weekly file says so while it is the only witness.
- **Public witness (OWNER-GATED)**: after the private push, `python scripts/hooks/publish_public.py`
  (exports the allowlist into `../court-vision-public`, branch public-master, refuses if origin/master
  is not merged) then `git -C ../court-vision-public push origin public-master:master` (the
  court-vision repo). Owner-gated because it is a new standing daily push to the public repo from an
  unattended step; the owner approves the scheduled task once and runs the first push by hand.
- **Witness record** next day before cut, `docs/evidence/forward/forecasts/witness/<D>.json`: for each
  forecast file: commit sha, git blob id, file sha256, remote, and `pushed_at` = the earliest GitHub
  server-side push whose pushed head has that commit as an ancestor, read-only from
  `gh api repos/<owner>/<repo>/activity` (activity_type push, timestamp, after) with
  `gh api repos/<owner>/<repo>/events` (PushEvent created_at) as fallback; ancestry by
  `git merge-base --is-ancestor`. Commit dates are never used (author-settable).
- **Row status**: ON_TIME iff pushed_at < scheduled_start of that row; else LATE (excluded from every
  score, counted and listed). No witness found by D+2 -> UNWITNESSED (excluded, counted). A file whose
  current blob differs from the witnessed blob -> EDITED (whole file excluded, counted, P1 issue).

## 4. Weekly scorer (S782b)

- **When**: Monday 13:00Z for the ISO week just ended (all games final by then); first file
  2026-W43 (10-20..10-25) on Monday 10-26. Outputs:
  `docs/evidence/forward/forecasts/weekly/<YYYY-Www>.json` + `.md` (public, aggregates and our own
  per-game p only) and the private join `data/cache/pregame_log/scored/<YYYY-Www>.jsonl` (per-game
  mids and outcomes; never under docs/ until LICENCE_LEDGER rows 11 and 1 change).
- **Outcome**: y = 1 if home final > away final from the season append file (status final); a tie,
  missing or non-final game -> OUTCOME_INVALID (excluded, counted). Where the in-game scoreboard
  settled the same ticker (`docs/evidence/forward/scoreboard/<D>.json`), a disagreement ->
  OUTCOME_CONFLICT (excluded, counted, P1).
- **Comparator (primary)**: the devigged Kalshi mid at the SAME cut_ts: for each side ticker of the
  event, the newest `snapshot_bulk` or `snapshot` row with capture_ts <= cut_ts and age <= 1,800 s,
  two-sided (0 < yes_bid < yes_ask < 1), spread <= 0.10; mid = (yes_bid + yes_ask) / 2;
  q_home = mid_home / (mid_home + mid_away) (proportional devig). Missing either side, stale, one-sided
  or wide -> NO_MID with the reason (excluded from the paired cell, counted). **Sensitivity**: Shin
  devig via `eval_gate/shin.py::shin_devig` on [mid_home, mid_away].
- **Comparator (secondary, the "close")**: the same rule at the last capture before scheduled_start
  (age <= 1,800 s). Reported in its own cell, never mixed with the primary.
- **Scores**: Brier and log loss (clip 1e-6, as the harness) for model, mid and close; paired
  d_i = loss_model - loss_mid per game; DM via `eval_gate/dm_test.py::diebold_mariano(d, game_key)`
  (game-clustered; one row per game) and the date-clustered sensitivity (cluster = D); 95% CI
  Student-t G-1; MDE = 1.429 x half-width (POWER_PAGE definition); BSS = 1 - B_model / B_mid;
  reliability table (10 bins) for the model, descriptive.
- **Cells**: per sport x family x comparator, for (a) the week and (b) cumulative since effective_from.
  Weekly cells are descriptive only. A verdict is printed only on the cumulative cell once paired
  n >= 150 games (about three weeks); below that the cell reads INSUFFICIENT with n and MDE.
- **Vocabulary** (packet rule, applied mechanically): MATCHES_MID if the CI includes 0, TRAILS_MID if
  above 0, BEATS_MID if below; the close cell uses MATCHES_CLOSE / TRAILS_CLOSE / BEATS_CLOSE. If the
  date-clustered CI gives a different verdict, the line adds "verdict sensitive to clustering".
- **BEATS guard**: a BEATS reading is written to the file but the public one-liner waits for a
  cv-honesty-gate pass (leak audit of the inputs_as_of fields, LATE/NO_MID exclusion audit); it is
  never described as an edge, profit or anything in money.
- **Honest one-liner (template, sealed)**:
  "NBA pregame log, cumulative to <date> (n=<n> paired games, <late> late, <nomid> no-mid excluded):
  model Brier <bm> vs devigged Kalshi mid at the cut <bq>; gap <g:+.4f> (95% CI [<lo>, <hi>],
  game-clustered DM p <p>, MDE <mde>): <VERDICT>. Calibration measurement only."
  When TRAILS: append "The market mid is sharper than this ratings-only model by <g> Brier; expected,
  the model sees no injury, rest or lineup information." When INSUFFICIENT: "n below the 150-game
  floor; projected date the MDE reaches 0.01: <date> (from the observed SD of d)."
- **Projection**: n needed for MDE 0.01 = n_now x (MDE_now / 0.01)^2, date by the observed games per
  day; at the retrospective SD this is about 840 games, i.e. around mid-February 2027 (estimate).
- **Byte-identity**: re-running the scorer over the same inputs writes identical bytes.

## 5. Seal (prereg)

- **Hashed**: the prereg payload; implementation sha256 of ml_accuracy.py (edb843b5...7d83 today),
  asof_box_accuracy.py (53811186...b2b6), ingest_espn_box.py (df50f178...6a0f),
  ingame/game_market_link.py (202bdd9b...2a45), execution/forward_schedule_sources.py
  (bde1cd4a...7901), ingame/nba_season_type.py, eval_gate/dm_test.py (6eb5100c...37e0),
  eval_gate/shin.py (c8430415...a47f) and every S782a/S782b/S782c file; data pins: base box
  9f52c38a...2949 and the backfill parquet (sha at seal). Values above are candidates; the seal cut
  re-reads them.
- **When**: on its own day, never the night of another identity change. Not 10-06 (consolidated seal
  A), not 10-07 (commit B), not the S644 PREREG_R2 day, not the S721 day. Default **2026-10-15**
  (Thu) after a preseason rehearsal on 10-12..10-14 (scratch output under data/cache/pregame_log/rehearsal/,
  never published as the record); fallback the next free day 10-16..10-18; hard limit 10-19 12:00Z.
  The seal file is `docs/evidence/forward/forecasts/PREREG_FORECAST_LOG_<seal day>.json`, committed
  alone, pinned by a test helper like s469_seal_helper; effective_from 2026-10-20T00:00:00Z.
  No seal by the hard limit -> the log starts the day after the seal lands; rows before it are never
  counted.
- **Amendments**: a new dated PREREG file (the old one kept, `supersedes` names it), committed alone,
  effective from a FUTURE listing day only; never retroactive; a changed forecaster identity starts a
  new evidence group (cumulative cells restart, the old group stays published). A new sport joins only
  by amendment sealed before its first row. Critical defect in the scorer: fix by amendment and
  re-score; forecast rows are never rewritten.

## 6. Build rows

| Row | What | Builder, hours | Before-condition | Files |
|---|---|---|---|---|
| S782a | forecaster CLI + daily file + box append | codex, 5 h (Claude review) | backfill parquet built; this spec | scripts/platformkit/pregame_log/forecast_nba.py, pregame_log/box_append.py, tests pregame_log/test_forecast_nba.py, test_box_append.py |
| S782b | weekly scorer + weekly files | codex, 5 h | S782a rows exist (rehearsal rows ok) | pregame_log/weekly_score.py, pregame_log/mid_at_cut.py, tests test_weekly_score.py, test_mid_at_cut.py |
| S782c | publication + witness | Claude, 3 h; OWNER: public push approval | S782a | pregame_log/forecast_push.py, pregame_log/witness.py, tests test_forecast_push.py, test_witness.py; allowlist line `+ scripts/platformkit/pregame_log/` (owner-visible, public tree) |
| S782d | dashboard card quoting the weekly one-liner | Claude, 1 h | first weekly file | a card reading weekly/<week>.json verbatim (webapp lane owns the page file); test asserts the text equals the file's one_liner |

Verifier contract (two tiers each; a third party must be able to run them):
- **Tier 1 (contract)**: S782a: inputs_as_of < D on every row; a box row dated D or later in the append
  file is excluded and counted; p for the appended rows equals `_walk_forward_elo` on a hand-built
  frame (fixture of three days); duplicate team refuses; preseason excluded; file written once.
  S782b: byte-identical rerun; a week under the floor prints INSUFFICIENT; LATE / NO_MID / OUTCOME_*
  counted and excluded; DM numbers equal `dm_test.diebold_mariano` on the fixture. S782c: every
  ON_TIME row has pushed_at < scheduled_start from the API record, not the commit date.
- **Tier 2 (adversarial, mutants)**: (1) a back-dated commit (author date before start, push after)
  reads LATE; (2) a forecast file edited after its witness reads EDITED; (3) a mid at cut_ts + 1 s is
  not used (point-in-time); (4) swapping home/away tickers flips q and is caught by the link check;
  (5) the p_source_identity hashes differ from the files actually imported -> refuse; (6) dropping a
  losing-forecast row from a day is caught (row count = in-scope game count from the schedule
  receipt); (7) a weekly scorer that silently drops NO_MID games from the count is killed by the
  count test. Each mutant must fail at least one test.
- **Per-file tests only**: `python -m pytest scripts/platformkit/pregame_log/test_<one>.py -q`, one
  process at a time, outside focus-hour quiet windows.

## 7. What a hiring manager checks in five minutes (once it runs)

```
git clone https://github.com/neeljshah/court-vision && cd court-vision
ls docs/evidence/forward/forecasts/nba/ | head                     # one file per slate day
python -m scripts.platformkit.pregame_log.witness --check --day 2026-10-20   # API push time < every start
gh api repos/neeljshah/court-vision/activity --jq '.[] | [.timestamp,.after] | @tsv' | head
git log --format='%H %ad' -- docs/evidence/forward/forecasts/nba/2026-10-20.jsonl   # never edited
cat docs/evidence/forward/forecasts/weekly/2026-W43.md               # n, Brier, CI, verdict, LATE count
python -m json.tool docs/evidence/forward/forecasts/PREREG_FORECAST_LOG_2026-10-15.json | head -40
```
Before the owner opens the public push, the same checks run against the private trunk by anyone with
read access; the weekly file states which witness applied.

## 8. Not claimed

No edge, profit, ROI or money figure; no claim that the model is sharper than the market; no
retrospective rows inside the log; no per-game Kalshi price and no per-game outcome in any public file
until the licence rows change; no MLB, NFL or soccer rows until a sealed amendment admits them.
