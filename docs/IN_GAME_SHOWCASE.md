# In-Game & Pregame -- what's actually strong (and how I know)

> Honest framing up front: against **closing** betting lines the market is
> efficient -- so I treat this as **model accuracy and validation rigor**, not a
> betting edge. Where a real edge exists, it's stated precisely. The full honest
> accounting is in [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

## In-game is the model's strongest signal -- as *accuracy*

Observed mid-game state (a starter yanked in a blowout, a player in foul
trouble, an ejection) is information a pregame model structurally cannot see.
Graded leak-free against real in-play lines, the in-game model's rest-of-game
projection is **closer to the final box than the live market line ~66% of the
time on assists and ~64% on FG3M** -- and that discrimination holds
**independent of bet cadence**, so it's a property of the model, not a
staleness artifact.

This is validated the hard way: walk-forward fitting on hundreds of thousands
of held-out snapshots, **truncation-invariance** unit tests (a feature at time
*T* is byte-identical with or without future events), and **two independent
adversarial skeptics** attacking every "improves" verdict. Most candidate
signals were correctly **rejected** -- and the one attribution-clean,
both-skeptics-confirmed signal (live "hot-hand" shading) is a deliberately
modest **+1-2%**, reported as a shading, not a windfall.

> Honest limit: the real-money in-play **ROI** is *unresolved, not proven* --
> the graded live-line corpus is small. I report in-game as an **accuracy**
> result and am growing the corpus before making any profit claim.

## Pregame -- one durable edge, and an efficient market

Against real DK/FanDuel/MGM **closing** lines, the production prop model is
**roughly break-even-minus-vig** overall. The one stat with a **durable,
book-robust, cross-season** edge is **assists (~+4-5% ROI, regular season)** --
verified to be genuine selection skill (positive in both over/under directions,
beats a blind baseline, survives on an independently-sourced book) and honestly
bounded (it **breaks in the playoffs**; the higher in-window figures are
regime-inflated peaks). Calibrating the other stats moves them *toward* the
line -- which is why "calibrate everything" converges to break-even, and why I
don't claim a broad edge.

## The methodology is the point

Walk-forward CV with per-fold leakage assertions / truncation-invariance
streaming tests / a multi-corpus calibration acceptance gate / shadow-logging
of passed *and* blocked bets / two-skeptic adversarial grading. These harnesses
caught my own flagship "+18% ROI" as a market-follow measurement artifact and a
Q4 data leak in my own metrics -- and I documented the honest numbers.
**Telling a real result from an artifact is the actual deliverable.**
