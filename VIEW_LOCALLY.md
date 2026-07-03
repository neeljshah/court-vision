# View the product locally

One command to see the whole CourtVision predictor product in your browser.
Everything runs on YOUR machine. Nothing is deployed, pushed, or registered to autostart.

## Quick start

1. Open PowerShell in the repo root (`C:\Users\neelj\nba-ai-system`).
2. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1
   ```

3. Wait for the message: `READY.  OPEN  http://localhost:3000`
4. Open **http://localhost:3000** in your browser.

To stop: press **Ctrl-C** in that PowerShell window, or run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Stop
```

Faster startup (skip the production build, use the dev server):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\view_local.ps1 -Dev
```

The launcher starts two things and waits until both answer:

- **predict_service API** on `http://127.0.0.1:8099` (the canonical FastAPI server).
- **webapp** on `http://localhost:3000` (the Next.js product). The launcher sets
  `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8099` so the site reads the local API.

It is idempotent: re-running it stops any prior instance first. `-Stop` kills both
process trees cleanly.

## What each page shows

- **Home (`/`)** -- the product intro: what the system is and how it works at a glance.
- **How it works (`/how-it-works`)** -- the funnel (DATA -> SIGNALS -> MODELS -> ENGINES
  -> PREDICTIONS -> INTELLIGENCE), the honest discipline (leak-free / walk-forward /
  calibration not edge), and the real findings (what shipped, what was rejected).
- **Games (`/games`)** -- the live slate per sport: matchup cards with calibrated
  probabilities and suggested positions sized in **units** (not dollars). Click a card
  for the per-game detail (`/games/<sport>/<gameId>`). Empty sports show an honest
  "no slate" message -- never a fabricated game.
- **System (`/system`)** -- what the system is doing right now: status, honesty bit,
  parity, and the self-improve loop state.
- **/p6** -- the internal P6 dashboard view.

## Honest notes (read these)

- **Units, not dollars.** Position sizing is shown in units / probabilities only.
  There is NO dollar field anywhere. This is a calibrated *predictor*, not a $-edge product.
- **Self-improve is READY but INERT.** The self-improvement loop is wired and
  measurement-only; it is not flipped on and does not place anything.
- **Real-money is DENY by default.** No real-money execution path is enabled.
- **Tennis is offseason / unavailable.** It shows a clear empty state, not a fake slate.
- **Honest empty states everywhere.** If a sport has no slate, the page says so. We
  never fabricate a game or a price.

## What the launcher will NOT do

- It will not run `boot.ps1` (the full supervised stack), `run.py`, or `loop_processor.py`.
- It will not deploy, push to git, or register anything to start on boot.
- It starts only the two local viewer processes and stops them on exit.
