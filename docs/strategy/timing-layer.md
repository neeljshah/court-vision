# Timing Layer — When to Bet Throughout the Day

*Event timeline from 6am to post-game — when to capture each edge.*

---

## Core Insight

Most bettors think about WHAT to bet. Systematic bettors think about WHEN.

The same model prediction has different expected CLV depending on when the bet is placed relative to line movements. Bets placed at opening (6am) capture maximum CLV because lines haven't been corrected by sharp money. Bets placed in the final hour before tip-off capture lines that have already been moved against you.

Research finding: bets placed 24+ hours pre-game average +1.2% CLV; final-hour bets average −0.5%. The difference compounds significantly over volume.

---

## The Daily Event Timeline

| Time (ET) | Event | Model Action | Edge Opportunity |
|-----------|-------|-------------|-----------------|
| ~6am | Props first posted | Poll Odds API; run line evaluator against current model | **Maximum opening CLV window** — lines have maximum error |
| ~9am | Referee assignments posted | Scrape ref assignments; re-run models with ref features | Ref foul/pace effects; FTA props in particular |
| 1pm | Mandatory injury report | Poll official report + RotoWire; update lineup models | Teammate redistribution window (5–15 min of stale lines) |
| 5pm | Final injury report | Same as 1pm; higher stakes for evening slate | Critical — last official information before tip |
| ~30–60 min pre-game | Starting lineup confirmed | Final distribution recalculation; late scratch detection | Last pricing opportunity; most volume-concentrated |
| Any time | Line movement alert (> 0.5 pts) | Steam detection trigger; evaluate residual at lagging books | Steam chasing — 60-second window |
| Any time | Injury news from reporters | Often faster than official report | Monitor X/Twitter for credible beat reporters |
| Post-game | Results come in | Collect residuals; compute CLV; update calibration | Nightly improvement loop |

---

## Opening Line Capture (6am)

**Why this is the highest-priority timing improvement:**

Props are posted 12–24 hours before tip, often at 6am ET. Opening lines are set by the book's automated model with no sharp correction. Sharp money accumulates throughout the morning, correcting pricing errors. By tip-off, most errors have been corrected. Bets at open capture the error before correction.

**Implementation (Phase 3 priority):**
```python
# 6am ET cron job
@scheduler.scheduled_job('cron', hour=6, minute=0, timezone='US/Eastern')
async def morning_sweep():
    lines = await odds_api.fetch_current_props(sport='basketball_nba')
    for market in lines:
        edge = compute_edge(model_prob=get_model_prob(market), 
                           book_prob=shin_devig(market.odds))
        if edge > EDGE_THRESHOLD:
            bet_queue.add(market, edge)
    await alert_if_high_edge_opportunities(bet_queue)
```

---

## Referee Assignment Update (9am)

**Why this fires consistently:**

NBA ref assignments are posted ~9am ET. Player prop lines are posted ~6am. The 3-hour gap means lines were set without referee context. Refs with historically high foul rates increase FTA props; refs with low foul rates suppress them. Refs with high pace impact push counting stat totals.

**Required data:**
- Daily ref assignment: `official.nba.com/referee-assignments` (scraped at 9am)
- Historical ref stats: NBAstuffer, Basketball-Reference (loaded once, updated monthly)

**Features added to model at 9am:**
- `ref_foul_rate_home_bias`: historical tendency to call more fouls on home or away team
- `ref_pace_factor`: ref-specific pace effect relative to league average
- `ref_fta_rate`: free throw attempts per possession under this ref
- `ref_star_player_foul_adjustment`: documented tendency for calls on max-contract players

**Automatic re-evaluation:** After ref data is injected, re-run line evaluator on all FTA-sensitive props (pts via FTA, FTA directional markets if available). Any newly-appearing +EV opportunities get queued.

---

## Injury Report Windows (1pm and 5pm)

**Why these are critical:**

NBA rules require teams to file injury status by 1pm ET and 5pm ET on game days. When a key player is updated from "probable" to "out," every teammate's prop is potentially mispriced. Books manually recalculate affected lines over 5–15 minutes.

**The window:** Your model recomputes all affected distributions in seconds via the usage redistribution model. During the 5–15 minutes while books manually update, you have line-shopping access to stale prices.

**How many times does this fire per week?**
During an NBA regular season (October–April): typically 3–5 meaningful injury updates per week. High-impact scratches (starter ruled out) occur 1–2 times per week on average.

**Implementation:**
```python
# 1pm and 5pm ET monitoring
async def process_injury_report():
    report = await scrape_official_injury_report()
    changes = detect_status_changes(report, prior_report)
    
    for change in changes:
        if change.is_significant:  # starter, key rotation player
            affected = compute_affected_players(change.player_id)
            for player in affected:
                new_dist = redistribute_usage(player, change)
                for line in current_open_lines[player]:
                    edge = compute_edge(new_dist, line)
                    if edge > EDGE_THRESHOLD:
                        bet_queue.add_urgent(player, line, edge)
```

---

## Late Scratch Detection (30–60 min pre-game)

**Higher stakes than scheduled injury reports:**

Late scratches are unscheduled. A player listed as "available" at the 5pm report who is scratched at 6:30pm for an evening game is the highest-value timing event. Every teammate's prop is stale; every opponent's defensive assignment changes.

**Monitor sources:**
1. RotoWire push notifications (most reliable single source)
2. ESPN injury feed
3. Official team accounts on X
4. Beat reporters for each team (assembled list of high-credibility accounts)

**Latency target:** Detect within 60 seconds of public announcement; complete distribution recalculation within 90 seconds; queue any resulting +EV bets within 120 seconds.

This window matters because books are slower than the information market. Sharp bettors hit immediately; book adjustments follow over 5–15 minutes. The residual opportunity at slower-adjusting books is real.

---

## Steam Detection (Any Time)

**What it is:** Coordinated sharp account action at multiple books simultaneously, detectable as rapid directional movement (3+ books moving same direction within 60 seconds, magnitude > 0.5 points).

**How to detect:**
- Poll all book feeds every 30–60 seconds
- Compute rolling line velocity per market (points moved per minute)
- Flag: if velocity > 3 SD from historical mean AND direction is consistent across 3+ books → steam signal

**How to trade it:**
- Note the direction sharp money moved
- Check whether your model agrees (if model agrees: strong bet; if model disagrees: stand aside)
- Bet in the steam direction at books that haven't yet adjusted
- The window is typically 60–180 seconds before all books have adjusted

---

## The Nightly Close (Post-Game)

Not a betting opportunity — the maintenance window:
1. Collect all settled bet outcomes
2. Compute CLV for each: `devig(model_prob) - devig(closing_line_prob)`
3. Update rolling CLV metrics (7/30/90-day windows)
4. Add residuals to calibration dataset
5. Run calibration update if new residuals > threshold
6. Log account health metrics per book
7. Flag any anomalies for morning review

The nightly close is how the system gets better over time. See [learning-loop.md](learning-loop.md).

---

## Priority Ordering

If only one timing improvement can be built first:

**Phase 3 (automate):** Opening line capture at 6am. This is where the most CLV is left on the table by manual operation.

**Phase 4 (automate):** Injury report processing at 1pm and 5pm. This fires reliably several times per week and has the largest per-event CLV opportunity.

**Phase 5 (automate):** Late scratch detection. Highest per-event value but lower frequency and harder to automate (requires natural language parsing of tweet/report content to confirm severity).

---

*See [execution-engine.md](../architecture/execution-engine.md) for how timed bets are routed. See [learning-loop.md](learning-loop.md) for the nightly improvement cycle.*
