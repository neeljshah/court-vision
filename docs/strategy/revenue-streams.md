# Revenue Surfaces — Six-Surface Monetization

*Six revenue surfaces — personal betting, fund management, signal subscriptions, team licensing, media augmentation, knowledge-layer API.*

---

## Overview

CourtVision is not a betting tool. It is a sports intelligence substrate that supports six monetization surfaces, deployed in sequence on top of the same model infrastructure. Personal betting is the primary feedback signal but is capital-constrained and faces account-limiting headwinds; the other five surfaces leverage the substrate with different risk, capital, and regulatory profiles. The substrate is built once; the surfaces are added as their gates clear.

| Surface | Status | Gate | Revenue target (scale) |
|---------|--------|------|-----------------------|
| 1. Personal betting | Active (paper-trading) | Gate 1 first | $1–5M/yr |
| 2. Fund management | Planned | 12-mo audited track record | $10–35M/yr |
| 3. Signal subscriptions | Planned | CLV track record public | $3–8M/yr |
| 4. Team / scouting licensing | Demo-ready | Pitch + demo | $1–5M/yr |
| 5. Media / broadcast augmentation | Planned | Team licensing proof | $500K–2M/deal |
| 6. AI knowledge layer API | Planned | Multiple surfaces live | Metered |

---

## Surface 1: Personal Betting (Primary, Validation Surface)

**Mechanism:** Deploy bankroll against +EV opportunities identified by the system; collect edge over volume. Iowa-legal, fully online. Multi-book (DraftKings, FanDuel, BetMGM, Caesars, bet365) plus P2P exchanges (Novig, ProphetX — zero vig, no account limiting).

**Economics:** Meaningful profitability at $10K–$50K bankroll; scales with bankroll. Variance is real — even with a 3% edge, a 312-bet sample can produce drawdowns of 10–15%. The Kelly sizer (half Kelly always) and circuit breakers manage this. Ceiling is constrained by sportsbook account limits (~$25–500/bet, account limiting after ~300 winning bets) and P2P market depth: ~$1–5M/year at scale.

**Requirements:** None beyond the built substrate. P2P exchanges become the primary venue as retail accounts age out.

**Status:** Active — paper-trading harness built. **Gate 1 (first CLV validation against real Pinnacle closing lines) NOT YET RUN.** Go-live gate: ≥50 settled bets, CLV beat rate ≥55%, paper ROI ≥3%, all simultaneously.

---

## Surface 2: Fund Management (After Audited Track Record)

**Mechanism:** Audited returns attract LP capital. The same signals that power personal betting are deployed at larger scale via P2P exchange market making, routed through individually-held accounts to avoid book flagging.

**Economics:** Informal LP agreements with 3–10 investors on a profit-split basis — not a registered fund (regulatory burden). P2P exchanges have higher capacity than retail books, supporting $500K–2M under management initially and a $10–35M/year ceiling at scale.

**Requirements:** 12+ months of audited track record at ≥55% CLV beat rate, Gate 1 passed, and reproducibility evidence (model registry, holdout R²s, CLV charts). Targets sports-context-aware family offices and HNW individuals. Note: Kalshi is legally gray in Iowa as of 2026-05 — monitor but do not build on it.

**Status:** Planned. Gated on the same CLV track record as Surface 1, extended to 12 months.

---

## Surface 3: Signal Subscriptions (No Capital Risk)

**Mechanism:** Sell model output — probability estimates, confidence tiers, recommended bet sizes — as a subscription service to sophisticated bettors. Capped at ~30 subscribers to preserve edge; more subscribers leak signal into the market faster.

**Economics:**
- Tiered pricing: Base ($5K/month, top-tier prop signals), Full ($15K/month, all 7 props + context signals), Premium ($25K/month, live alerts + raw outputs + research notes)
- 30 subscribers × $15K average = $450K/month ≈ $5.4M/year; surface ceiling $3–8M/year
- Zero capital risk — scarcity and the subscriber cap support premium pricing

**Requirements:** A publicly documented CLV track record (12+ months, Pinnacle-close verified). The 312-bet history at +14 bps CLV and +3.8% ROI is the start of this record; without auditable evidence no serious sharp will pay. Position as model output with full methodology transparency and CLV as the headline metric — not "tips" or "handicapping." Selling sports signals commercially is generally legal for individuals in the US without a license; verify Iowa-specific requirements.

**Status:** Planned. Earliest meaningful release after the CLV track record is public.

---

## Surface 4: Team / Agent / Scouting Licensing (Demo-Ready)

**Mechanism:** License CV spatial features — defender pressure, spacing, play type, shot quality by context, fatigue curves — to NBA front offices, player agents, and analytics consultancies.

**Economics:** Second Spectrum charges $100K+/year per team for in-arena camera tracking. CourtVision extracts equivalent signals from broadcast video, which also covers G-League, college, and international games at the same cost. Pricing: NBA front offices $150–400K/yr, player agents $50–100K/yr, DFS/fantasy operators $50–150K/yr. Five franchises plus other buyers → $2–5M/yr.

**Requirements:** A working demo on 3+ games, a pricing document, and a target list. No audited betting track record required — unlike Surfaces 1–3 — which makes this an early commercial surface despite its later number.

**Status:** Demo-ready. The CV pipeline already extracts `defender_distance`, `spacing_score`, `play_type`, and `fatigue_index`; the remaining work is an analytics dashboard on top of the existing data.

---

## Surface 5: Media / Broadcast Augmentation (Longer Term)

**Mechanism:** Real-time court-coordinate overlays during live broadcasts — "open / contested / impossible" shot probabilities, spacing visualizations, fatigue alerts for commentators. Delivered as a cloud API that accepts a live video stream and returns spatial annotations, wrapped for broadcast latency.

**Economics:** Broadcast networks need new formats as streaming cannibalizes linear TV; AI overlays are the natural evolution (cf. Hawk-Eye, TopSpin). Target buyers: ESPN, TNT, Amazon Prime, regional sports networks, NBA League Pass. Revenue: 1–2 deals at $500K–2M each.

**Requirements:** Team licensing proof (Surface 4) to demonstrate the spatial data is accurate and useful — broadcast deals require a reference customer.

**Status:** Planned. Gated on Surface 4 traction.

---

## Surface 6: AI Knowledge Layer API (Longer Term)

**Mechanism:** A sports brain queried by LLM applications and metered by call — player history, spatial telemetry, prediction distributions, and event sequences exposed as a structured API. The integrated quant betting terminal (see [dashboard-spec.md](../architecture/dashboard-spec.md)) and the FastAPI backend (see [`api/main.py`](../../api/main.py)) are the delivery mechanisms: the dashboard for human users, the metered API for LLM apps, DFS optimizers, and broadcast analytics tools.

**Economics:** Metered per call ($0.01–0.10/query depending on complexity), volume discounts, enterprise SLA. As LLM applications proliferate, domain-specific sports context becomes commodity infrastructure. Ceiling is speculative and dependent on LLM-app proliferation in sports: $1–5M/yr at scale.

**Requirements:** The knowledge graph must be built (planned months 4–6), and multiple commercial surfaces must be live to establish that the data is trustworthy. The FastAPI backend already serves model outputs; the commercial layer is primarily metering, billing, and SLA infrastructure.

**Status:** Planned — the latest surface, dependent on the others.

---

## Priority Sequencing

```
Now:
  Surface 1 (Personal betting) — run Gate 1 first, validate CLV, grow bankroll

After CLV track record is public:
  Surface 3 (Signal subscriptions) — limited release, capped subscribers
  Surface 4 (Team licensing) — demo-ready now; pitch in parallel, no track record needed

After 12-month audited returns:
  Surface 2 (Fund management) — informal LP capital on P2P exchanges

Longer term:
  Surface 5 (Media / broadcast) — once team licensing provides a reference customer
  Surface 6 (Knowledge layer API) — once the knowledge graph and multiple surfaces are live
```

Each surface enriches the others: personal betting generates CLV evidence → CLV evidence enables subscriptions and fund capital → subscription revenue funds research → research improves signals → better signals improve personal betting CLV.

---

## Risk Management Across Surfaces

**Surface 1:** Bankroll variance, account limiting. Mitigated by half-Kelly sizing, circuit breakers, account rotation, and migration to zero-vig P2P exchanges.

**Surface 2:** Regulatory and LP-reporting risk. Mitigated by informal profit-split structure (not a registered fund), audited reporting, and avoiding legally gray venues.

**Surface 3:** Reputation risk if signals underperform, and edge decay if the subscriber base grows. Mitigated by publishing model output (not "guarantees") with calibration and methodology, and by the ~30-subscriber cap.

**Surface 4:** Buyers may distrust broadcast-derived data versus in-arena tracking. Mitigated by accuracy demos on real games and the broader coverage (G-League, college, international) that in-arena systems cannot match.

**Surface 5:** API outages and latency becoming a broadcaster's on-air problem. Mitigated by SLA-appropriate uptime monitoring (see [dashboard-spec.md](../architecture/dashboard-spec.md) System Health panel).

**Surface 6:** Competition from better-funded teams building the same knowledge API. Mitigated by first-mover advantage and the depth of the proprietary CV signal that no competitor can replicate.

---

*See [VISION.md](../../VISION.md) and [MASTER_PLAN.md](../../MASTER_PLAN.md) for the full strategic context. See [validation-methodology.md](../research/validation-methodology.md) for the track record requirements before launching Surface 3.*
