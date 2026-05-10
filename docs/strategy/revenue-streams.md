# Revenue Streams — Beyond Direct Bankroll

*Status: Stream 1 (betting) is the current focus. Streams 2–4 are longer-term diversification. Updated 2026-05-10.*

---

## Overview

The direct betting operation is the primary revenue source but is capital-constrained and faces account-limiting headwinds. Three additional revenue streams leverage the same model infrastructure with different risk/capital profiles.

---

## Stream 1: Direct Betting Profits (Primary)

**Mechanism:** Deploy bankroll against +EV opportunities identified by the system; collect edge over volume.

**Capital requirement:** Meaningful profitability at $10K–$50K bankroll; scales with bankroll.

**Risk:** Variance is real. Even with a 3% edge, a 312-bet sample can produce drawdowns of 10–15% due to natural variance. The Kelly sizer and circuit breakers manage this, but bankroll management discipline is required.

**Ceiling:** Constrained by sportsbook account limits (~$300 bets per account, 6 accounts = ~$1,800 total runway) and P2P market depth. Estimated sustainable annual profitability at $50K bankroll and 3% edge: $5,000–$15,000 depending on volume.

**Scaling path:** Grow bankroll from profits; migrate to P2P market making as sportsbook accounts age.

---

## Stream 2: Picks / Predictions Service (No Capital Risk)

**Mechanism:** Sell model output (probability estimates and recommended bets) as a subscription service.

**Economics:**
- Subscription range: $50–200/month per subscriber
- 100 subscribers = $5,000–$20,000/month at zero capital risk
- 500 subscribers = $25,000–$100,000/month

**Required first:** Validated track record with verifiable CLV data. The 312-bet history at +14 bps CLV and +3.8% ROI is the start of this track record; 500+ bets with sustained positive CLV is the threshold for marketing credibility.

**Format options:**
- Daily email/app with recommended bets, model probabilities, Kelly-suggested sizes
- API access to real-time model output (higher tier)
- Telegram/Discord channel with alerts on timing events (injury updates, line movements)

**Legal note:** Selling sports picks commercially is generally legal for individuals in the US without a license requirement (unlike investment advice). Verify Iowa-specific requirements; the current understanding is no license is required for individual picks sellers.

**Positioning:** Not "tips" or "handicapping." Position as model output with full methodology transparency, verifiable backtests, and CLV as the primary metric. The audience is sophisticated bettors who want quantitative signals, not recreational bettors who want picks.

---

## Stream 3: Model / API Licensing (Longer Term)

**Mechanism:** License model outputs or API access to:
- DFS players who want predictive distributions for lineup construction
- Fantasy sports platforms seeking proprietary analytics
- Other bettors who want infrastructure without building it

**Economics:** API licensing is typically $200–$2,000/month per commercial customer. 10 commercial API customers = $2,000–$20,000/month.

**Requirements:** Clean API interface, uptime SLA, documentation. The FastAPI backend (see [`api/main.py`](../../api/main.py)) already serves model outputs; the commercial licensing layer is primarily legal/billing infrastructure.

**DFS opportunity:** DraftKings and FanDuel host multi-million-dollar DFS contests where lineup optimization using probability distributions provides a measurable edge over naive players. This is a large addressable market for model outputs.

---

## Stream 4: Dashboard as a Product (Longer-Term)

**Mechanism:** The integrated quant betting terminal (see [dashboard-spec.md](../architecture/dashboard-spec.md)) has standalone value for sharp bettors who have their own models but want the infrastructure.

**Positioning:** Target bettors with $50K+ bankrolls who bet systematically but lack portfolio risk management, CLV tracking, account health monitoring, and real-time odds streaming in one tool.

**Competitive gap:** OddsJam, Unabated, Pikkit, and Betstamp each solve one piece of this. None combines model signals + portfolio risk + CLV attribution + account health in one interface.

**Revenue model:** SaaS subscription ($100–500/month per user). 50 users = $5,000–$25,000/month.

**Prerequisite:** The dashboard must first serve the primary operation reliably. Do not build a SaaS layer on top of a tool that isn't stable enough for internal use.

---

## Priority Sequencing

```
Now:
  Stream 1 (Betting) — build the system, validate CLV, grow bankroll

After 500+ validated bets:
  Stream 2 (Picks service) — limited release, 20–50 subscribers

After Season 2 (2027-28):
  Stream 3 (API licensing) — commercial API tier on existing FastAPI backend
  Stream 4 (Dashboard) — SaaS launch if internal tool is stable

Long-term:
  P2P market making becomes the primary form of Stream 1
  Streams 2–4 provide income independent of capital deployment
```

---

## Risk Management Across Streams

**Stream 1 risk:** Bankroll variance, account limiting. Mitigated by Kelly sizing, circuit breakers, account rotation.

**Stream 2 risk:** Reputation risk if picks underperform. Mitigated by only publishing model output (not "guarantees"), showing calibration alongside picks, publishing a methodology.

**Stream 3 risk:** API outages, data quality issues becoming customer problems. Mitigated by SLA-appropriate uptime monitoring (see [dashboard-spec.md](../architecture/dashboard-spec.md) System Health panel).

**Stream 4 risk:** Competition from better-funded teams building the same dashboard. Mitigated by first-mover advantage among sharp bettors and the depth of the proprietary CV signal that no competing dashboard can replicate.

---

*See [MASTER_PLAN.md](../../MASTER_PLAN.md) for the full strategic context. See [validation-methodology.md](../research/validation-methodology.md) for the track record requirements before launching Stream 2.*
