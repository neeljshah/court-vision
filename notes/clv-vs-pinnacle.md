# CLV vs Pinnacle on 312 settled picks: what closing-line value actually measures

## Abstract

CLV is the best pre-settlement predictor of long-run betting edge, and almost
everyone computes it wrong — either against their own book's close (circular) or
without de-vigging the closer (biased toward the heavy-favorite side). This writeup
tracks 312 settled picks from the CourtVision stack against Pinnacle's no-vig
Shin-devigged close. Mean CLV is +14 bps per bet, t=2.3 vs zero, with a right tail
dominated by ~20 prop lines that moved 8+ cents post-pick. I decompose CLV three
ways: (a) by market — props beat sides by +9 bps after controlling for other
factors; (b) by time-to-close — picks placed >4 hours pre-tip capture 3× the CLV of
picks placed in the final hour, consistent with market-maker liquidity concentrating
near close; (c) by bet size vs Kelly — picks sized at >1.0× Kelly *destroy* CLV,
because the size itself front-runs the market maker into widening. I close by being
explicit about what CLV cannot do: it cannot distinguish predictive skill from
mechanical line-shopping, it rewards first-movers on stale lines even when they're
uninformed, and it's a noisy estimator on samples under ~200. Most of these caveats
cut against my own sample; I think the +14 bps number is real but it's not *all*
skill.

## Outline

1. Methodology + Shin de-vig — why Shin, dataset description (312 picks)
2. Headline distribution — +14 bps, t=2.3, right-tail analysis
3. Cuts by market / time-to-close / bet-size-vs-Kelly
4. CLV vs realized ROI correlation — are they telling the same story?
5. Caveats — what CLV cannot distinguish; honest limitations

## The plot

Cumulative CLV in bps over bet sequence, with 95% bootstrap band. The band not
crossing zero late in the sequence is the money shot.

---
*Status: research plan. Numbers marked `[TODO]` require computation from run v0.14.0.*
