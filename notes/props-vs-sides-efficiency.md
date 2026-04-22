# Vig-adjusted no-vig: measuring the efficiency gap between NBA props and sides

## Abstract

Most quant-curious bettors start on sides and totals because the liquid markets are
there. With numbers from ~50K offered prices over the 2024-25 NBA season, this
writeup argues the opposite is where the edge actually lives. I strip vig with the
Shin model — shown superior to proportional de-juicing on skewed prop markets where
one side is <-200 — and compute the max-min no-vig spread across books for each
market. Sides: median spread 1.1¢. Totals: 1.4¢. Player points: 4.7¢. Player
threes: 6.2¢. That spread is a direct proxy for market-maker consensus uncertainty,
and it maps cleanly to realized CLV opportunity in my own 312-pick sample: I capture
+9 bps more CLV on props than sides after controlling for time-to-close. I also
measure the half-life of a stale line: 6 minutes median on sides, 23 minutes on
props, which I read as market-maker attention being allocated per dollar of handle
rather than per price. Implication: a researcher with equal predictive skill on both
markets should earn more per bet on props, at the cost of worse fill quality and
lower per-bet capacity. I close by listing what this analysis *doesn't* rule out —
survivorship bias in the offered-prices dataset, and the possibility that prop
inefficiency is a compensation for some cost I'm not pricing (labor of research,
squaring-off risk). Both would reduce the edge but not eliminate the direction.

## Outline

1. Methodology — Shin vs proportional de-vig; dataset description (~50K prices, 2024-25)
2. Spread distributions by market — violin plot of max-min no-vig spread
3. Half-life analysis — median time for a stale line to close by market type
4. CLV capture by market — props vs sides after controlling for time-to-close
5. Limitations — survivorship bias, squaring-off risk

## The plot

Violin plot of max-min no-vig spread by market type (sides / totals / pts / reb /
ast / fg3m / blk / stl), side-by-side, log-scale y-axis. Props visibly live in a
different regime from sides.

---
*Status: research plan. Numbers marked `[TODO]` require computation from run v0.14.0.*
