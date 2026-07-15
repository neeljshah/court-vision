# Product Overview

## What it is

A **calibrated multi-sport predictor** with a real, CLV-tracked paper
trail, a live CourtVision UI (court-visions/), a self-improving autonomous
loop, and a governance layer that hard-blocks dishonest artifacts before
they ship.

## Honest value proposition

The sellable claim is NOT a dollar ROI or a betting edge. A sophisticated
quant buyer gets exactly this honesty:

- **Out-of-sample calibration** (Brier / ECE) under a leak-free,
  walk-forward, truncation-invariant, reproducible methodology.
- **Closing-line-value (CLV) discipline** -- every paper bet is graded
  against the true close (proxy-close labelled separately). A positive
  mean_clv_pct means bets were recorded at a better number than the close,
  on average. CLV is computed by the vetted clv_ledger and never recomputed
  in the sell layer.
- **A signed, tamper-evident track record** -- HMAC-SHA256 over the
  canonical JSON; any single mutated field (top-level or nested) fails
  verify.
- **Governance honesty gates** -- governance.run_governance exits 0/1;
  a retracted figure or a $-edge key RAISES and nothing ships.
- **One-command reproducibility** -- `python -m sell.evidence_pack` rebuilds
  the complete evidence pack from scratch.

No dollar ROI / P&L / edge is asserted anywhere. The track record and the
sell API carry edge_claimed=false by design.

## Architecture (5 bullets)

- **Sport-blind kernel** (`kernel/`) + per-sport adapters (`domains/<sport>/`)
  -- NBA, MLB, soccer, tennis are proven adapters on shared machinery.
- **Monte Carlo possession sim** (`src/sim/basketball_sim.py`) driving all
  markets coherently from a single player-level simulation.
- **Self-improving autonomous loop** (`scripts/loop/run_loop.py --forever`)
  -- discovers, validates, and ships (or reverts) signals unattended;
  eval-gate-gated recalibration; grade_summary and CLV ledger updated live.
- **Live CourtVision UI** (`court-visions/`, port 8098) -- in-game
  projected-finals, CLV ledger view, real-time paper-bet placement.
- **Governance layer** (`governance/`) -- honesty_linter + run_governance
  hard-block any artifact with a banned $-edge key or a retracted figure
  before it reaches disk or the API.

## What is NOT claimed (binding)

- No dollar ROI / P&L / edge anywhere (`edge_claimed=false` on every
  API surface and track record).
- In-game gain is CALIBRATION vs a base-rate prior; vs the close it is
  UNPROVEN (no in-play odds captured) -- not a realized market edge.
- Pregame team-strength markets are efficient: the model matches the
  devigged close within noise. MATCHES_CLOSE and BEHIND are honest
  successes, not failures.

## Public deploy

Public deployment and pushing to `origin` are **human-gated**. No agent
ever pushes to a public remote or deploys automatically.
