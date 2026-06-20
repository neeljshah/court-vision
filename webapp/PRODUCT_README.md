# CourtVision -- Front-End Product README

A calibrated, multi-sport prediction **product** (NBA / MLB / soccer, with tennis
honest-empty in the offseason). One pipeline turns raw game data into a single
coherent, calibrated prediction per market, and this webapp is the cohesive,
honest reader for it.

> **Honest by construction.** UNITS / probability only -- there is **no `$`
> field anywhere**. The honest win is **calibration, not a market edge**. The
> self-improve loop is **READY but INERT** (human-gated OFF). Real money is
> **DENY** (paper only). `vs_close` is **UNPROVEN** where no liquid in-play price
> exists. The UI never fabricates a game or a number; missing data degrades to an
> explicit EMPTY / Stale / Degraded / Unavailable state, **never green-on-missing**.

---

## 1. Run it locally

Everything is **local only** -- no deploy, no push.

```powershell
# From the repo root (PowerShell). Starts the FastAPI predict_service on :8099
# and the Next.js webapp on :3000, waits until both answer, prints OPEN.
powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1

# Fast iteration (next dev, skips the production build):
powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Dev

# Honest health probe (STALE != GREEN; consumes the freshness field):
powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Health

# Stop both servers:
powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Stop
```

Then open **http://localhost:3000**.

Front-end-only commands (from `webapp/`):

```bash
npm run dev        # next dev on :3000
npm run build      # production build (run before handoff)
npm run typecheck  # tsc --noEmit
npm run test       # vitest run (per-file is fine; we never run a full py suite)
npm run lint       # next lint
```

---

## 2. What each page shows

| Route | Purpose (honest one-liner) |
|-------|----------------------------|
| `/` (Home) | Front door: hero, the DATA -> ... -> VALIDATION funnel, live status row, honest headline findings + the "calibration, not a market edge" disclaimer. |
| `/games` | Tonight's **real** slate as cards (`SlateCards`/`GameCard`). Honest-empty per sport when nothing is live -- never a fabricated game. |
| `/games/[sport]/[gameId]` | One game: `CoherentPrediction` (one anchor spines every market), `GameMarketSurface`, `ValidatedSignalsStrip`, reused `GameReport`/`BestBets`/`InGameNumber`/`ClvScoreboard`. |
| `/how-it-works` | The funnel + validation discipline in plain language: `FunnelDetail`, `ValidationDiscipline`, `HonestFindings`, `SelfImproveExplainer`, `WhatAmILookingAt`, `LiveExample` (honest-empty or a real pred). |
| `/risk` | Descriptive portfolio risk in **UNITS**: `PortfolioRiskPanel`, `BestBetRiskCard`, `ExposureLimitsPanel` (joint < naive-sum, capped quarter-Kelly, RoR descriptive). Never money advice. |
| `/progress` | Honest "getting better" view: `CoverageBars`, `VerdictTrend`, `VerdictTally`, `BacklogBurndown`, `CompletenessStrip`, `WhatsNext`. The model is **STATIC** -- not a live accuracy climb. |
| `/system` | Full gate-verdict ledger (`GateLedgerPanel`), `BacklogPanel`, `ClvOverTimePanel` + reused panels. A REJECT is a SUCCESS. |
| `/p6` | The live dashboard (lines / paper / detail) -- same product area as Games. |

A first-run **onboarding overlay** (`components/onboarding/OnboardingOverlay.tsx`)
auto-opens once with the four honest rails + this page map, and a persistent
"?" Help button (bottom-right) re-opens it any time.

---

## 3. Data sources / APIs

The webapp is a **read-only** reader; it never recomputes a prediction.

- **`lib/p5api.ts`** -- low-level transport against the canonical predict_service
  (`P5_BASE`, default `http://127.0.0.1:8099`). Real per-sport data: NBA / MLB /
  soccer / soccer_intl live; tennis honest-empty.
- **`lib/api.ts`** -- the single import surface (`import { api, ... } from "@/lib/api"`).
  Re-exports all of p5api and adds the combined honest product status
  (`all_honest`, self-improve INERT/READY, real-money DENY) + read-only findings.
- **`lib/fetchHonest.ts`** -- the hardened fetch primitive: bounded timeout +
  capped backoff retry, **never throws**, degrades to an `Unavailable` sentinel.
- **`lib/useStream.ts`** -- the live in-game stream hook; surfaces a
  **disconnected** state (no snapshot) and a degraded "last snapshot (stale
  frame)" note rather than a fake live number.
- **`lib/config.ts`** -- `API_BASE` (legacy :8000), WS URL, REST helper.
- Same-origin Next route handlers (e.g. `app/system/funnel-artifacts`) read the
  on-disk funnel artifacts directly, so the ledger renders even when the Python
  service is down.

Every fetcher returns either the typed body **or** an `Unavailable` sentinel
(`isUnavailable(x)`); panels render an honest EMPTY / Degraded / Unavailable
state on the sentinel.

---

## 4. Honest framing + the 3 human gates (stay OFF)

The product is honest by construction. Three gates are human-gated and remain
**OFF** in this build -- do not flip them from the front end:

1. **Self-improve loop** -- READY but **INERT**. The model does not recalibrate
   itself; `/progress` is coverage/verdicts over time, not a live accuracy climb.
2. **Real-money placement** -- **DENY** by default. Paper mode only; the Nav
   shows a permanent `paper` badge.
3. **`vs_close` grading** -- **UNPROVEN** wherever no liquid in-play closing price
   exists. We never print a beat-the-close claim there.

The only gate survivor that ships is **soccer corners**, and it ships as a
**CALIBRATION** improvement, not a market edge. A REJECT is recorded as a
SUCCESS (markets are efficient). The retracted artifact numbers
(+18.38% / 0.119 / +54% / 78.11) are never printed as current.

---

## 5. Front-end dev: where to work on details

A front-end dev can pick up DETAILS here with confidence. Map:

### Component map (`webapp/components/`)

- **Shell / nav** -- `AppShell.tsx` (skip-link, main landmark, footer rail,
  mounts the onboarding overlay), `Nav.tsx` (links, theme toggle, mobile menu),
  `ProductStatusBadges.tsx` (honest status pills).
- **Shared depth primitives** -- `components/depth/*`: `InfoTip`, `Legend`,
  `ProvenanceBadge`, `SignalVerdictBadge`, `UncertaintyBar`, `MarketSurfaceTable`,
  and **`glossary.ts`** (the single source of "what is this number?" copy).
  Import via the barrel `@/components/depth`.
- **Honest states** -- `components/honest/*`: `HonestState`, `RouteError`,
  `RouteLoading`. Use these for every empty / error / loading surface.
- **Onboarding** -- `components/onboarding/OnboardingOverlay.tsx` (first-run
  guide + persistent Help). Page-purpose copy lives in `PAGE_GUIDE` there.
- **Per-area panels** -- `components/games_depth/*`, `components/risk/*`,
  `components/progress/*`, `components/system/*`, `components/explain/*`,
  `components/home/*`, reused `components/p6/*`.

### Design tokens

- **`lib/tokens.ts`** + `app/globals.css` (CSS variables) + `tailwind.config.ts`.
  Semantic colors: `success` / `warning` / `danger` / `muted` / `border` /
  `foreground` / `background` / `surface-1`. Focus ring is `ring`.
  Color is **never the only signal** -- every badge carries a text label.
- Global `:focus-visible` ring is defined in `globals.css`; the skip-link uses
  `sr-only` + `focus:not-sr-only`.

### How to add a new market view

1. Add a typed fetcher to `lib/p5api.ts` (or reuse `api`); it must return the
   typed body **or** `Unavailable` -- never throw, never fabricate.
2. Build the panel from shared primitives (`MarketSurfaceTable` for surfaces,
   `SignalVerdictBadge` for verdicts, `InfoTip`/`Legend` for explanation).
   The surface table has a **"model prob"** header and **no price/payout/odds/$**
   column -- keep it that way.
3. Render an honest EMPTY / Degraded / Unavailable state via
   `components/honest/*` whenever `isUnavailable(...)`.
4. Add a glossary entry in `components/depth/glossary.ts` for any new term so
   `InfoTip term="..."` resolves a single honest definition.
5. Add a test file under the route's **own** `__tests__` dir (disjoint
   ownership): assert coherence (displayed pick == the model prob it came from),
   the honest empty/unavailable path, and that no `$<digit>` reaches the DOM.

### How honest-states work

- Fetchers degrade to an `Unavailable` sentinel (`{ status: "unavailable",
  reason }`); guard with `isUnavailable(x)`.
- A stale / never-produced feed reads STALE / Degraded, **never GREEN**
  (mirrors the `-Health` rail in `view_local.ps1`).
- The live stream (`useStream`) distinguishes **streaming** vs **disconnected
  (no snapshot)** vs **degraded (last/stale snapshot)** -- never invents a frame.

### Accessibility baseline

- Skip-to-main-content link is the first focusable element (`AppShell`).
- Nav exposes `banner` + named `navigation` landmarks; active route uses
  `aria-current="page"`; icon-only buttons (theme, mobile menu) have aria-labels.
- The sortable gate ledger header buttons have aria-labels; the owning `<th>`
  carries `aria-sort` (ascending / descending / none).
- `InfoTip` is a real `<button>` with an accessible name; tooltips use
  `role="tooltip"`.
- Verdict / status badges render the verdict as **text**, not color alone.
- Smoke coverage: `components/__tests__/a11y-smoke.test.tsx` +
  `components/system/__tests__/gate-ledger-a11y.test.tsx`.

### Testing

- `vitest` only (`npm run test`). Per-file is fine. Each route's tests live in
  its own `__tests__` dir to avoid collisions; a test lane that finds a bug in a
  shared component **reports** it rather than editing the shared source.

---

*Calibrated decision-support only. Markets are efficient; no dollar edge claimed.
CLV (better-number-than-close) is the only honest yardstick. Paper mode only.
Local only.*
