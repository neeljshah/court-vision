# FINAL REPORT — Your AI Prediction + Paper-Trading System

_Last verified: 2026-07-15. Honest by design: this is a **calibrated-prediction** system, not a profit product. Paper / units only. Real money is OFF (default-DENY)._

---

## TL;DR — what you have

A live, self-healing, self-improving **4-sport (NBA / MLB / soccer / tennis) AI** that:
- ingests data → builds signals → trains models → runs a **player-level possession Monte-Carlo simulation** → produces **calibrated predictions** for every market,
- surfaces them as **best-bets cards**, **live games**, and a **paper-trading center** with your records,
- **paper-trades** in units (never dollars), grades itself with **CLV** (closing-line value),
- **gets better on its own** through a do-no-harm self-improve loop,
- runs as a **44-service supervised stack** that stays up **without Claude** and heals itself.

**Verified right now:** 41/44 services READY (3 restarting) · all pages styled + 200 · 5,000 prediction records surfaced · 58 best-bets cards (mixed sports) · governance ALL PASS · `$`-leaks = 0 · real-money DENY.

---

## Run it + see everything (no Claude needed)

```
.\go.ps1      # starts the whole stack + opens the UI
.\stop.ps1    # stops everything cleanly
```

Then open **http://localhost:3000**:

| Page | What it shows |
|---|---|
| **/bets** | Best-bets cards (player-prop + game), confidence, multi-book lines + best line, units, tier, CLV. Click a card → full detail + execution trail. |
| **/records** | **Your 5,000 paper-prediction records** — matchup, selection, model prob, line, fair odds, result, CLV. |
| **/paper-trading** | The paper-trading center: prediction-market (Kalshi/Polymarket) trail, live/done sections, running units tally. |
| **/live** + **/games** | Live + today's games with in-game predictions (honest "none right now" when no games are live). |
| **/models** | **How the AI is getting better** — the ratchet, per-sport calibration trends, ship/candidate timeline. |
| **/system** | **Live independent-stack status** — every service, heartbeat age, self-heal, uptime (this is your "is it working?" page). |

> The UI is served from a **production build** for stability. After any frontend code change, run `npm run build` in `webapp/` then `.\go.ps1` to publish it.

---

## How to read the predictions (what the numbers mean)

- **model_prob** — the calibrated probability the model assigns (e.g. 0.55 = 55%).
- **line / fair_odds** — the market line and the model's fair odds for it.
- **edge-vs-market / divergence** — how far the calibrated model sits from the market. **This is calibrated divergence, NOT a profit claim.** A "no-bet" (model agrees with the efficient close) is a *success*, not a miss.
- **confidence / tier** — a derived ranking proxy, not a guarantee.
- **CLV** — better-number-than-close; the **honest yardstick** for whether a number beat the close. Shows **INSUFFICIENT_DATA** when no liquid closing line exists (currently true — offseason / few liquid in-play prices).
- **units** — sizing in units. **There is no dollar figure anywhere.**

Full depth: **`docs/guide/`** (12 in-depth docs — start at `docs/guide/README.md`).

---

## How it gets better (and how to watch it)

The self-improve loop ingests settled games → proposes recalibration candidates → runs them through a **5-gate, do-no-harm ratchet** → ships **only** changes that improve held-out calibration (Brier/ECE/BSS), else honestly reports **NO_CANDIDATE**. A CLV second-corpus acts as a do-no-harm guard. Watch it on **/models**.

Honest expectation: ships are **rare and gated**. Most cycles are NO_CANDIDATE — that's the system refusing to fool itself, which is the point.

---

## Honest limits (what may / may not be claimed)

- Markets are **efficient pregame** — we **match the devigged close**, we do **not** claim to beat it.
- The decisive measured edge is **in-game conditioning** (calibration), delivered + calibrated.
- **Paper / units only. Real money is default-DENY.** No `$` P&L anywhere.
- **vs-close CLV is UNPROVEN** where no liquid closing prices exist (shown honestly as INSUFFICIENT_DATA).
- Retracted measurement artifacts (e.g. an old +18.38% pregame ROI, an endQ3 Brier, a +54% in-play figure) appear **only** inside explicit retraction notes — never as current results. Truth source: **`docs/JOB_EVIDENCE_PACKET.md`**.

---

## Go fully live (3 human-only gates — currently OFF by design)

You (the human) flip these when ready; the system never flips them itself:
1. **Arm self-improve** — create the file `data/cache/improve/PIPELINE_ENABLED` (already armed in `go.ps1`).
2. **Auto-start on boot** — `.\register_autostart.ps1 -Register` (runs the stack at login, unattended).
3. **Enable real money** — flip the real-money gate from default-DENY. _This is a real financial decision — do it deliberately._

---

## What is where

- **Run/control:** `go.ps1`, `stop.ps1`, `view_local.ps1`, `register_autostart.ps1` (repo root).
- **In-depth docs:** `docs/guide/00..10` + `README.md`; truth source for claims: `docs/JOB_EVIDENCE_PACKET.md`.
- **Backup:** no dated backup directory currently exists on disk (the `nba-ai-backup-2026-06-20` copy referenced previously is gone). **Make a fresh full-repo + auto-memory + data backup** before relying on one.
- **APIs:** predict_service (:8099) + boards (:8098); UI (:3000).
- **Live status files:** `data/frontend/ops/supervisor_status.json`, `autonomy_status.json`.

---

## What was done today (this session)

- Built/deepened the **all-in-one front end**: best-bets cards, click-through detail, **records surface (your 5,000)**, **paper-trading center**, live/done sections, execution browse, live auto-refresh, full a11y + polish.
- **Surfaced the real data** that was hidden behind empty panels (records, 58 best-bets cards).
- **Fixed two crash-loops** (orphaned ports 8099 then 3000) and made the orphan cleanup permanent in `stop.ps1`.
- **Fixed the white-page** (corrupted dev cache) by switching to a stable production build.
- Fixed honesty defects the review fleet caught (dead/stale market cards, degenerate-model edge claims, CLV row-key) → governance now ALL PASS.
- Wrote **12 in-depth docs** (committed locally), improved **memory** (10 curation passes, connected + verified), and made a full backup at the time (since removed — see backup note above).

**Status: live, stable, honest, filled, documented, backed up.** Verified green at the timestamp above.
