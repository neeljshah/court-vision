# 02 -- Betting Product Frontend + Serving + Snapshot Architecture

Area owner doc for the deep project-understanding report. Scope: how the multi-sport
decision-support board is computed, cached, served, and rendered. Files under
`scripts/platformkit/frontend/` + `scripts/platformkit/predict_matchup.py`.

Binding framing (carried from repo rules): markets are efficient; the honest win is
CALIBRATION (matching the devigged close within noise), NOT a money edge. The product
NEVER places a bet and NEVER connects to a sportsbook. Everything below is paper /
decision-support only. Any "edge"/"EV" shown is a raw prob-vs-price gap or a
line-shopping execution number, explicitly not a beat-the-close claim.

---

## 1. INVENTORY -- what EXISTS and is USED

### Serving + snapshot core (the live path)

- `scripts/platformkit/frontend/serve.py` -- the always-on FastAPI decision-support
  service. Port 8098 (`FRONTEND_PORT`). Endpoints `/health`, `/api/sports`,
  `/api/slate`, `/api/live`, `/api/props`, `/api/game`, `/api/clv`, `/api/clv/record`
  (POST), `/api/intent` (POST), `/` (serves `static/index.html`). ~300 LOC.
- `scripts/platformkit/frontend/snapshot_writer.py` -- the "compute once" keystone:
  builds a sport's full board (slate + live + props) ONCE and writes it atomically to
  `data/frontend/snapshots/<sport>.json`. `build_snapshot`, `write_all`,
  `read_snapshot`. ~275 LOC.
- `scripts/platformkit/frontend/refresh_daemon.py` -- tiny background loop that calls
  `snapshot_writer.write_all` on a cadence (default 60s). `run_once`, `run_forever`.
  "Degrade, never die" -- a bad tick keeps the last-good snapshots.
- `scripts/platformkit/frontend/slate.py` -- reshapes the REAL predictor output into
  flat table rows (`build_row`, `build_slate`); derives an honest verdict tag. Defines
  `SPORTS = ("nba","mlb","soccer","soccer_intl","tennis")` and `HONEST_NOTE`.
- `scripts/platformkit/frontend/bet_board.py` -- per-game board: EVERY market for ONE
  game (moneyline / spread / totals / team totals / periods / derived props) with
  model prob, fair odds, best book price, EV-where-priced, ranked best bets.
  `game_bet_board`.
- `scripts/platformkit/frontend/bet_board_flat.py` -- flattens the predictor's nested
  per-sport `markets` surface into a uniform `{group, selection, model_prob, line}`
  row list (`flatten`). Consumed by `bet_board._enrich`.
- `scripts/platformkit/frontend/live_board.py` -- TODAY's real games + LIVE state from
  ESPN's keyless public scoreboard, with in-game predictions on in-progress games.
  `todays_live_games`, `resolve_team`. Injectable `http_get` (offline tests).
- `scripts/platformkit/predict_matchup.py` -- the ONE buyer-facing CLI + the shared
  `build_result(sport, predictor, ns)` seam that slate / bet_board / live_board all
  call. Emits coherent pregame (+ optional in-game) blocks with full market surfaces.

### React/Vite UI (built but NOT mounted by serve.py)

- `scripts/platformkit/frontend/web/` -- React 18 + Vite 5 + TS + Tailwind + shadcn/ui.
  - `src/App.tsx` -- shell: header, honest banner, sport controls, 4 tabs (Board /
    Arbitrage / +EV / Bet tracker), game-detail modal.
  - `src/lib/api.ts` -- typed client; mirrors slate/game contracts; `fetchSlate`,
    `getGame`, `postIntent`, `parseMatchup`, `SPORTS` (World Cup first).
  - `src/lib/useSlate.ts` -- slate fetch hook with 30s auto-poll.
  - `src/components/board/` -- `BoardTable`, `BoardControls`, `HonestBanner`,
    `VerdictBadge`, `RowActions`, `useSort`.
  - `src/components/game/` -- `GameDetail` (modal), `BestBetCard`, `BetRowsTable`,
    `betFormat.ts`.
  - `src/components/screens/` -- `BoardScreen`, `PlaceholderScreen` (arb/EV/tracker).
  - `src/components/ui/` -- shadcn primitives (badge/button/card/collapsible/dialog/
    input/select/table/tabs).
  - `dist/` -- a built bundle exists: `index-BVP9sgtd.js` (288 KB), `index-...css`
    (19 KB). Vite dev proxies `/api` + `/health` -> `http://127.0.0.1:8098`.
- `scripts/platformkit/frontend/static/index.html` -- the LEGACY vanilla-JS UI
  (single 147-line file, dark theme). THIS is what `serve.py /` actually returns.

### Snapshot / odds-history accumulators (separate from the board snapshot)

- `scripts/platformkit/frontend/odds_snapshot.py` -- timestamped price-snapshot ledger
  (`snapshot_sport`, `load_snapshots`, `line_movement`) -> `data/domains/<sport>/
  odds_snapshots/snapshots.jsonl`. Raw opener->closer history for CLV grading.
- `scripts/platformkit/frontend/snapshot_scheduler.py` -- orchestrates `odds_snapshot`
  over all sports; emits opener-vs-closer candidate pairs for `clv.py`. CLI
  `capture` / `candidates <sport>`.

### Supporting / adjacent (in dir, used by other lanes, not the board hot path)

- `feed.py` / `feed_espn.py` / `feed_bovada.py` / `feed_multi.py` -- `OddsFeed`
  abstraction + concrete keyless feeds (used by odds_snapshot, arb).
- `arbitrage.py` / `arb_panel.py` -- cross-book arb math + panel.
- `clv.py` / `clv_view.py` -- CLV grading + view (the honest yardstick).
- `book_norm.py` -- book-name normalization.
- Tests present: `test_serve.py`, `test_serve_snapshot.py`, `test_snapshot_writer.py`,
  `test_bet_board.py`, `test_live_board.py`, `test_refresh_daemon.py`.

### Likely STRANDED / superseded (built-but-unread by the live board path)

- `app.py` (port 8099), `board.py`, `board_html.py`, `build_board.py`,
  `recal_board.py`, `intel_panel.py` -- an EARLIER server + HTML-board generation
  generation. `serve.py` (8098) is the current entry point; these are not on its path.
  `serve.py` docstring explicitly calls itself "distinct from api/main.py AND
  frontend/app.py". Treat as legacy unless a caller is found.

---

## 2. HOW IT WORKS -- data flow + key components

### The shared prediction seam

Every board reads from ONE function so prediction math is never reimplemented:

- `predict_matchup.build_result(sport, pred, a) -> dict` (predict_matchup.py:228).
  Produces `{sport, home, away, edge_claimed: False, framing, pregame, ingame?}`.
  - `_pregame_block` (pm:163) calls `pred.predict(...)` and attaches the FULL
    per-sport market surface: NBA via `domains.basketball_nba.markets.full_surface`,
    tennis via `domains.tennis.markets.markets_for_matchup`, soccer/soccer_intl via
    `raw["markets"]` (one scoreline matrix), MLB rides `raw["markets"]`.
  - `_ingame_block` (pm:207) calls `pred.predict_live(...)` when `live_kwargs` returns
    a complete sport-appropriate state (pm:70); else a pregame-only note.
  - `_jsonsafe` (pm:118) coerces numpy scalars/arrays so strict JSON never chokes.
- The predictor itself comes from `predictor_jd._build_predictor(sport)` (cached,
  guarded). Missing corpus -> `pred is None` -> `_UNAVAILABLE` note, exit 0.

### Slate (the flat table)

`slate.build_slate(sport, *, matchups, predictor_factory, market_lookup, odds_lookup)`
(slate.py:217). Builds the predictor once, iterates default matchups
(`_DEFAULT_MATCHUPS`, slate.py:41 -- hardcoded demo/real slates per sport), and for
each calls `build_row` (slate.py:171):

- `model` = compact summary string (`_model_summary`, slate.py:90).
- `edge` = `p_home_win - market.p_home_implied` (`_edge`, slate.py:116) -- decision
  support only, None when no market.
- `verdict` = parsed from the predictor's own `honest_note`
  (`_verdict`, slate.py:72: BEHIND / MATCH / AHEAD / CALIBRATED / UNKNOWN). It does
  NOT compute calibration; it reads the predictor's English self-description.
- Multi-book block (`_book_fields`, slate.py:143) via `odds_shop.summarise_twoway`:
  `best_home/away_book/price`, `arb_pct`, `model_ev_best`. arb_pct is SUPPRESSED for
  three-way markets (`_THREE_WAY = {soccer, soccer_intl}`, slate.py:140) to avoid
  phantom 2-way arbs.

Every row is guarded: a bad matchup -> `status:"error"`/`"unavailable"` row, never a
fabricated number, never a 500.

### Per-game board

`bet_board.game_bet_board(sport, home, away, *, predictor, odds_lookup, live, surface)`
(bet_board.py:188). Flow: build_result -> `flat.flatten` of `pregame.markets` ->
`_enrich` attaches `fair_odds = 1/model_prob` to EVERY row and a real book price +
`ev_pct = model_prob*price - 1` ONLY to Moneyline rows (the reliably shoppable market)
-> `_rank_best` (bet_board.py:131): rank priced rows by EV above `_EV_FLOOR = -0.02`,
else fall back to model-confidence `|p-0.5|` favored picks labelled "model view, NOT a
priced edge", cap 8. `_live_rows` (bet_board.py:247) adds LIVE-labelled moneyline rows
from the in-game block (model view only -- no live book shopping).

### Live board

`live_board.todays_live_games(sport, *, http_get, predictor_factory)`
(live_board.py:229). GET ESPN keyless scoreboard (`_ESPN_ROUTES`, live_board.py:38 --
mlb / nba / soccer_intl=fifa.world / soccer=eng.1). Parse each event
(`_parse_event`, :129) -> normalized row (state pre/in/post, score, clock/period).
For `state == "in"` rows: resolve ESPN team names to predictor ids
(`resolve_team` + `_NBA_ABBR`/`_MLB_ABBR`/`_INTL_NAME` maps), build a live Namespace
(`_live_ns`, :168 -- `_nba_elapsed`, `_soccer_minute`, `_mlb_half_inning` translate the
clock), and attach `build_result`. Unresolvable team -> SKIPPED with a note, never
faked. Feed down (`events is None`) -> `status:"unavailable"`. Always 200.

### Snapshot architecture (compute-once)

`snapshot_writer.build_snapshot(sport, ...)` (snapshot_writer.py:145) calls the three
real seams (slate / live / props) each behind its own guard:

- `_build_slate` (sw:91) tries WITH odds, retries WITHOUT odds, then an unavailable
  stub -- a slow odds feed never costs the model-only slate.
- `_build_live` (sw:114) and `_build_props` (sw:129) each degrade independently;
  props is OPTIONAL (None when `prop_edge` absent).
- Envelope: `{sport, generated_at, status, slate, live, props, freshness:{as_of,
  source:"snapshot"}, honest_note}`. `status="ok"` only if the slate is ok.
- `_atomic_write` (sw:66): write `.tmp` then `os.replace` -- a polling reader sees the
  OLD or the COMPLETE new file, never a half-write.
- `write_all(sports)` (sw:212) loops all sports; one sport failing never stops others.

Verified on disk: `data/frontend/snapshots/soccer_intl.json` (2.7 MB) with keys
`[sport, generated_at, status, slate, live, props, freshness, honest_note]`,
`status=ok`, `slate.rows=4`, `live.games=4`, props edges present.

### Read path / fast path in serve.py

`_read_snapshot_part(sport, key)` (serve.py:104): reads the envelope, requires
`status=="ok"` and a non-empty dict at `key`, stamps `freshness` +
`served_from:"snapshot"`. `/api/slate`, `/api/live`, `/api/props` ALL prefer the
snapshot and fall back to a synchronous live compute on a miss (stamped
`served_from:"live_compute"`) so a cold cache never dark-screens. `/api/game` is the
exception -- it always computes live (no per-game snapshot). `/api/intent`
(`log_intent`, serve.py:126) appends a JSONL record stamped `executed:False`,
`channel:"manual_human"` -- a hard invariant that no bet was placed.

Speed: the snapshot read is a single `json.load` + dict slice (sub-millisecond);
the expensive predictor build happens once per refresh tick, not per request. The
refresh_daemon (or prop_loop) is what keeps the snapshot warm.

---

## 3. HOW IT IS USED -- callers / consumers

- `python -m scripts.platformkit.frontend.serve` -> FastAPI on 8098, serves
  `static/index.html` (the vanilla-JS board), which polls `/api/slate?sport=` every
  30s and POSTs `/api/intent` on the "I placed this" checkbox.
- `refresh_daemon.run_forever` (CLI `python -m ...frontend.refresh_daemon`) keeps
  snapshots warm on a cadence. On disk evidence: `soccer_intl.json` regenerated at
  13:36 UTC today -> the daemon/loop is actively running for that sport.
- `prop_loop.run_tick` (scripts/platformkit/prop_loop.py:114-119) calls
  `snapshot_writer.write_all(sport_list)` as step 2 of its unattended paper-accrual
  cycle -- the snapshot is shared infrastructure, not board-only.
- `pm_trading/run_paper_today.py` imports `bet_board.game_bet_board` and
  `live_board.todays_live_games` directly to build per-game boards for paper grading
  (run_paper_today.py:27-28) -- the SAME seams the UI uses.
- React app (Vite dev `npm run dev` on 5174, proxy to 8098): consumes `/api/slate`
  (BoardScreen via `useSlate`) and `/api/game` (GameDetail modal). It does NOT consume
  `/api/live` or `/api/props`. The arb/EV/tracker tabs are `PlaceholderScreen`s that
  re-filter the slate rows; the tracker tab is an explicit TODO.
- `predict_matchup` is also a standalone CLI and the `predict-matchup` skill.

---

## 4. STRENGTHS

- Clean single-seam discipline: slate, bet_board, live_board, snapshot_writer all
  funnel through `predict_matchup.build_result` -> `predictor_jd._build_predictor`.
  No prediction math is duplicated; a model change propagates everywhere at once.
- Honesty is structural, not cosmetic: `edge_claimed:False` in every result; EV only
  attached where a real book price exists and labelled line-shopping; arb suppressed
  for 3-way markets; verdict tags are READ from the predictor's note, never invented;
  `/api/intent` hard-stamps `executed:False`. The no-edge rule is enforced in code.
- Fail-soft everywhere: every endpoint and every snapshot stage is wrapped so it
  degrades to `status:"unavailable"` / `served_from:"live_compute"` rather than 500 or
  dark-screen. The atomic snapshot write + "keep last-good" daemon is genuinely robust.
- The compute-once snapshot is the right architecture: one expensive predictor build
  per cycle, many sub-ms reads; readers and the paper loop share one cache.
- Fully offline-testable: `http_get`, `predictor_factory`, every snapshot seam, and
  the daemon's `writer`/`sleep` are injectable. Six per-file test modules exist.
- The React/shadcn UI is real (builds to a 288 KB bundle), typed against the API
  contract, and has a working clickable game-detail modal with collapsible market
  groups + best-bet cards.

---

## 5. LIMITATIONS / RISKS / GAPS / KNOWN BUGS

- THE BIG ONE -- the React UI is NOT served. `serve.py /` returns the legacy
  `static/index.html` (vanilla JS, slate table only). The polished React/shadcn app in
  `web/dist/` is never StaticFiles-mounted; the only way to see it is `npm run dev` on
  5174 with the API proxy. So "the UI a user sees at :8098" is the basic table, not the
  premium board. There is no `app.mount("/", StaticFiles(directory="web/dist"))`.
- React app ignores half the API. `/api/live` (today's real + in-game) and
  `/api/props` (the World Cup prop edge board -- the current frontier per NOW.md) are
  built, snapshotted, and served, but NO React screen consumes them. The live games and
  prop ladders are backend-only today.
- Arb / +EV / tracker tabs are thin. Arb and +EV just re-filter the same slate rows
  (no dedicated feed); the Bet tracker / CLV tab is a literal `PlaceholderScreen` with
  "Full ledger view is a TODO" -- `/api/clv` exists but nothing reads it in React.
- Freshness/staleness is computed but not surfaced. The envelope carries
  `freshness:{as_of, source}` and `served_from`, but neither the static UI nor the
  React UI displays snapshot age or a "stale" warning. A user cannot tell if the board
  is 5 seconds or 50 minutes old. The static UI shows only the client's own fetch time.
- Default matchups are hardcoded. `slate._DEFAULT_MATCHUPS` (slate.py:41) is a static
  per-sport list (e.g. specific 2026 WC/MLB games). The slate does NOT pull today's
  real schedule from `live_board` -- `/api/slate` and `/api/live` can show DIFFERENT
  games. They will drift as real schedules move; this is a maintenance landmine.
- `/api/game` has no snapshot -> always a live predictor build per click. Fine for one
  modal, but it is the slow path and is uncached; rapid clicks recompute every time.
- ESPN team-name resolution is brittle. `_NBA_ABBR`/`_MLB_ABBR`/`_INTL_NAME` are
  hand-maintained maps; any new/renamed code (e.g. a World Cup nation ESPN spells
  differently) silently SKIPS the game. Honest (no fabrication) but lossy.
- EV is moneyline-only in bet_board. Totals/spreads from the keyless feed are not
  priced even when quoted (`_enrich` attaches book price only to `group=="Moneyline"`),
  so the "every market" board shows fair-odds-only for most rows.
- Legacy clutter: `app.py`, `board.py`, `board_html.py`, `build_board.py`,
  `recal_board.py` appear superseded by serve.py + the React app but still live in the
  dir, raising "which is the real entry point?" confusion.
- Honesty rails to respect (not bugs): the verdict/edge are calibration-context only;
  any positive `model_ev_best`/`arb_pct` is a line-shopping execution number on a SOFT
  book, NOT evidence the model beats the sharp close. Prop "edges" depend on thin
  single-match club priors (per NOW.md the reliable-edge count came from a 36-player
  sample) -- treat as in-sample/thin until forward CLV settlement accrues.

---

## 6. PLAN TO GET BETTER (prioritized)

Quick wins (hours):

1. Mount the React build. Add `app.mount("/app", StaticFiles(directory=web/dist,
   html=True))` (or replace `/`) in serve.py so the premium UI is the default at 8098.
   Biggest single UX jump -- the good UI already exists, it just is not wired.
2. Surface freshness. The envelope already carries `freshness.as_of` + `served_from`;
   pass them through the slate/game payloads and render a "snapshot N s ago / LIVE
   COMPUTE / STALE >Xm" pill in `HonestBanner`. Pure plumbing, high trust payoff.
3. De-duplicate the entry point. Move `app.py`/`board*.py`/`build_board.py` to a
   `legacy/` subfolder (or delete) so serve.py is unambiguously the server.
4. Cache `/api/game` per (sport,home,away) for a short TTL, or fold a per-game board
   into the snapshot for the day's real games.

Medium (days):

5. Wire `/api/live` into a React "Live" tab: today's real games, scores, in-game
   re-priced moneyline, with a LIVE badge and short poll. The data is already served.
6. Wire `/api/props` into a World Cup prop-board screen (click player -> priced ladder
   + reliable/thin tier labels). This is the stated current frontier in NOW.md.
7. Make the slate schedule real: have `build_slate` source today's matchups from
   `live_board.todays_live_games` instead of `_DEFAULT_MATCHUPS`, so slate and live
   agree and never go stale.
8. Build the CLV tracker tab against `/api/clv` (and a ledger-read endpoint) -- the
   honest yardstick deserves a first-class view, not a placeholder.

Bigger bets:

9. Replace polling with SSE/WebSocket push from the refresh cadence so the board
   updates the instant a snapshot is rewritten (no 30s lag, no redundant polls).
10. Price more than moneyline: extend `_enrich` + odds_shop to attach feed prices to
    totals/spreads where quoted, so the "every market" board actually shows EV beyond
    the moneyline row.
11. Harden ESPN resolution: replace the hand maps with a fuzzy/aliased resolver backed
    by the corpus team table, and log skipped games to a visible "unmatched" panel.

---

## 7. HOW GOOD CAN IT GET (honest ceiling)

The serving + snapshot architecture can become genuinely excellent and fast: the hard
parts (compute-once, atomic writes, degrade-never-die, a single shared prediction seam,
a typed React contract) are already built and sound. With items 1-8 done, this is a
clickable, sub-second, multi-sport board with live games, prop ladders, CLV tracking,
and visible freshness -- a polished decision-support product. That is a realistic,
reachable ceiling and a strong portfolio artifact.

What it CANNOT become, and the doc must say so plainly: a profitable betting edge. The
ceiling on the NUMBERS is set entirely upstream by the predictor, and the repo's own
honest verdict is that pregame MATCHES the devigged close (calibration, not a money
edge) and markets are efficient. No amount of frontend polish changes that. The "edge",
"EV", and "arb" surfaces are, at best, a line-shopping/execution convenience on soft
books plus calibration context -- never a beat-the-close claim. The defensible product
story is: a fast, honest, well-engineered, fully-calibrated multi-sport prediction +
decision-support board, paper-only, with CLV as the truth metric -- excellent as
engineering and as honest calibration, explicitly not as a profit machine.
