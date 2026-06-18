# 03 - UI Design: Multi-Sport Betting Decision-Support Board

Date: 2026-06-17. Author: research agent. ASCII-only.

Scope: design the BEST possible UI for our multi-sport betting decision-support
board and recommend HOW to build it. Decision-support only -- no auto-execution,
no claimed money edge. Line-shopping and arbitrage are labelled EXECUTION edges
(a better price than your own book), never a predictive/beat-the-close edge.

References:
- Current UI: `scripts/platformkit/frontend/static/index.html`
- Slate shape: `scripts/platformkit/frontend/slate.py`
- Odds/value engine: `scripts/platformkit/odds_shop.py`

---

## 0. What we have today (baseline)

A single vanilla HTML/JS page (`index.html`, ~146 LOC) that:
- Has one sport dropdown, a Refresh button, a 30s auto-poll checkbox.
- Renders ONE flat table: Matchup | Model | Market line | Edge* | Verdict | Note | Action.
- Per-row action = an external Google-search link ("Place on my book") + a
  paper-only "I placed this" checkbox that POSTs to `/api/intent`.
- Dark theme already (bg `#0f1115`, amber honest banner, green/red verdict + edge).

Data available per row (from `slate.build_row`):

| Field            | Meaning                                                        |
|------------------|----------------------------------------------------------------|
| `sport`          | nba / mlb / soccer / soccer_intl / tennis                      |
| `matchup`        | "HOME vs AWAY"                                                  |
| `status`         | ok / unavailable / error                                       |
| `model`          | compact string, e.g. "P(home)=58.3%, total~221.4"              |
| `p_home_win`     | float (raw model prob, used for EV)                            |
| `market`         | market line string (or None)                                   |
| `edge`           | model P(home) - market-implied P(home) (decision support only) |
| `verdict`        | MATCH / BEHIND / AHEAD / CALIBRATED / UNKNOWN / UNAVAILABLE     |
| `note`           | predictor's honest_note (plain English standing vs market)     |
| `best_home_book` / `best_home_price` | best decimal price + book, home side          |
| `best_away_book` / `best_away_price` | best decimal price + book, away side          |
| `arb_pct`        | guaranteed-return % if a two-way arb exists (else None)        |
| `model_ev_best`  | model EV at the BEST available home price (per $1)             |

`odds_shop.summarise_twoway` ALSO computes but slate does not yet surface:
`fair_prob_a/b` (devigged no-vig probs), `arb_stake_a/b` (stake split),
`model_ev_b` (away-side EV). These are free wins to expose.

Gap vs best-in-class: no per-book grid (only the single best price is shown), no
+EV feed view, no arb cards, no filters/sorting, no CLV/bet-tracker, no event
detail, no logos, no live indicators, no responsive/mobile layout.

---

## 1. Best-in-class UX patterns (researched)

Studied OddsJam, Outlier.bet, Unabated, Betstamp, Pikkit, OddsChecker, RotoGrinders.

### 1.1 The odds-comparison grid (line-shopping)
- Rows = market sides (or events); COLUMNS = sportsbooks. Each cell shows that
  book's price for that side. (OddsChecker, RotoGrinders, OddsJam Odds Screen.)
- Best price per side is HIGHLIGHTED (green cell / bold / left border). One glance =
  where to bet. RotoGrinders highlights the single best book's line.
- A "No-Vig / fair line" column shows the devigged true price; a "market width"
  (vig %) column shows how much juice each book charges. (OddsJam.) Lower width =
  sharper market.
- Sportsbook LOGOS as column headers (not text) for instant recognition. Clicking
  a cell deep-links to that book with the bet pre-loaded ("one-click bet").
- Sticky first column (the matchup/side label) so it stays visible while the book
  columns scroll horizontally -- essential when there are 10+ books.

### 1.2 +EV feed
- A continuously-updating LIST (not a grid) of individual bets ranked by EV%.
- Each row: event, market/side, the book + price offering the +EV, the fair/no-vig
  price it is being measured against, EV%, and (optionally) Kelly stake.
- Compares a soft book's price to a sharp reference (Pinnacle / consensus). OddsJam
  is explicit that +EV = a line discrepancy vs a sharp book, NOT a model claim.
  This maps cleanly to OUR honesty rule: we measure EV vs the BEST price you can
  actually bet, and we do NOT claim to beat the sharp close.
- Filters: league, market type (mainlines / alternates / props), min EV%, book
  in/out, min/max odds. Sort by EV%, by time-to-start.
- Freshness affordance: a timestamp + "updated Ns ago" + subtle row flash on change.

### 1.3 Arbitrage finder
- Surfaced as CARDS or a list: each = a guaranteed-profit two-way opportunity.
- Card shows: event, the two sides, the two DIFFERENT books + their prices, the
  guaranteed return %, and the STAKE SPLIT (how much on each side for equal payout).
- Universally framed as fragile/short-lived; refresh as fast as 1.6s-30s. Best
  tools show a countdown / "found Ns ago". We already warn arbs are rare and
  limit-restricted -- keep that warning ON the card.

### 1.4 Bet tracker / CLV
- A logged-bets table + an analytics header (CLV%, % of bets beating close, ROI,
  bankroll curve). GREEN = beat the close, RED = did not. CLV is presented as THE
  honest yardstick of skill (Pikkit, Outlier, Betstamp) -- exactly our position.
- Aggregations by day/week/month/all-time. Bankroll progression line chart.
- For us: this is the natural home for the existing `/api/intent` paper log. We add
  the closing price later and compute CLV. NO real-money, NO book sync -- paper only.

### 1.5 Per-event detail
- One event expands to: all markets (ML / spread / total / props), the full book
  grid per market, the model number + honest note, and a mini line-movement chart.
- Outlier's praised pattern: visual HIT-RATE bars + "evaluate a prop in under a
  minute". Clarity and speed over chart density.

### 1.6 Cross-cutting craft
- Dark, DENSE, monospaced-numeric tables (tabular-nums) -- bettors scan numbers fast.
- Color language: green = favourable/best/beat-close; red = unfavourable; amber =
  caution/honesty. We already use this.
- Live/in-game badge (pulsing dot) and a global "last updated" + auto-refresh toggle.
- Mobile: Outlier is mobile-first and is repeatedly called "actually usable" vs
  OddsJam -- responsive card fallback for narrow screens is a real differentiator.
- One-tap deep-link to the user's book (we keep this as a plain link -- no execution).

---

## 2. Our information architecture

Five screens, all fed by the SAME slate + odds_shop output. Top-level nav tabs:

```
[ Board ]  [ +EV Feed ]  [ Arbs ]  [ Tracker ]   sport: (NBA v)   updated 3s ago  (auto)
```

### (a) Odds Board / line-shopping grid  -- the home screen
Components:
- Sport selector, global refresh + auto-poll, last-updated stamp, honest banner.
- Filter bar: sport, market (ML to start), min-edge slider, book in/out multiselect,
  search box. Sortable column headers.
- Main grid. Two display modes:
  - Compact (default): one row per matchup = Matchup | Model | Verdict | Edge* |
    Best home (book+price) | Best away (book+price) | Arb | Model EV | Action.
  - Expanded book-grid: rows = sides, columns = each book's decimal price, best
    cell highlighted, plus a No-Vig column. (Needs raw per-book prices passed
    through -- see 4.2.)
- Data needed: every slate row field. Expanded mode additionally needs the raw
  `book_prices` dict (book -> {side: decimal}) which odds_shop already parses via
  `parse_event_books` but slate currently collapses to best-only.

### (b) +EV Feed
- A ranked list of (matchup, side, best book, best price, fair/no-vig price, EV%).
- Built from `model_ev_best` (home) + `model_ev_b` (away) + `fair_prob_a/b`.
- Filters: min EV%, sport, book. Sort by EV% desc.
- Honest label on the view: "+EV vs the best price you can bet -- an execution
  read, not a beat-the-close edge."
- Data needed: `p_home_win`, `best_*_price/book`, `fair_prob_a/b`, `model_ev_best`,
  `model_ev_b` (expose the away EV + fair probs that summarise_twoway already returns).

### (c) Arbitrage finder
- Cards filtered to rows where `arb_pct` is not None.
- Each card: matchup, side A (home book+price), side B (away book+price), guaranteed
  return %, stake split, "found at HH:MM:SS", and the fragility warning.
- Data needed: `best_home_book/price`, `best_away_book/price`, `arb_pct`, and the
  stake split `arb_stake_a/b` (expose these from summarise_twoway through slate).

### (d) Bet Tracker / CLV
- Header KPIs: count, CLV%, % beating close, paper ROI, bankroll curve (paper).
- Table of logged intents (from `/api/intent`): time, matchup, side, price taken,
  closing price (filled later), CLV, result. Green/red by CLV sign.
- Data needed: the intent log + a later closing-price fill. Strictly paper.

### (e) Per-event detail (drawer/expand from Board)
- Model block (full pregame summary + honest note + verdict), the full per-book
  grid for each available market, EV + arb for that event, link to book.
- Data needed: the full `result` from `predict_matchup.build_result` (the slate
  already calls it -- expose the richer pregame dict, not just the compact string)
  + raw book_prices.

---

## 3. Tech path -- recommendation

### Option A -- Enhance the current vanilla HTML/JS board
Pros: zero new deps/build step; ships today; one file; matches the repo's
no-framework `static/` serving; trivial to keep <=300 LOC discipline per file by
splitting into a few small JS modules; nothing to learn.
Cons: hand-rolled state/components get unwieldy past ~3 screens; no component
library so polish (logos, drawers, charts, responsive cards) is manual CSS; harder
to reach the "premium" bar the user wants.
Effort: ~0.5-1 day for grid + filters + sort + +EV/arb tabs as plain JS.

### Option B -- Rebuild as React + Vite + shadcn/ui
Pros: premium UI fast -- shadcn/ui gives accessible Table, Tabs, Select, Slider,
Badge, Card, Drawer, Sheet, Tooltip out of the box; Tailwind density + dark mode
are first-class; the repo HAS the `shadcn-ui`, `react-components`, and
`stitch-design` skills, so generation + integration is supported; TanStack Table
gives sort/filter/sticky-column/virtualization for the big grid for free; recharts
for the bankroll/line-movement charts; trivially responsive (card fallback on
mobile -- the Outlier differentiator).
Cons: adds a Node/Vite build + `node_modules` to a Python repo; a build artifact to
serve from FastAPI (`/static` -> Vite `dist/`); more moving parts; the per-file LOC
rule and "build under scripts/platformkit/" still apply to the new frontend tree.
Effort: ~2-3 days to parity + premium polish, less with the Stitch/shadcn skills.

### RECOMMENDATION: Option B (React + Vite + shadcn/ui), staged.

Reasoning:
1. The user explicitly wants "the BEST possible UI using different methods /
   external tools" -- that is a direct mandate for the component-library path, and
   the repo already ships the exact skills (`shadcn-ui`, `react-components`,
   `stitch-design`) to make it cheap.
2. The product is genuinely multi-screen (board, +EV, arbs, tracker, detail) with a
   dense sortable/filterable grid, sticky columns, drawers, and charts. That is
   precisely where vanilla JS rots and shadcn/TanStack shine.
3. Mobile-responsive "actually usable" is the single most-praised thing about the
   best tool (Outlier) and the easiest win with Tailwind + shadcn that is painful
   by hand.
4. Honesty rules are UNAFFECTED by the framework -- the banner, the "EV vs best
   price" labelling, the arb fragility warning, and paper-only logging all port
   directly. The FastAPI `/api/slate` + `/api/intent` contract stays; React just
   becomes a richer client of the same JSON.

De-risk with a staged plan so we are never blocked:
- Stage 0 (do first, Option-A style, ~half day): on the EXISTING page, expose the
  fields odds_shop already computes (away EV, fair probs, arb stake split), add the
  best-price columns + arb flag, add sport-aware sorting and a min-edge filter.
  This delivers value immediately and de-risks the data contract before any React.
- Stage 1: scaffold Vite + React + Tailwind + shadcn under
  `scripts/platformkit/frontend/web/`; build the Board grid with TanStack Table
  reading `/api/slate`. Serve the built `dist/` from the existing FastAPI static
  mount.
- Stage 2: +EV Feed tab and Arb cards (need the 3 extra fields from Stage 0).
- Stage 3: Tracker/CLV tab over `/api/intent` + recharts bankroll curve.
- Stage 4: per-event detail drawer (full pregame block + per-book grid) + mobile
  card fallback + logos + live badges.

Keep `index.html` working until Stage 1 is at parity, then switch the static mount.

---

## 4. Wireframes (ASCII)

### 4.1 Main Board (compact mode)

```
+--------------------------------------------------------------------------------+
|  Multi-Sport Decision-Support Board          sport [ NBA v ]   o auto  upd 3s  |
|  Pregame MATCHES the devigged close (calibration, not a money edge).           |
|  Markets are efficient -- NO $ edge claimed. You place every bet manually.     |
+--------------------------------------------------------------------------------+
|  market[ML v]  min edge [==o------] 2%   books [ DK FD MGM +3 v ]   search[__]  |
+----------+------------------+--------+------+----------------+---------+--------+
| Matchup ^| Model            |Verdict | Edge*| Best HOME      |Best AWAY| Arb EV*|
+----------+------------------+--------+------+----------------+---------+--------+
| BOS v LAL| P(BOS)=58% t~221 | MATCH  | +2.1%| FD  1.91  [>]  |DK 2.05  |  -  +1%|
| DEN v GSW| P(DEN)=63% t~229 | MATCH  | -0.4%| MGM 1.62  [>]  |FD 2.40  |  -  -2%|
| MIA v NYK| P(MIA)=49% t~215 | BEHIND | +0.8%| DK  2.10 *[>]  |MGM 1.78 | 1.3% +4|  <- best price highlighted *
+----------+------------------+--------+------+----------------+---------+--------+
| * Edge = model P(home) - market-implied P(home), decision support only.        |
| * EV = model EV at the BEST price you can bet -- execution read, not the close. |
+--------------------------------------------------------------------------------+
   [>] = open my book (external link; no bet is placed here)
   click a row -> per-event detail drawer (full book grid + model note)
```

### 4.2 Expanded book-grid (per-event, sticky first column)

```
| BOS vs LAL  (ML)     |  FD  |  DK  |  MGM |  CZR | Caesars | No-Vig | Vig% |
|----------------------|------|------|------|------|---------|--------|------|
| BOS (home)           | 1.91 |1.88  | 1.90 |1.85  |  1.89   | 1.93   |      |
|  best ->             |  **  |      |      |      |         |  fair  | 4.2% |
| LAL (away)           | 2.02 |2.05**|2.00  |1.98  |  2.01   | 2.08   |      |
   model P(BOS)=58.3%   honest_note: "matches devigged close within noise"
```

### 4.3 Arb card

```
+-------------------------------------------------+
|  ARB  guaranteed +1.3%        found 00:00:06 ago|
|  MIA vs NYK  (Moneyline)                        |
|  MIA  @ DraftKings   2.10   stake 45.9%   [>]   |
|  NYK  @ FanDuel      2.02   stake 54.1%   [>]   |
|  Split $100 -> $45.90 / $54.10 ; locks ~+$1.30  |
|  ! Arbs are rare, vanish fast, and books void / |
|    limit accounts that take them. Fragile.      |
+-------------------------------------------------+
```

### 4.4 +EV feed row

```
+-----------------------------------------------------------------------------+
|  +EV (vs best bettable price -- execution read, NOT a beat-the-close claim)  |
+--------------+-----+----------+--------+----------+--------+-----------------+
| Event        |Side | Book     | Price  | No-Vig   |  EV%   | Action          |
+--------------+-----+----------+--------+----------+--------+-----------------+
| MIA v NYK    | MIA | DraftKngs| 2.10   | 2.04     | +4.1%  | [open my book >]|
| BOS v LAL    | BOS | FanDuel  | 1.91   | 1.93     | +1.2%  | [open my book >]|
+--------------+-----+----------+--------+----------+--------+-----------------+
   sort: EV% desc   filter: min EV [+1% v]  sport [NBA]  book [all v]
```

---

## 5. Honesty guardrails (carry into every screen)

- Persistent amber banner with the `HONEST_NOTE` on every screen.
- "Edge*" always footnoted: model P - market-implied P, decision support only.
- "EV*" always footnoted: EV vs the BEST price you can actually bet; NOT a claim to
  beat the sharp close; the model does not beat the close.
- Arb cards always carry the fragility warning (rare / short-lived / limit-voided).
- Verdict colors stay honest: MATCH/AHEAD/CALIBRATED green, BEHIND red, UNKNOWN grey.
- NO sportsbook connection, NO auto-execution anywhere; the only action is an
  external link + a PAPER-ONLY intent log. No real-money, no book sync, no ROI claim.
- Unavailable data -> explicit "unavailable" state, NEVER a fabricated number
  (slate already enforces this; the UI must render the null states, not hide them).

---

## 6. First upgrades (priority order)

1. Stage 0 on the existing page (half day, no deps): expose away-side EV, fair/no-vig
   probs, and arb stake split (already computed by `summarise_twoway`, just not
   surfaced); add best-home/best-away price+book columns and an Arb flag column; add
   sortable headers and a min-edge filter. Pure value, de-risks the data contract.
2. Pass raw per-book `book_prices` through the slate payload (today it is collapsed
   to best-only) so the expanded book-grid and +EV/arb tabs have their inputs.
3. Scaffold React + Vite + shadcn/ui under `scripts/platformkit/frontend/web/`;
   rebuild the Board with TanStack Table (sort/filter/sticky col); serve `dist/`
   from the FastAPI static mount; keep `index.html` as fallback until parity.
4. Add the +EV Feed tab and Arb cards.
5. Add the Tracker/CLV tab over `/api/intent` + a recharts bankroll curve (paper).
6. Per-event detail drawer + mobile card fallback + sportsbook logos + live badge.

---

## Sources
- https://oddsjam.com/ , https://oddsjam.com/betting-education/how-to-use-the-oddsjam-positive-ev-tool , https://oddsjam.com/betting-tools/arbitrage
- https://outlier.bet/ , https://flatstudio.co/projects/outlier_ios , https://screensdesign.com/showcase/outlier-smart-sports-betting
- https://www.bettoredge.com/post/top-odds-screens-for-sports-bettors-in-2026 , https://rotogrinders.com/sports-betting/online-sports-betting-odds-comparison-tool , https://www.oddschecker.com/
- https://pikkit.com/closing-line-value , https://oddsjam.com/betting-education/closing-line-value , https://betstamp.com/comparison/oddsjam
