# 03 - How To See Predictions

This guide shows where the system's predictions actually surface -- the web pages, the
JSON APIs behind them, and the one-shot CLI -- and explains **every number you will see**
on screen.

Read this first so the framing is clear:

- This is a **calibrated predictor**, not a betting-edge product. The honest, defensible
  result is "**match the devigged closing line within noise**" on team-strength markets.
  Markets are efficient pregame; we do **not** claim to beat them.
- The one **measured** win is **in-game conditioning**: fusing the pre-game prior with the
  realized mid-game score sharpens the live win-probability forecast (a **calibration**
  gain, not a dollar edge -- a live book sees the score too).
- Everything is **units / probability only -- there is no dollar figure anywhere**, paper
  mode only, and real-money execution is **default-DENY**. (Truth source for any claim:
  `docs/JOB_EVIDENCE_PACKET.md`.)

---

## The two front ends

There are two surfaces, both read-only over the same backend:

```
  Next.js webapp (/bets, /games, /p6)  ->  reads  ->  Auto-API  http://127.0.0.1:8099
  FastAPI/Jinja dashboard (/tonight ...) ->          (api/main.py + predict_service/app.py, ~36 endpoints)
```

The webapp's API base is `NEXT_PUBLIC_P5_BASE`, defaulting to `http://127.0.0.1:8099`
(`webapp/lib/p5api.ts`). The typed client lives in `webapp/lib/p5api.ts` /
`webapp/lib/api.ts`; every fetch degrades to an explicit **Unavailable** sentinel on
error -- it is **never green-on-missing** and never fabricates a slate.

The five sports served are `nba`, `mlb`, `soccer`, `soccer_intl`, `tennis`
(`SPORTS` in `webapp/lib/p5api.ts`).

---

## The pages

### `/bets` -- Best Bets card board

The flagship view (`webapp/app/bets/page.tsx`). Cards are grouped into **Live / Pregame /
Done** sections and ranked by **calibrated model-vs-market divergence + confidence + CLV**.
A "no bet" result (model matches the efficient close) is rendered as a **calibration
success**, not a failure. Backed by `GET /api/bestbets/board`.

Each card (`webapp/components/bets/BetCard.tsx`) shows:

| On the card | Field | What it means |
|---|---|---|
| `NYK @ SAS` | `matchup` | The two sides. |
| `prop:pts +24.5 over` | `market_type` + `line` + `side` | Market, the posted line, and which side the model leans. |
| **Model p** | `model_prob` [0,1] | The **calibrated** model probability for that side. |
| **Market p** | `market_prob` [0,1] | The **devigged** market probability (vig removed). |
| **Calibrated divergence** | `edge_vs_market` = `model_prob - market_prob` | A signed calibration signal. **Not a profit/edge claim.** Negative is a valid under/away lean, never an error. |
| **Best book** `+105` | `best_book` + `best_odds` | Best price across books, shown in American odds. |
| **Units** `0.50u` | `units` | Quarter-Kelly stake **in units, never dollars** (can be <1 or >1). |
| **Tier** `S/A/B/C` | `tier` | Confidence/quality bucket from the gate; `--` / null means **no actionable bet**. |
| **CLV** | `clv` | See below. `null` renders as `INSUFFICIENT_DATA`. |
| **signal 60%** | `confidence` | A derived proxy from EV magnitude (`|ev|*5`, clamped). **Not** a profit claim. |

Honesty guards baked into the component: a `degenerate_model` card renders an explicit
`no_bet`; settled games render a settled label; divergence colour is keyed to *magnitude*,
never sign (a negative divergence is never red).

### `/games` -- the slate

Per-sport list of game cards (`webapp/app/games/page.tsx`). Each card is one matchup +
the **one coherent prediction** (probability) + a few key markets + a best-bet chip
(units + tier, or an honest **NO BET**). Click through to `/games/[sport]/[gameId]`.

### Card detail -- `/bets/[sport]/[gameId]`

The full per-game view (the "View detail" link on every card). Same numbers as the card,
expanded with the multi-book line comparison and per-prop line-move history.

### `/p6` -- the dashboard

The operator dashboard (`webapp/app/p6/page.tsx`), read-only over the Auto-API. Panels
include the slate browser, a live CLV scoreboard, the parity grid (cross-sport
coverage/loop health -- a broken cell goes **red** and fails the gate), the self-improve
ratchet (shipped **READY but INERT**, human-gated OFF), the in-game panel, ops/health, and
the paper trail streamed over SSE. It **reads** canonical values; it never recomputes them.

---

## The APIs (what the pages call)

All paths are relative to the Auto-API base (`http://127.0.0.1:8099`). Defined in
`webapp/lib/p5api.ts`; served by `api/main.py`.

| Endpoint | Returns |
|---|---|
| `GET /api/bestbets/board?sport=&tier=&status=` | Ranked best-bet cards (the `/bets` board). |
| `GET /api/predict/{sport}` | Latest snapshot **envelope** for a sport (`status: "ok"` when live). |
| `GET /api/predict/{sport}/{game_id}` | One game's coherent projection. |
| `GET /api/predict/props/{sport}?game_id=` | Player-prop board (`model_prob`, `line`, `tier`); degrades to **Unavailable** in the offseason. |
| `GET /api/results/{sport}?game_id=` | Settled finals -- real scores or nothing. |
| `GET /api/ingame/{sport}/{game_id}/full` | Composite live payload: score + win-prob + boxscore + prop projections + CLV status. |
| `GET /api/paper/clv` | Aggregate CLV scoreboard (units/probability only). |
| `GET /api/quant/{sport}/validate` | Per-game, per-market auditable verdicts (tier/units/edge/CLV/`gate_proven`). Most are `no_bet` / match-the-close -- a **success**. |
| `GET /api/status.all_honest` | The single product-wide honesty bit: `ok=true` only if **no** face violates a rail. |

Note the contract on `market_prob`: the backend derives it as **`1 / fair_odds`** (the
de-vigged fair probability), `null` when no line is available
(`predict_service/frontend/paper_predictions_routes.py`). So `fair_odds` is the
model's fair price; `market_prob` is its probability form; `model_prob` is the model's
own calibrated probability; and `edge_vs_market = model_prob - market_prob`.

---

## The CLI -- `predict-matchup`

For a one-off forecast without the web stack, use the `predict-matchup` skill, which wraps
the single buyer-facing entrypoint `scripts/platformkit/predict_matchup.py`:

```bash
# pregame
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL --markdown

# in-game (24 minutes elapsed, BOS 55 - LAL 50)
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
  --elapsed 24 --home-score 55 --away-score 50 --markdown
```

It prints `p_home_win` for the pregame block, and -- when a complete live state is supplied
-- an `ingame` block with the re-priced `p_home_win` plus a `pregame_p_home` field so you
can see the conditioning move. On a fresh clone with no local corpus it prints an
"unavailable" note and **exits 0** -- it never fabricates a number.

---

## How in-game predictions update live

A pregame number is static for a matchup. The **live** number is produced by feeding the
realized score state through the validated in-game repricer + recalibrator
(`src/prediction/live_engine.py`; CLI path `_ingame_block` in `predict_matchup.py`). On the
pages, the in-game payload comes from `GET /api/ingame/{sport}/{game_id}/full` and updates
via the per-game SSE stream:

```
  game in progress
        |
        v
  realized score state  --(repricer + in-game recalibrator)-->  conditional win-prob
        |                                                              |
        +------ SSE  /api/stream/game/{sport}/{gid}  ----> /p6 InGamePanel, card detail
```

The conditioned forecast is sharper than the static prior (the measured calibration win),
but it is **still calibration, not a dollar edge** -- a live book sees the same score. When
no live in-play closing price exists (e.g. NBA offseason), **CLV shows
`INSUFFICIENT_DATA`** rather than a fabricated value.

---

## Reading CLV honestly

CLV (closing-line value) = did we get a **better number than the close**. It is the only
honest yardstick of edge, and it is shown carefully:

- `clv = null` -> renders `CLV: INSUFFICIENT_DATA` (amber, **never green**). This is the
  common case today because liquid in-play closing prices are not yet captured.
- A numeric CLV is coloured by sign and flagged `(proxy)` when computed against a
  last-seen pre-tip line rather than a true close (`clv_is_proxy`).

Do **not** read the divergence column or the units number as profit. The full-season
leak-free backtest shows pregame CLV approximately **0** against real closing lines -- the
market is efficient, and that honest finding is the point.

---

## Where to look in the repo

- `webapp/app/bets/page.tsx` -- the `/bets` Best Bets board page.
- `webapp/components/bets/BetCard.tsx` + `BetCardHelpers.tsx` -- every field on a card, with its honesty tooltips.
- `webapp/app/games/page.tsx` -- the `/games` slate.
- `webapp/app/p6/page.tsx` -- the `/p6` dashboard and its panels.
- `webapp/lib/p5api.ts` -- the typed API client: every endpoint path, `P5_BASE`, `SPORTS`, the Unavailable sentinel.
- `webapp/lib/api.ts` -- product-status / honest-findings layer on top of `p5api`.
- `webapp/lib/types.ts` -- the wire types (`model_prob`, `line`, `tier`, CLV fields).
- `predict_service/frontend/paper_predictions_routes.py` -- the `market_prob = 1/fair_odds` contract.
- `scripts/platformkit/predict_matchup.py` -- the buyer-facing pregame + in-game CLI.
- `.claude/skills/predict-matchup/SKILL.md` -- how to invoke that CLI.
- `src/prediction/live_engine.py` -- the in-game projection / repricer.
- `api/main.py` -- the FastAPI surface (~36 endpoints total across `api/main.py` and `predict_service/`) behind the Auto-API.
- `docs/JOB_EVIDENCE_PACKET.md` -- the truth source for every number and the do-not-claim list.
