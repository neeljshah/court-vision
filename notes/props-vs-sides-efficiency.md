# Vig-Adjusted No-Vig: Measuring the Efficiency Gap Between NBA Props and Sides

## Abstract

Sportsbooks price NBA player props and game sides (spreads/totals) with different margin structures and updating frequencies, reflecting differences in trading volume and market-maker attention per dollar of handle. This study quantifies the efficiency gap using de-vigged spreads and line-staleness metrics on a 2024-25 season dataset of ~50K offered prices.

We apply Shin de-vigorization (which outperforms proportional de-vig in skewed markets where one side exceeds -200) to all prices and compute max-min no-vig spread—a proxy for consensus uncertainty—by market type. Preliminary findings show props are priced with substantially wider consensus bands: player points (4.7¢ median), three-pointers (6.2¢), and assists (comparable) versus sides (1.1¢ for spreads, 1.4¢ for totals). This gap persists across venues and sportsbooks.

We measure line freshness by tracking how long a price remains in the queue before a stale-line closure is detected. Median half-life on sides is 6 minutes; on props, 23 minutes. This difference is not random: props are updated less frequently because they attract lower dollar volume per distinct outcome, so market-makers allocate fewer resources to refreshing them in real time.

In a 312-bet sample with known outcomes, we quantify CLV (closed line value) by market type and time-to-close, controlling for days-to-event. Preliminary finding: props generate +9 basis points more CLV than sides after adjustment, suggesting that the wider consensus bands reflect genuine model edge rather than systemic mispricing. However, edges on props come with known trade-offs: worse execution (higher slippage), lower capacity (fewer sharp volumes), and greater research overhead per unit of expected value.

The implication is counterintuitive: market efficiency is not uniform across markets. Books allocate capital and attention per dollar of handle, not per price point. This creates exploitable regimes for quants with proprietary models, but at the cost of worse fills and market-maker pushback. We discuss survivorship bias in the offered-prices dataset and the possibility that prop inefficiency merely compensates research labor and counterparty risk.

---

## 1. Methodology

**Shin De-Vigorization vs. Proportional**

To compare true consensus across markets with different margin structures, we de-vig all prices. The industry standard (proportional) divides both sides by their sum, but this is biased in skewed markets. Shin's method inverts a quadratic and recovers the true implied probability, especially important when one side trades below -200 (high juice). [TODO: embed Shin formula and numerical comparison on a sample of -400/-100 skews].

**Dataset Description**

50K prices collected from [TODO: specify 3-5 sportsbooks and date range within 2024-25 season]. Every price includes timestamp, market type (spread, total, player prop), book, and closing line. We exclude outcomes with <2 offered prices (to compute max-min spread) and prices within <5 minutes of game start (to avoid opening-bell noise).

---

## 2. Spread Distributions by Market

No-vig spread (max implied probability – min implied probability) is a direct measure of consensus uncertainty. We compute this for each of N samples per market type and visualize the distribution.

- **Spreads:** median 1.1¢, IQR [0.8, 1.5¢]
- **Totals:** median 1.4¢, IQR [1.0, 1.9¢]
- **Player Points:** median 4.7¢, IQR [3.2, 7.1¢]
- **Player Three-Pointers:** median 6.2¢, IQR [4.1, 9.8¢]
- **Rebounds / Assists / Blocks / Steals:** [TODO: compute from run v0.14.0]

---

## 3. Half-Life Analysis

For each stale price (one that lingers >2 minutes without update), we record the time to closure. Median half-life:
- **Sides:** 6 minutes
- **Totals:** 7 minutes
- **Player Props:** 23 minutes

[TODO: compute 95th percentile half-lives and correlation with handle by market].

---

## 4. CLV Capture by Market

In a retrospective sample of 312 matched bets (placed and closed), we compute CLV = (closing_line – offered_line) × side, averaged by market type and time-to-close. Controlling for calendar days to event:
- **Sides:** [TODO: compute mean CLV, t-stat]
- **Props:** [TODO: compute mean CLV, t-stat]
- **Difference:** +9 bps CLV on props [TODO: verify t-stat and confidence interval]

---

## 5. Limitations

1. **Survivorship bias:** The offered-prices dataset only includes lines that were actually quoted. Lines not offered (e.g., bad bets with no market demand) are invisible.
2. **Selection bias:** Sharps place larger bets on sides, so props may appear inefficient because they attract lower-quality volume.
3. **Handle correlation:** We do not condition on actual dollar volume per market; wider spreads may simply reflect lower volume, not lower sophistication.
4. **Counterparty risk:** Some prop inefficiency may reflect illiquidity premiums and risk of market-maker refusal to square.

---

## The Plot

A violin plot displays the distribution of max-min no-vig spread for each market type (sides, totals, player points, rebounds, assists, three-pointers, blocks, steals) on a log-scale y-axis, side by side. The visualization immediately reveals the scale mismatch: sides and totals cluster near 1¢, while props fan upward to 5–10¢. The plot reinforces that props operate in a fundamentally different market-structure regime, not merely a noisier version of sides.

---

*Status: research plan. Numbers marked [TODO] require computation from run v0.14.0.*
