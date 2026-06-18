# Competitor Teardown -- Sports-Betting Decision-Support Tools

Research date: 2026-06-17. ASCII-only. Decision-support framing (line shopping,
+EV, arbitrage, middling, model predictions, CLV) where the human places bets
manually. Goal: extract every feature detail from the best products so we can
build to that bar.

Products covered: OddsJam, Outlier Bets, Unabated, Action Network, OddsPortal,
RebelBetting, BetBurger, Crazy Ninja Odds, DarkHorse Odds, Pinnacle (anchor book),
Props.Cash, Sharp App, Betstamp, Juice Reel.

Sources are cited inline as bare URLs. Where review sites disagree, the
discrepancy is flagged. Numbers that could not be confirmed on a primary page are
labelled as review-sourced.

---

## 0. The category at a glance

The 14 products split into five archetypes. Knowing which archetype each one is
prevents apples-to-oranges comparison:

1. **All-in-one sharp tools** (the bar to beat): OddsJam, Outlier, Betstamp PRO,
   Sharp App. Devig + +EV + arb + middling + tracker + props + alerts.
2. **Sharp odds screen, pro-grade, desktop**: Unabated. The "Unabated Line" fair
   value, in-game pricing, latency-dot UX. No tracker auto-sync, no app.
3. **Value/arb scanners (EU/global heritage)**: RebelBetting, BetBurger. Sharp-book
   devig -> value bets + surebets + middles, deep offshore book coverage.
4. **Devig calculator suites (power-user, cheap)**: Crazy Ninja Odds, DarkHorse
   Odds. The deepest devig menus in the market, promo conversion, low cost.
5. **Content / odds-comparison / tracker-first**: Action Network (content + bet
   tracker + sharp money), OddsPortal (EU odds comparison + historical archive),
   Betstamp tracker, Juice Reel (tracker + verified picks marketplace),
   Props.Cash + Sharp App (player-prop research).

**Pinnacle** is not a tool -- it is the reference sportsbook every +EV tool devigs
to derive fair value (low margin, high limits, does not limit winners).

---

## 1. OddsJam

**Core value prop.** Real-time odds comparison + sharp-betting analytics across
100-150+ books/DFS apps, surfacing +EV, arbitrage, middles, low-holds, promo
conversions, with a bet tracker + CLV. Markets itself on speed ("over 1,000,000
odds per second"). 100k+ users, 4.7/5 iOS (2.2k ratings). In 2025 OpticOdds/OddsJam
was reported acquired by Gambling.com Group.
(https://oddsjam.com/, https://dev.oddsjam.com/odds-screen,
https://stocktitan.net/news/GAMB/gambling-com-group-...-acquire-odds-i0dx42o2e5yk.html)

**+EV / fair value & devig.** Strips vig from sharp books to get no-vig fair odds,
compares soft prices against it. Default "Recommended Filters" requires +EV vs a
*consensus of multiple sharp books*, ML-weighted by "historical sharpness"
backtesting. Sharp anchors: Pinnacle (primary), Circa, BookMaker; user can pick a
single source-of-truth book or consensus. **5 devig methods:** Multiplicative,
Additive, Power, Shin, plus **Worst-Case** (lowest implied prob across methods).
Per-bet "Market Width" (vig) shown as a confidence cue.
(https://oddsjam.com/betting-education/how-do-positive-ev-sports-betting-filters-work,
https://oddsjam.com/betting-education/uncovering-true-outcome-probabilities,
https://oddsjam.com/betting-education/market-width)

**Arbitrage.** Scans 30+ (Gold) to 150+ (Platinum) books; sorts by ROI/profit %;
auto stake sizing per leg; one-click deep-link placement to both books.
(https://oddsjam.com/betting-education/arbitrage)

**Middling.** Two-sided line gaps where both bets can win (e.g. Over 51.5 +104 /
Under 52.5 +101). (https://oddsjam.com/betting-tools/middles)

**Low-hold / hedging.** Dedicated Low Hold screen for near-break-even two-sided
pricing (rollover/playthrough clearing).
(https://www.promoguy.us/sports-betting/guide/oddsjam-review/)

**Odds-screen UX.** "Fastest odds screen in the world": side-by-side per game across
all books; one screen toggles main markets / alternate markets / player props;
inline injury status, live scores, play-by-play, venue, weather; custom weighted
consensus lines with move alerts; click-to-bet deep link with pre-populated slip.
(https://dev.oddsjam.com/odds-screen)

**Books.** 100+ marketing / 150+ app / ~300 in data-feed materials. Gold ~40 US;
Platinum/Global 150+ incl. offshore. Includes DraftKings, FanDuel, BetMGM, Caesars,
sharps (Pinnacle/Circa/BookMaker), DFS (PrizePicks, Underdog). Tracks Kalshi/
Polymarket prediction markets.
(https://apps.apple.com/us/app/oddsjam-sharp-sports-betting/id6448072108)

**Sports & markets.** NFL/NBA/MLB/NHL/CFB/CBB/Soccer/Golf+. ML/spread/total, alt
lines, player props, **live in-game (Platinum-only, "2x more profitable")**, prop
trends over 5/10/20-game windows.

**Tracker & CLV.** One-click add from any tool -> auto-grades W/L/refund.
Sportsbook sync supported (exact mechanism not publicly documented). **CLV auto-
tracked vs sharpest book**: % of bets beating close, CLV by book, CLV alerts. P&L,
ROI, most-profitable book/sport breakdowns; separate deposits/withdrawals tracker.
(https://oddsjam.com/bet-tracker, https://oddsjam.com/betting-education/closing-line-value)

**Alerts.** Real-time +EV / arb / middle / line-move / CLV via mobile push, email,
Slack + Microsoft Teams. No documented native Discord/SMS.
(https://www.betsmart.co/tool-reviews/oddsjam)

**Filters & sorting.** Books include/exclude, EV%/profit threshold, min/max odds,
sport/league, market type, date window, **devig method + source-of-truth book
toggle**, save presets, "Recommended Filters" conservative preset. Sort by EV%/ROI.

**Parlay / SGP.** SGP calculator previews payouts, compares SGP pricing across
books, **correlation analysis** flags correlated legs and the "correlation tax."
(https://oddsjam.com/betting-education/same-game-parlay)

**Promo.** Promo Converter finds best hedge to turn bonus/free bets into cash,
sorted by conversion % (~80c/$ typical, 95-98% best). Free standalone calc.
(https://oddsjam.com/betting-tools/promo-converter)

**Refresh.** "Over 1,000,000 odds/sec"; Platinum adds Auto-Refresh; real-time live
odds. No fixed interval published.

**Mobile vs web.** Full web + native iOS (4.7/5). **No Android app** (uses web).

**Pricing (iOS listing, authoritative).** 7-day trial (card req); no permanent free
tier (calculators free). Trends $19.99/mo; Fantasy $59.99/mo; Sharp Money
$199.99/mo; **Gold $199.99/mo** (~40 US books, no live/auto-refresh); Global
$399.99/mo; **Platinum $499.99/mo** (150+ books, live, auto-refresh, line charts,
1:1 coaching). Annual ~20% off. Review sites cite conflicting figures.

**Standout UX.** One-click deep link + auto stake sizing; Auto-Refresh + live +EV
(Platinum); user-selectable devig source + 5 methods; auto-graded tracker w/ auto
CLV; inline injury/score/PBP/weather; free 1:1 coaching; DFS optimizer for
PrizePicks/Underdog.

---

## 2. Outlier Bets (outlier.bet)

**Core value prop.** Mobile-first all-in-one research/decision tool: player-prop
analytics, game lines, line movement, +EV, arb, middling, boost analysis, injuries,
direct bet-slip placement. 4.9/5 across 16,000+ iOS ratings.
(https://outlier.bet/, https://apps.apple.com/us/app/outlier-smart-sports-betting/id6443885102)

**+EV / fair value & devig (best-in-class breadth).** Compares each line to no-vig
true prob; +EV gets a badge. **8 devig methods:** Multiplicative, Additive, Power,
Implied Probability Power (IPP), Shin, **Probit**, **Worst Case**, **Average**.
**Default = Average.** **Multi-book devig with custom weights (Pro):** pick multiple
sharp books, set Required vs Optional, weight unsharp books to zero. **Radar/spider
viz** shows how EV shifts across devig settings. Concrete EV presets ship with
specific Pinnacle/Circa/BookMaker anchors + EV%, width, Kelly, variation thresholds.
(https://help.outlier.bet/en/articles/8208129-how-to-devig-odds-comparing-the-methods,
https://help.outlier.bet/en/articles/10714084-multi-book-devig-custom-weighting...,
https://help.outlier.bet/en/articles/11908672-...-positive-ev-filter-presets...)

**Arbitrage / Middling.** Both Pro-only; arb computes exact stakes per book;
middling computes P/L across O/U outcomes.
(https://help.outlier.bet/en/articles/12556823-choosing-the-right-outlier-plan...)

**Low-hold / bonus conversion.** No dedicated calculator -- a gap.

**Odds-screen UX.** Games tab (matchups); **Prop Finder** (filter by league/team/
player/prop type/min odds; each prop shows L5/L10/season hit-rate); Market Detail
(historic stats, matchup, injuries, line movement, public %). My Picks shows book +
odds; **"Add All Bets to Betslip"** = two-click deep-link checkout; **Tail Links**
social sharing. Pro feed adds Market Width + Variation columns.
(https://help.outlier.bet/en/articles/6676022-find-your-next-bet-outlier-quick-start-guide)

**Books.** ~15+. Deep-link: FanDuel, DraftKings, Caesars, BetMGM, Hard Rock,
bet365, ESPN Bet. Devig/sharp: Pinnacle, BetUS, BetOnline, SuperBook, MyBookie,
BookMaker, Circa. DFS/prediction: Underdog, PrizePicks, **Kalshi, Fliff**.

**Sports & markets.** NFL/NBA/WNBA/MLB/NHL/NCAAF/CBB/soccer. ML/spread/total,
**player props (core strength)**, SGPs, odds boosts. **Alt lines and live in-game
NOT explicitly documented -- gap; product is pregame-research-framed.**

**Tracker & CLV.** Major gap: no documented bet-history tracker, ROI dashboard, CLV,
or screenshot import. Markets "no screenshotting" via deep links instead.

**Alerts.** Real-time custom alerts (+EV, line move, player perf), price-target
alerts, Outlier Discord with real-time alerts. In-app push primary; no SMS/email.

**Filters & sorting.** Book, devig method, sport, EV threshold, fair-value odds
range, market width cap, Kelly multiplier, variation %, vig %, date. Prop Finder by
league/team/player/prop type/min odds.

**Parlay / SGP.** SGP supported + deep-linked; **Boosted parlay highlights** +
**Boost Index** (scores if a boost is +EV). No SGP correlation engine -- gap.

**Promo.** Boosts tab aggregates boosts across books + Boost Index (value scoring).
No dedicated bonus-bet-conversion calculator -- gap.

**Refresh.** "Real-time"; 2026 EV Feed Refresh for Pro. No latency published.

**Mobile vs web.** iOS-first (4.9/5, 16k ratings). No native Android (uses web).

**Pricing.** 7-day trial. **Premium $19.99/mo ($199.99/yr)**; **Premium+ $29.99/mo
($299.99/yr)** adds +EV badge + boost index; **Pro $79.99/mo ($359.99/yr ~62% off)**
adds full +EV custom-filter feed, multi-book devig weighting, boosted-parlay
highlights, middling, arb feed w/ stakes.

**Standout UX.** Two-click checkout w/ pre-filled deep links; radar/spider EV viz;
custom multi-book devig weighting; inline L5/L10/season prop hit-rate badges; Tail
Links; Kalshi+Fliff; Boost Index.

---

## 3. Unabated

**Core value prop.** Desktop-first premium sharp tool by pros (Captain Jack Andrews,
Rufus Peabody). Fast multi-book odds screen whose differentiator is the proprietary
**Unabated Line** -- a vig-free fair-value blend of the sharpest market-makers,
weighted per sport/market -- against which every price is compared to surface "Edge."
Explicitly "advanced/expert," not beginner.
(https://unabated.com/articles/what-is-the-unabated-line)

**+EV ("Edge") methodology.** No-vig fair-odds blend of sharpest market makers per
sport; Edge = best book line vs Unabated Line; +EV lights green. **Weights chosen by
which books reach the closing line fastest/most accurately, and differ by sport AND
market type** (the key differentiator). Pinnacle-anchored consensus; no-vig calc now
shows historical accuracy of each Pinnacle-based consensus line. **Devig is
deliberately proprietary -- no user-facing method toggle** (unlike OddsJam/Outlier).
Standalone no-vig calculator de-vigs both sides but offers no method choice.
(https://unabated.com/articles/finding-positive-ev-wagers-step-by-step-guide,
https://unabated.com/betting-calculators/no-vig-fair-odds-calculator)

**Arbitrage.** None -- philosophically opposed ("the arbitrage mirage"); advises
betting only the +EV side. A negative synthetic-hold column passively surfaces arb/
low-hold situations.
(https://unabated.com/articles/arbitrage-betting-risk-free-riches-or-a-mirage)

**Middling.** No standalone finder; priced via Derivatives/Alt-Line + Partial-Game
calculators.

**Low-hold / hedging.** **Synthetic Hold column** auto-computes hold per market;
negative hold (bettor advantage) highlighted green. Dedicated Hold + Hedge
calculators. Premium adds derivatives/hedging/CLV/vig-removal/alt-line calcs.

**Odds-screen UX (signature).** Pulls from dozens of books + exchanges, near-real-
time. **Latency dot per book** (freshness cue). Color coding: negative hold = green,
moved line flashes yellow. Unabated Line column (Premium) inline. Market-scope
toggle: full-game/half/quarter/in-game. Separate dedicated **Props, In-Game, and
live futures odds screens (30+ books)**. **Click-to-bet deep links NOT documented --
likely gap vs OddsJam.**
(https://unabated.com/articles/learn-about-the-game-odds-screen)

**Books.** "25+"/"dozens": DraftKings, FanDuel, BetMGM, Caesars, Fanatics, ESPN Bet,
bet365; **P2P exchanges ProphetX + Novig**; Fliff + Underdog; Kalshi.

**Sports & markets.** NFL/NBA/WNBA/MLB/NHL/CFB/CBB/Tennis(ATP)/Golf(PGA)/CFL. **No
soccer, no UFC/MMA.** Spreads/totals/ML, alt lines, partial-game derivatives (MLB
F5/first-inning, halves, quarters), futures, props, live/in-game. MLB props expanded
to K totals + first-inning across 20+ books.

**Tracker & CLV.** **No auto-sync tracker (no account linking) -- calculator-only,
manual entry.** CLV via dedicated calculator (enter bet + closing/Unabated Line).
CLV tracking/logging is Premium. Reviews flag lack of auto-sync as its weakness.
(https://unabated.com/betting-calculators/closing-line-value-calculator)

**Alerts.** Browser alerts core ("Rusher alerts" on line changes/new edges). Discord
free + Premium/Concierge private channels (discussion, not automated feeds). **No
native SMS/email/push.**
(https://unabated.com/articles/introducing-edge-rusher)

**Filters & sorting (Edge Rusher).** Leagues, books, **freshness (max edge age /
freshest plays)**, edge threshold/price boundaries, **"Exclude Line Changed First"
toggle** (suppresses false positives where book moved before Unabated Line). New
edges fade light->dark blue; changes yellow; hour-by-hour edge-frequency report. **No
user-facing devig-method toggle.**

**Parlay / SGP.** Parlay Builder/betslip + **teaser tools/"teaser shopper"**
(Premium). No dedicated SGP-correlation EV engine -- likely gap.

**Promo.** No bonus-conversion calculator documented.

**Refresh (emphasized).** **WebSocket push (no polling)** for pregame/live/props from
25+ books. In-game integrates **DeckPrism Sports** ("sharpest in-game market maker")
+ **Sports411** (~30-60s faster than TV); "a delay of even 20 seconds is too slow."
Per-book latency dot = live freshness readout. Public WebSocket Odds API sold
separately. (https://unabated.com/articles/using-the-unabated-in-game-betting-tool)

**Mobile vs web.** **Web/desktop only. No iOS or Android app.**

**Pricing (cross-source variance).** Essentials ~$67/mo; Props+ $99/mo; **Premium
$199/mo** (unlimited +EV, props deep-dive, in-game live pricing, CLV tracking/
logging, alt-line calc, sport simulators); **Concierge $799/mo** (requires Premium;
Edge Rusher, Prop Rusher, private Discord). Add-ons (one review): Edge Rusher
$250/wk, CFL $399/season, CFB $499/season, WNBA $199/mo. ~5-day trial; no perpetual
free tier.

**Standout UX.** Per-book latency dot; custom projection upload + FantasyPros/
numberFire integration; **props simulator (10,000 Poisson sims/player** w/ cumulative
graph); **NFL/season simulators (10,000 Monte Carlo Massey-Peabody** -> win totals +
playoff/SB matrix); in-game pricing engine (worked +9.3% / +4.91% live edges);
public WebSocket Odds API.

---

## 4. Action Network

**Core value prop.** "ESPN for sports betting": content + bet tracking + sharp-money
intelligence -- NOT a quant scanner. Free best-line odds comparison, auto bet
tracking (BetSync) with a "My Action" analytics dashboard, and a paid intelligence
layer (public bet%/money% splits, sharp action, model projections). 350M+ bets
tracked; iOS/Android/web.
(https://www.actionnetwork.com/app)

**+EV / fair value.** NOT a true +EV/devig tool -- no no-vig fair-odds across the
market and no devig method. What they have is **PRO/Model Projections "Edge"**:
proprietary power ratings produce a projected "true line" per game/prop; Edge =
(model line - book line) %, shown as an **A-F letter grade**; recommended threshold
"Grade B or +3.5%", PRO Report projection icon fires at **>=5%** model-vs-market gap.
This is projection-vs-line, weaker than devigged-fair-price-vs-soft-book. Action Labs
"Edge View" normalizes prop lines vs a vig-free "True Line."
(https://www.actionnetwork.com/projections, https://labs.actionnetwork.com/props-new)

**Arbitrage / Middling.** None (educational only). Manual Hedging Calculator.

**Odds-screen UX.** Per-game grid: Spread (w/ juice), ML, Total + dedicated "Best
Odds" column; **best line highlighted green**. **Click-to-bet via "QuickSlip"** deep
links to FanDuel/DraftKings/BetMGM/Caesars/bet365. **Line Move Alerts** (set target
price) PRO-only.
(https://www.actionnetwork.com/nfl/odds)

**Books.** US-focused: ~8 on grid (bet365, Fanatics, Kalshi, FanDuel, DraftKings,
BetMGM, Caesars, BetRivers), state-filtered. Props compare "more than a dozen";
Action Labs 40-60+. Underlying Sports Insights engine tracks 50+ incl. offshore.

**Sports & markets.** NFL/NBA/MLB/NHL/soccer/golf/college/WNBA/tennis/NASCAR/UFC.
Spread/ML/Total, props, alt lines, parlays, futures, DFS, live odds. NBA prop tabs:
Pts/Reb/Ast/3pt/Stat Combos + Alt versions.

**Tracker & CLV (flagship moat).** **BetSync** (auto sync via account linking --
BetMGM + bet365 first-party, free) + **BetScan** (screenshot-to-betslip parsing) +
manual + DFS tracking. "My Action": W/L, ROI, units, avg odds, breakdowns by sport/
league/bet type, live play-by-play win prob. **CLV native and automatic** -- "Closing
Line Value Breakdown" showing Total Value Saved + % beating close; all bets count.
(https://www.actionnetwork.com/betsync,
https://www.actionnetwork.com/general/...-revamped-my-action-tab-clv-breakdown-more)

**Alerts.** Line Move Alerts (PRO), Sharp/Big Money/Steam signal alerts (PRO),
instant expert-pick push (PRO), in-game play-by-play. Free = basic pick/game alerts.

**Filters & sorting.** Odds by bet type, timeframe (full/1H/1Q/period), state, books;
props by league/market + player search; Action Labs sortable by edge vs True Line.

**Parlay / SGP.** Gap: no SGP correlation engine, no parlay EV-grader. Free Parlay
Calculator assumes independent legs. Free "Playbook AI" bot turns a tagged pick into
a preloaded betslip.

**Promo.** Odds Boosts page filters by sport/state/operator but does NOT rank by EV.
No automated boost-EV ranker, no bonus-conversion calc.

**Refresh.** Officially "real-time," but reviewers flag lag in fast markets.

**Mobile vs web.** iOS + Android + web; mobile is the primary surface; cross-device
sync is a PRO unlock.

**Pricing (web, confirmed).** Action PRO: **$14.99/wk, $24.99/mo, $49.99/3mo,
$99.99/yr**. No standing free trial. iOS in-app higher. Action LABS sold separately
(price uncertain). FantasyLabs separate.

**Standout UX.** PRO Report with 5 signal icons (Sharp Action, Big Money, PRO Systems
back-tested since 2003, Model Projections >=5%, Top Experts). Public betting shows
**% of Bets vs % of Money + a "Diff" column** flagging sharp/recreational divergence.
Sports Insights taxonomy: Reverse Line Movement, Steam Moves, Line Freeze,
Contrarian. Action Labs: 60+-book board vs True Line + build-your-own historical
Systems.

---

## 5. OddsPortal

**Core value prop.** Free, registration-optional odds-comparison + historical-odds
aggregator (not a quant tool). Line-shops pre-match + in-play across many bookmakers,
maintains a deep historical archive (decade-plus) of opening-to-closing movement.
Light derived screens: Dropping Odds, Value Bets, Sure Bets, Blocked Odds. EU-centric,
dated UI, no app.

**+EV.** NOT a true sharp-anchored +EV/devig engine. "Value Bets" = one book vs field
average (heuristic), much weaker than a sharp devig.
(https://www.oddsportal.com/value-bets)

**Arbitrage / Sure Bets.** Dedicated Sure Bets page: arbs from cross-book divergence,
**Profit % column** + calculator icon for stake split. **Free tier shows top 10**;
more gated behind "Professional Sure Bets." Real surebet ROI ~1-3%. Standalone arb
calculator. (https://www.oddsportal.com/sure-bets)

**Middling.** None documented.

**Value betting.** Value Bets page: one book vs all-book average, value/overvalue % +
implied prob; football/tennis/basketball/NFL/NHL/cricket. Free + "Professional Value
Bets" upsell. Overlaps with simple line-shopping.

**Odds-screen UX (core).** Per-event grid expands to bookmaker x outcome (1/X/2),
**best price highlighted yellow**; average/highest odds shown; rows link out;
decimal/fractional/American; **Payout % (1 - margin)** per event. **Historical odds
(famous):** archive since 2009-06-18, opening-through-closing per book per market,
decade-plus for majors; **hover a price to reveal opening->close movement**, changed
cells flagged yellow. **Dropping Odds:** Drop % column, start vs current, flags
drops >~20%, filters by 1h/12h/24h, market, sport.
(https://www.oddsportal.com/dropping-odds)

**Books.** Official FAQ "~30 (varies by location)"; reviews 60-80 global incl.
exchanges. EU/global/offshore; **weak/no US coverage.**

**Sports & markets.** ~20-23 sports. 1X2, ML, O/U, Asian handicap, double chance,
DNB, BTTS, HT/FT, outrights. **Player props NOT a strength.** Live/in-play: yes.

**Tracker & CLV.** Light only -- "My Coupon" tracks placed bets with email result
notifications; **no CLV.**

**Alerts.** "OddsAlert" (set target price, email when a book reaches it), live-score
notifications, My Coupon settlement emails. No SMS/push (no app).

**Filters & sorting.** Country/league/sport/time; outcome odds sortable by highest;
Dropping Odds filters; personalization (favorite books/sports, market, odds format,
time zone, exchange commission %).

**Parlay tools.** None (no accumulator builder). Has bet/odds calc, odds converter,
arb calc.

**Refresh.** Pre-match every 15s auto; in-play few-second delay. Freshness stripe:
**green <10min, red 10-60min, black >1h.**

**Mobile vs web.** Web-first responsive; **no native app** (repeated criticism).

**Pricing.** Core FREE; registration unlocks personalization + OddsAlert + My Coupon.
Two paid upsell tiers ("Professional Sure Bets", "Professional Value Bets") -- prices
not public. Monetized via affiliate.

**Standout UX.** Yellow best-price + yellow-flag-on-change; Payout % per event;
hover-to-see opening->close (signature); archive since 2009; community predictions;
"Blocked Odds" screen; settable exchange commission.

---

## 6. RebelBetting

**Core value prop.** Oldest dedicated +EV/arbitrage toolset (since 2008). Scans 100+
books, surfaces soft-book mispricings vs "true odds" for value betting or guaranteed-
profit arbitrage. Analyzes ~1M odds every ~60s.
(https://rebelbetting.com/valuebetting)

**+EV / Value Betting (transparent math).** From the official manual: **"True odds"
= sharp odds incl. margin; "Fair odds" = sharp odds with margin removed via the
proportional margin algorithm; "Probability" = 1/fair odds.** **Devig =
proportional/multiplicative no-vig (NOT Shin, NOT power).** Sharp anchor = sharp
books, **Pinnacle named top sharp book** (Betfair/Smarkets exchanges also sharp); on
Starter you value-bet vs soft books only, sharp books/exchanges as references are
Pro. **Value %** = how much offered beats fair (fair 2.50, offered 2.75 -> ~10%).
**Default value filter min 3% max 20%; Starter caps at 3.5%, Pro uncaps.**
(https://rebelbetting.com/valuebetting/valuebetting-web-manual,
https://rebelbetting.com/faq/valuebetting-default-settings)

**Arbitrage / Sure Betting.** Auto-scans + auto stake calc; per-arb ~2-5%; 2-way and
3-way; recommends 5-10 accounts; Starter excludes arbs >3.5%, Pro uncaps. Variants:
regular, negative arbs, low holds, middles.

**Middling.** Yes, inside Sure Betting. Regular + negative middles; no Polish/inverted
middles.

**Value betting settings.** Value % 3/20 default; odds range default 1.40-2.90;
time-to-start default 48h; **Kelly sizing default fraction 30%, max stake ~1.5-2%
bankroll**; per-book commission/tax.

**Odds-screen UX.** Row shows value %, odds, market, time + Bet button opening
bookmaker in new tab (often homepage, not true deep link -- acknowledged imperfect).
Row actions: open, log to tracker, snooze, edit odds/stake, keyboard shortcuts. Pro
adds Auto-login/AutoSurf and automated placement on supported books.

**Books.** Marketed 100+ (~60 EU + 13+ US/CA). US: DraftKings, FanDuel, BetMGM,
Caesars, Bovada, BetOnline, bet365, Unibet, Everygame. Sharp/exchange/broker (Pro):
Pinnacle, Betfair, Smarkets, Betdaq, Matchbook; brokers BetInAsia, Sportmarket,
AsianConnect.

**Sports & markets.** 14 sports (soccer/tennis/basketball/baseball/NFL/NHL/rugby/AFL/
horse racing/esports/handball/MMA/boxing). **Player props NOT a focus. Pregame-
focused, weak live/in-play** (reviewers prefer BetBurger for live arbing).

**Tracker & CLV.** Built-in tracker: one-click logging, auto-settlement add-on,
manual settlement, tags, Reports (ROI/yield/EV, profit-over-time, by book/market/
sport); Pro adds CSV export + multi-currency. **CLV: yes** -- compares taken odds to
sharp books just before start, framed as the pro long-term metric.

**Alerts.** Real-time new-value/arb alerts; audio toggle; push cited. No clear native
Discord/Telegram.

**Filters & sorting.** Bookmaker, sport, market, value/EV %, min/max odds, time to
start; "hide low tier"; **saved filter groups: Starter 2, Pro 4.** Sort by highest
value/closest to start/most recent.

**Parlay tools.** None.

**Refresh.** ~1M odds every 60s.

**Mobile vs web.** Browser-based + optional desktop app + mobile-optimized/Mac. No
native app-store apps -- responsive web.

**Pricing (US, USD).** Free trial **14 days, no card, 50 bets/day**. **Value Betting:
Starter $99/mo or $69/mo yearly; Pro $209/mo or $139/mo yearly.** Sure Betting sold
separately (~EUR 49-129/mo). Value + Sure are separate subs. Profit Guarantee: no
profit month 1 -> another month free. Trustpilot 4.2/5.
(https://rebelbetting.com/pricing)

**Standout UX.** Transparent per-bet true-odds/fair-odds/probability breakdown + CLV
benchmark (unusually open). Safe/Surf browser (auto-clears cookies) + AutoLogin/
AutoSurf + Pro automated placement. Built-in gubbing-avoidance playbook.

---

## 7. BetBurger

**Core value prop.** Real-time arbitrage (surebet) + value-betting scanner across
hundreds of books; bundles **Surebets, Valuebets, Middles** across prematch AND live
in one sub. European/Asian/CIS-dominant, heavier structural arbitrage, fast live
scanning.
(https://www.betburger.com/, https://www.betburger.com/prices)

**+EV / Valuebets.** Flags where a display book's odds exceed a sharp/"TOP-bookmaker"
reference **with the margin removed** (method qualitative; no formal no-vig/Shin
label). Reference book user-selectable; cited anchors Pinnacle, Betfair, Sbobet,
Dafabet, 188bet (default William Hill + Bet365). **Default yield cap 20%; free trial
caps valuebets at 2%.**
(https://www.betburger.com/manual/functional-value-bets)

**Arbitrage / Surebets (core).** sum(1/odds)<1 test + stake allocation. Returns
5-15% advertised. **2-way, 3-way, multiway.** Prematch + live. Built-in surebet calc
(Round/Balanced/commission-adjusted), Decimal/American/Fractional/HK/Indonesian +
40+ currencies incl. crypto. (https://www.betburger.com/surebets)

**Middling.** Yes -- one of the three core feeds, bundled in Live tier.

**Odds-screen UX.** Rows show event, outcomes, books' odds, profit/yield %, age. Per-
row calculator (optionally separate window), renews instantly. **Click-to-betslip
deep links via browser extension** (account-restriction risk noted).

**Books.** Headline **600+ (incl. clones)**; ~400+ "right now"; granular ~76-94
prematch + clones, ~66-102 in-play + clones. Strong in Europe/CIS/LatAm/Africa/NA +
substantial Asian books. **US coverage weak vs OddsJam.**

**Sports & markets.** **40 sports + 27 esports** advertised (~27 actively scanned).
Prematch + live (live a strength). Asian handicaps + totals core; **player props
weaker than OddsJam.**

**Tracker & CLV.** **No bankroll/bet-tracker module and no CLV metric -- a genuine
gap.** Telegram bot offers light "deal tracking" notes; sort by ROI/yield not CLV.

**Alerts.** Official **Telegram bot** sends real-time Surebets + Valuebets matched to
filters. Browser extension for jump-to-betslip; no standalone desktop app.
(https://www.betburger.com/telegram-bot)

**Filters & sorting.** Deepest multifilter: sport, bookmaker, country, leagues
(include/exclude), outcome type (2/3-way), markets, odds ranges, yield/profit %, ROI,
**age (minutes prematch / seconds live = bet lifetime)**. **Multiple saved filter
"setups"/profiles**, switchable simultaneously.

**Scanner speed.** Among the fastest, esp. live: reviews cite **~3-second** results;
up to **1,800 surebets/valuebets per minute via API.**

**Mobile vs web.** Web app + Telegram bot + public JSON **API** (65+ bookies / 230+
with clones, 30+ sports, prematch+live, up to 30/request, 1,800/min). No native app.

**Pricing (official EUR; no USD).** Monthly: **Prematch EUR 79.99/mo; Live EUR
279.99/mo; Prematch+Live bundle EUR 319.99/mo** (each incl. Surebets+Valuebets+
Middles). Cheaper "Prematch Start" ~EUR 29.99 (~3-min delay). Day ladder: 1 day EUR
5.99 down to 360 days ~EUR 1.94/day. **Free version exists** (delayed, valuebets
capped 2%).

**Standout UX.** Category-leading live scan speed (~3s, 1,800/min API); saved
multifilter profiles; deep Asian/EU/CIS coverage + structural arbitrage; API
automation + Telegram bot; click-to-betslip deep links.

---

## 8. Crazy Ninja Odds (CrazyNinjaMike)

**Core value prop.** Web-based devig-first +EV and promo-optimization toolkit built
around the "CrazyNinjaMike Sportsbook Devigger." The power-user's calculator suite:
~25+ books, an unusually deep devig + consensus-weighting menu, +EV/arb/low-hold/
promo. Cheap, sharp, community-driven (support from $5/mo).
(https://crazyninjaodds.com/site/tools/positive-ev.aspx, https://whop.com/crazyninjaodds/)

**+EV / devig (deepest menu in the category).** Methods: **Multiplicative /
Normalization / Traditional**, **Additive**, **Power**, **Shin**. Layered with
consensus/weighting: **Liquidity-Weighted** (more weight to higher-limit books,
factors in how limits rise toward game time), **Unweighted Market Consensus**,
**Conservative / Worst-Case** (lowest implied prob among Multiplicative/Additive/
Power/Shin), **Weighted Average** (custom blend of 2-4 methods).
(https://crazyninjaodds.com/site/tools/positive-ev.aspx)

**Arbitrage / Middling.** Dedicated Arbs and Middles tools.
(https://crazyninjaodds.com/site/general/about.aspx)

**Low-hold / hedging.** Dedicated Low-Holds tool reports **ROI%** and a distinctive
**Value%** that accounts for capital tied up (recognizes a hedge is "better" when a
promo requires a large spend); plus Hedge calc, Combo Breaker, up-by-X promo
simulator, pinch-hit risk, Monte Carlo calcs.
(https://crazyninjaodds.com/site/tools/low-hold.aspx)

**Player-prop research depth.** Props are a market filter, not a research product --
no game logs or L5/L10/L20 trends. Warns props cause account limitation.

**Odds-screen UX.** Odds comparison across books; filters for odds ranges, liquidity
minimums, hours-to-start, +EV thresholds; search syntax; up to 300 results. Web only;
no documented one-click deep link.

**Books.** ~25+: BetMGM, DraftKings, FanDuel, Caesars, BetRivers, Bovada, Pinnacle,
PrizePicks, Bally Bet, bet365.

**Sports & markets.** Baseball/Basketball/Football/Hockey/Soccer; MLB/NBA/NCAAB/
NCAAF/NCAAW/NFL/NHL/WNBA/FIFA World Cup; mainlines + props.

**Tracker & CLV.** Not a tracker-first product; no auto-sync log or CLV graphs.

**Alerts.** Free **Discord** (6,000+ members) with state/book-specific play/boost
notifications per user.

**Parlay/SGP, promo.** Free-bet converter, odds-boost, risk-free, Bet&Get, Win&Get
promo tools; Combo Breaker for parlays.

**Pricing.** Support from **$5/mo**; donations; substantial free access. Web only.

**Standout UX.** Richest devig menu (Multiplicative/Additive/Power/Shin x Liquidity-
Weighted/Unweighted/Worst-Case/Custom-Blend) + capital-aware Value% metric.

---

## 9. DarkHorse Odds (darkhorseodds.net)

**Core value prop.** Matched-betting + +EV platform pitched as the budget OddsJam
alternative ("less than 20% of the price"). Strong on devig flexibility + promo
conversion; devigs inline as you browse and surfaces +EV/arb/promo.
(https://about.darkhorseodds.com/guides/what-we-offer)

**+EV / devig (deepest documented method list).** Choose a single method, **worst-
case**, or a **custom-weighted blend of methods**, AND combine multiple **source
sportsbooks** (the anchor) by worst-case or custom-weighted blend with **per-book
weights**. Methods: **Multiplicative, Additive, Power, Shin, Goto** (margin-
distribution param fitted from history), **Probit** (z-score space), **Worst-Case**.
**Hover a line to see fair odds** (power method by default). Bankroll sizing: **Kelly
or fixed**; results sortable by +EV or **Certainty Equivalent**.
(https://about.darkhorseodds.com/guides/determining-fair-odds)

**Arbitrage.** Dedicated finder incl. exchanges for lay betting.

**Middling / low-hold / hedging.** Bet finders compute both sides + stakes; hedge-book
filter. Standalone middling/low-hold less documented than Crazy Ninja's.

**Player-prop research depth.** Props supported as a market; not a hit-rate research
tool.

**Odds-screen UX.** Hover-to-see-fair-odds devig overlay (signature). Filters: sport,
league, market, min/max odds, hedge book, event include/exclude.

**Books.** **40-45+** books + exchanges incl. DraftKings, FanDuel, BetMGM, Caesars,
Sporttrade, Kalshi.

**Sports & markets.** NFL/MLB/NBA/tennis+. ML, Spread, Total, **Alt Spreads/Totals**,
game segments, Draw No Bet, Double Chance, tennis markets, props.

**Tracker & CLV.** Not a tracker-first product.

**Alerts.** Discord; promo/sign-up-offer dashboards per your books.

**Promo (core strength).** Converters for Bonus Bet, Site Credit, Second-Chance,
Profit Boost, Qualifying Bet; Promo + Sign-up Offer dashboards w/ completion status.

**Pricing.** Not transparently listed (a criticism). Review estimates ~$39/mo basic,
~$199/mo premium; 2-day free trial + $30 off first month.

**Standout UX.** Hover-to-devig on live screen; 7 documented methods (incl. Goto +
Probit) + dual-layer custom weighting (per-method AND per-source-book); Certainty-
Equivalent sorting.

---

## 10. Pinnacle (the fair-value anchor)

**Why it matters.** Pinnacle is not a tool -- it is the reference book whose lines
every +EV tool above devigs to derive fair value. Its low-margin, high-limit,
winners-welcome model makes its closing lines the closest thing to true probability;
a "market maker" alongside Circa.

**Why it is the no-vig anchor.**
- **Low margins:** ~1.5-3% overround vs 4-7% retail (often -105/-105 vs -110/-110).
  Its no-vig line is the "gold standard"/"source of truth."
- **High limits:** up to **$50,000** NFL/NBA handicaps; ~**$30,000** main markets
  football/basketball/tennis; up to **$250,000** max accumulated daily winnings.
  Limits open ~25% of max and rise toward game time.
- **Does not limit winners:** welcomes sharp action, relies on volume + low margin.
(https://www.pinnacleoddsdropper.com/guides/how-to-devig-pinnacle-s-odds-for-betting-on-soft-books,
https://surebetmonitor.com/knowledge-base/pinnacle-sports-betting-limits/)

**Implication for us.** Any +EV/devig feature should default its fair-value source to
Pinnacle (or a Pinnacle-weighted sharp consensus) and offer the same multiplicative/
power/Shin/worst-case/weighted options the competitors expose.

---

## 11. Props.Cash (player-prop research)

**Core value prop.** Category-leading player-prop *research* app (not odds/devig).
Consolidates hit rates, defense-vs-position, game logs, matchup splits; cuts research
30-60min -> 10-15min. Covers ONLY player props.
(https://props.cash/, https://picksandparlays.net/reviews/ai-picks/props-cash)

**Prop research depth (core).** **Hit rates** color-coded (green cleared/red missed)
across **L5/L10/L20 + full season**, rolling windows **3/5/7/10/20/custom**.
**Defense vs Position (DVP)** rankings to isolate matchups (e.g. a PG on the road
without their starting center vs a top-5 defensive backcourt). Splits: home/away,
with/without specific teammates, H2H opponent history, matchup grades. **No
projections, alerts, or AI picks** -- pure research.

**Line integration.** Live lines from DraftKings/FanDuel/BetMGM/Caesars/Barstool +
DFS pick'em from PrizePicks/Underdog/Boom/Thrive (DFS next to sportsbook lines).

**Sports.** NBA/NFL/MLB/NHL/WNBA/NCAAB/MLS/EPL/CS:GO.

**Tracker/CLV/arb/middling.** None (out of scope).

**Mobile vs web.** Native iOS + Android (4.8, 1,200+ reviews) + web + Discord bot.

**Pricing.** **$19.99/mo, $199.99/yr (~17% off), NBA Season Pass $69.99 one-time,
7-day free trial no card.**

**Standout UX.** Color-coded hit-rate bars + with/without-teammate + DVP filters;
cleanest DFS-vs-sportsbook line juxtaposition.

---

## 12. Sharp App (sharp.app)

**Core value prop.** Broader intelligence toolkit than Props.Cash: AI prop
projections + +EV + real-time arbitrage + unique "Sharp Report" across 100+ books.
Prop angle is **projection-driven** (model vs market line -> edge % + bet rating).
(https://sharp.app/)

**+EV / prop devig.** **Proptimizer** grades every prop vs the **de-vigged
consensus**, surfacing underpriced edges; blends prop-origination models + top-down;
generates DFS projections (PrizePicks Proptimizer).
(https://sharp.app/intro-to-sharp-tools/how-to-create-dfs-projections-using-the-proptimizer)

**Prop research depth.** AI projections vs current lines -> **edge % + bet rating**;
trend tracking; cross-book prop comparison.

**Arbitrage / +EV.** Real-time pre-game AND in-play arbitrage; +EV across 100+ books.

**Distinctive "Sharp Report."** View into a major sportsbook's balance sheet to spot
square/whale/sharp action -- unique in the category.

**Books.** 100+.

**Mobile vs web.** iOS + Android + web; full features require Pro.

**Pricing.** 7-day trial; **Sharp Pro ~$199.99 first year, renewing ~$299.99/yr.**

**Standout UX.** Proptimizer (devigged-consensus prop grading) + Sharp Report balance-
sheet view; in-play arbitrage.

---

## 13. Betstamp (tracker-first + PRO odds screen)

**Core value prop.** Dual product: (a) free **auto-syncing bet tracker** with
ROI/CLV analytics + social following, and (b) **Betstamp PRO**, a pro-grade player-
prop +EV odds screen across 200+ books with proprietary fair-value pricing. "The
pricing and data layer for modern sports markets."
(https://www.betstamp.com/, https://www.betstamp.com/pro)

**Tracker & CLV (core).** Connects **directly to sportsbooks** and **auto-grades
every bet (W/L/push) in real time -- no screenshot uploads.** Tracks **ROI and CLV
across every sport/league/bet type/book**; CLV computed for every main-market bet vs
both the book you bet at AND the best closing line available. Immutable shareable
verified records. **50+ books** for tracking.
(https://www.betstamp.com/tracking)

**Social / tipster following.** Follow friends/top performers; **real-time
notification when a follow places a bet**; share verified record.

**+EV / devig (PRO).** +EV odds screen with real-time edge detection across **200+
books**; proprietary **"True Line"** market-weighted fair value backtested 5+ seasons;
standalone No-Vig/Fair-Odds calculator.

**Arbitrage / low-hold (PRO).** Sort by **negative hold to surface every arb**; sort
by Edge, EV, or Hold %.

**Player-prop depth (PRO).** Props incl. milestones/derivatives; **alt props with
full ladder pricing**; SGP pricing engine. (A pricing screen, not a hit-rate tool.)

**Odds-screen UX.** **2,500+ markets**, line history with limits, **one-click bet
tracking and placement**, customizable views/filters by sport/market/player/book.

**Markets.** Main markets, props, alt props, SGPs, **live in-play markets.**

**Alerts.** **Steam alerts** on 2.5%+ True Line moves; real-time follow notifications.

**Refresh.** **400ms median refresh** on PRO screen.

**Mobile vs web.** iOS + Android + web.

**Pricing.** Tracker **free, no card.** PRO **Main tier $249/mo**; Props + Live tiers
contact-sales (capped/approval-gated).

**Standout UX.** Backtested "True Line" fair value, 400ms refresh, full alt-prop
ladder pricing, negative-hold arb sort, best-closing-line CLV on a FREE tracker.

---

## 14. Juice Reel (tracker-first + picks marketplace)

**Core value prop.** Free, mobile-first **auto-syncing bet tracker** fused with odds
comparison, a **verified picks marketplace**, and AI picks. Differentiator: verified
social proof -- every seller record is auto-verified via synced bets. 250,000+ users,
$4B+ synced.
(https://www.juicereel.com/, https://www.betsmart.co/tool-reviews/juice-reel)

**Tracker & CLV (core).** Connect accounts -> **auto-sync from 300+ books**, real-
time P&L by sport/team/bet type; analytics include **CLV**. (One June-2026 review
counts ~11 fully-integrated auto-sync books w/ 30+ referenced -- auto-sync may be
narrower than the 300+ odds-feed figure.)

**Picks marketplace & social tailing (standout).** Fully-transparent verified picks
marketplace; buy/sell picks with verified records; **"Sharp Mush"** surfaces top-
performer activity; **one-click tail**; bettors ranked by sport; daily free "Juice
Picks" (2/day) with refund-if-lose.

**AI picks.** Across NBA/NFL/MLB/CBB; April-2026 added **AI bet-grading (Tier 1-3).**

**Parlay / SGP (standout).** **Same-game-parlay odds comparison** in the dashboard --
the same SGP priced across DraftKings/FanDuel/BetMGM side by side.

**Line-shopping.** Odds comparison across **300+ books** incl. offshore softer-line
books.

**Arbitrage / alerts.** Arbitrage alerts + line-shopping notifications referenced; one
review notes no explicit push/Discord system documented.

**Books (tracking).** DraftKings, FanDuel, PrizePicks, Caesars, Underdog, Bet365,
BetMGM, Fanatics, Kalshi, Pick6, Fliff, BetRivers, ESPNBet, NoVig, ProphetX, Rebet +
300 others.

**Mobile vs web.** Mobile-first (iOS + Android); web app exists at app.juicereel.com.

**Pricing.** **Free** with optional premium.

**Standout UX.** Auto-verified tipster records (anti-fake-screenshot) + side-by-side
SGP price comparison + the picks-marketplace economy.

---

# PART 1 -- FEATURE MATRIX (products x features)

Legend: Y = yes / strong; P = partial / weak / undocumented; N = no; -- = N/A.
Numbers are book counts or notable values. "Us" = our current odds_shop.py.

## A. Core engine features

| Feature | OddsJam | Outlier | Unabated | ActionNet | OddsPortal | RebelBet | BetBurger | CrazyNinja | DarkHorse | Betstamp | JuiceReel | Props.Cash | Sharp | Us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| +EV vs devigged fair value | Y | Y | Y | P(proj) | P(avg) | Y | Y | Y | Y | Y | P | Y(prop) | Y | P(no live key) |
| Devig method choice | 5 | 8 | N(proprietary) | N | N | 1(mult) | P | 4+blends | 7+blends | N(True Line) | N | -- | P | 1(Shin only) |
| Sharp-book anchor (Pinnacle) | Y | Y | Y | N | N | Y | Y | Y | Y | Y | N | -- | Y | N(best-of-all) |
| Multi-book weighted consensus | Y | Y | Y | -- | N | P | Y | Y | Y | Y | -- | -- | Y | N |
| Arbitrage finder | Y | Y | N | N | Y | Y | Y | Y | Y | Y(neg hold) | P | -- | Y | Y |
| Middling | Y | Y | P(calc) | N | N | Y | Y | Y | P | P | -- | -- | P | N |
| Low-hold / hedging | Y | P | Y | P(calc) | N | Y | Y | Y | Y | Y | -- | -- | P | N |

## B. Odds screen / line shopping

| Feature | OddsJam | Outlier | Unabated | ActionNet | OddsPortal | RebelBet | BetBurger | CrazyNinja | DarkHorse | Betstamp | JuiceReel | Props.Cash | Sharp | Us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Best-line highlight | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y(best line) |
| Click-to-bet deep links | Y | Y | P | Y | P(link) | P | Y(ext) | N | N | Y | P | Y | N |
| Supported book count | 150+ | 15+ | 25+ | ~8-60 | 30-80 | 100+ | 600 | 25+ | 45+ | 200+ | 300+ | ~9 | depends API |
| Alt lines | Y | P | Y | Y | Y(AH) | P | Y(AH) | P | Y | Y | P | -- | N |
| Live / in-game odds | Y | P | Y | Y | Y | P | Y | N | P | Y | P | -- | Y(prop) | N |
| Historical odds archive | P | P | P | P | Y(2009) | P | N | N | N | Y(line hist) | N | Y(logs) | P | N |
| Data refresh speed | "1M/s" | RT | WS push | RT(lag) | 15s | 60s | ~3s | -- | -- | 400ms | -- | -- | RT | on-demand |

## C. Player props & parlays

| Feature | OddsJam | Outlier | Unabated | ActionNet | OddsPortal | RebelBet | BetBurger | CrazyNinja | DarkHorse | Betstamp | JuiceReel | Props.Cash | Sharp | Us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Player props +EV | Y | Y | Y | P | N | N | P | P | P | Y | P | -- | Y | N |
| Prop hit-rate research (L5/10/20) | Y | Y | P | Y(Labs) | N | N | N | N | N | N | N | Y | Y | N |
| Defense-vs-position | P | P | N | Y | N | N | N | N | N | N | N | Y | P | N |
| SGP price comparison | Y | Y | P | N | N | N | N | N | N | Y | Y | -- | P | N |
| SGP correlation EV engine | Y | N | N | N | N | N | N | N | N | P | N | -- | N | N(have corr research) |
| DFS pick'em (PrizePicks/UD) | Y | Y | Y | Y | N | N | N | Y | Y | P | Y | Y | Y | N |

## D. Tracker, CLV, alerts, promos

| Feature | OddsJam | Outlier | Unabated | ActionNet | OddsPortal | RebelBet | BetBurger | CrazyNinja | DarkHorse | Betstamp | JuiceReel | Props.Cash | Sharp | Us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Bet tracker | Y | N | P(manual) | Y | P | Y | N | N | N | Y | Y | N | P | N |
| Auto-sync (link/screenshot) | Y | N | N | Y(both) | N | P(add-on) | N | N | N | Y(link) | Y(link) | N | P | N |
| CLV tracking | Y | N | Y(calc) | Y | N | Y | N | N | N | Y | Y | N | P | N |
| Real-time alerts | Y | Y | Y(browser) | Y | P(email) | Y | Y(Telegram) | Y(Discord) | Y(Discord) | Y(steam) | P | N | N | N |
| Push / SMS / email / Discord | push,email,Slack | push,Discord | browser,Discord | push | email | push | Telegram | Discord | Discord | push | P | N | P | N |
| Promo / bonus conversion | Y | P(boost) | N | P(list) | N | N | N | Y | Y | N | N | -- | N | N |
| Filter presets saved | Y | Y | Y | P | Y | 2-4 | Y(profiles) | Y | Y | Y | P | Y | Y | N |

## E. Platform & pricing

| Attribute | OddsJam | Outlier | Unabated | ActionNet | OddsPortal | RebelBet | BetBurger | CrazyNinja | DarkHorse | Betstamp | JuiceReel | Props.Cash | Sharp | Us |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Web | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y | P | Y | Y | Y(HTML board) |
| iOS | Y | Y | N | Y | N | N | N | N | N | Y | Y | Y | Y | N |
| Android | N | N | N | Y | N | N | N | N | N | Y | Y | Y | Y | N |
| Free tier | calc | trial | trial | Y(basic) | Y | trial | Y(delayed) | Y | trial | Y(tracker) | Y | trial | trial | Y(local) |
| Entry price/mo | $200 | $20 | $67 | $25 | free | $69 | EUR80 | $5 | ~$39 | free/$249 | free | $20 | ~$17 | -- |
| Own model predictions | N | P(AI) | Y(sim) | Y(proj) | N | N | N | N | N | Y(TrueLine) | Y(AI) | N | Y(AI) | Y(4 sports, calibrated) |

---

# PART 2 -- GAP ANALYSIS vs our current product

## What we have today

`scripts/platformkit/odds_shop.py` provides, as pure tested functions over The Odds
API (when `ODDS_API_KEY` is set):
- `best_line` -- best (highest-decimal) price per side across books.
- `devig_twoway` -- no-vig fair probs via the vetted **Shin** solver (one method only).
- `detect_arb` -- two-way arb check + optimal stake split + margin %.
- `ev_vs_price` -- model EV per $1 at the best price.
- `summarise_twoway` -- bundles best-line + Shin devig + arb + optional model EV.
- A basic HTML board, manual bet placement.

Plus the broader system's genuine asset: **calibrated model predictions for
NBA/MLB/World-Cup/club-soccer/tennis**, an honest eval gate, and existing playstyle-
correlation research (relevant to SGP).

We do NOT have (today): a live odds key wired into a running board, a CLV ledger,
alerts, player props, alt lines, live/in-game odds, multi-book consensus, devig method
choice, middling, low-hold, promo conversion, a mobile app, or click-to-bet links.

## Gaps ranked by impact (highest first)

1. **No live odds feed actually running (no key wired into a refreshing board).**
   Every competitor's entire value depends on a fast, always-on odds feed. Without
   it, all of odds_shop's logic is dormant. This is the single highest-impact gap --
   it gates everything else. Bar: OddsJam "1M odds/sec", Betstamp 400ms refresh,
   Unabated WebSocket push.

2. **No CLV ledger.** CLV is the universal "honest edge" yardstick (OddsJam,
   Betstamp, RebelBetting, Action Network, Juice Reel all ship it) and it maps
   exactly to our own north star ("beat the devigged close"). We have the math
   (devig) but no persistent bet log that records taken price vs closing line. This
   is our most natural differentiator because we already produce calibrated closing-
   line proxies per sport.

3. **No player props at all.** Props are the single largest US growth surface
   (OddsJam, Outlier, Props.Cash, Sharp, Betstamp all lead here). We are NBA-deep on
   player modeling but expose zero prop value, no hit-rate research, no DVP. Outlier/
   Props.Cash set the bar: L5/L10/L20 hit-rate badges, DVP, with/without-teammate
   splits.

4. **Single devig method (Shin only), no method choice, no multi-book consensus.**
   The +EV battleground is devig depth. Outlier exposes 8 methods + Average default +
   multi-book weighting; OddsJam 5 + worst-case + source-of-truth toggle; DarkHorse 7
   incl. Goto/Probit + dual-layer weighting. We have one method and take best-of-all-
   books (no sharp anchor), which is methodologically weaker for fair value.

5. **No alerts / notifications.** Real-time +EV/arb/line-move/CLV alerts (push,
   Discord, Telegram, email) are table stakes -- the value is time-sensitive. We have
   none.

6. **No live / in-game odds and no alt lines.** In-game is the explicit market gap
   (Unabated's whole edge; OddsJam Platinum's "2x"). Notably this is also where OUR
   measured calibration edge lives (in-game conditioning). Alt lines unlock middling.

7. **No middling, low-hold, or promo-conversion tools.** Standard execution-edge
   toolkit across OddsJam/RebelBetting/BetBurger/CrazyNinja/DarkHorse. Promo
   conversion (CrazyNinja/DarkHorse/OddsJam) is the highest-ROI execution lane for a
   new bettor.

8. **No click-to-bet deep links.** OddsJam/Outlier/Action Network pre-fill the
   betslip; this is the premium "feels fast" detail. We require fully manual placement.

9. **No mobile app.** OddsJam/Outlier/Action Network/Betstamp/Juice Reel/Props.Cash
   are mobile-first; alerts + tracking live on the phone. We are an HTML board.

10. **No saved filters / presets / sort UX.** Every competitor ships rich filtering
    (EV%, min/max odds, book include/exclude, devig method, freshness, saved presets).
    Our board is static.

11. **No SGP / parlay tooling.** Only OddsJam has a true correlation engine -- and we
    already have playstyle-correlation research that could power one (a latent
    differentiator, not just a gap).

12. **No historical odds archive / line-movement charts.** OddsPortal (2009 archive)
    and Betstamp (line history w/ limits) set this bar; useful for CLV context.

13. **No promo/boost discovery, no DFS pick'em (PrizePicks/Underdog) integration.**

## Where we are already differentiated (do not lose this)

- **Genuine calibrated multi-sport model predictions** with an honest eval gate.
  Most competitors either have no model (OddsJam, OddsPortal, RebelBetting, BetBurger,
  CrazyNinja, DarkHorse) or a black-box one (Betstamp True Line, Action proj). We can
  show a *calibrated, leak-free* number per sport -- and crucially, an honest in-game
  conditional edge. Frame it as calibration, never as a $ edge (per house rules).
- **Tennis + World Cup + club soccer model coverage** -- Unabated has no soccer;
  most US tools are thin on tennis modeling.
- **Existing SGP-correlation research** -- a head start on the one feature only
  OddsJam has.

---

# PART 3 -- PRIORITIZED FEATURE BACKLOG

Constraints honored: build under `scripts/platformkit/`, <=300 LOC/file, no edge
claims (calibration framing only), no secrets, data/vault gitignored, local-only.

## P0 -- become functional and honest-best (do first)

- **P0.1 Wire a live, refreshing odds board.** Add a scheduled fetch loop around
  `fetch_odds` that snapshots all books to a local store on an interval; render the
  HTML board off the snapshot with a freshness timestamp per row. *How:* small
  poller + on-disk JSON/parquet snapshot table; board reads latest snapshot. Gates
  everything else.
- **P0.2 CLV ledger.** Persist every "intended bet" (sport, market, side, taken
  price, book, timestamp) and later join the closing line (devigged sharp consensus
  or our calibrated close) to compute CLV % and % beating close. *How:* append-only
  JSONL ledger + a `record_clv`-style joiner reusing existing devig; surface CLV in
  the board. Reuse the calibrated closing-line proxy we already produce.
- **P0.3 Multi-book sharp anchor + devig method choice.** Add a Pinnacle-anchored (or
  weighted sharp-consensus) fair-value path and expose method choice
  (multiplicative/additive/power/Shin/worst-case) alongside our existing Shin. *How:*
  add `devig_multiway(method=...)` + `fair_value(anchor_books, weights, method)`;
  keep Shin as default. Each method is a small pure function (<300 LOC/file).
- **P0.4 Filters, sorting, presets on the board.** EV% threshold, min/max odds, book
  include/exclude, sport, market, freshness; sortable by EV%/arb%; save presets.
  *How:* query params over the snapshot table; presets in a local config.

## P1 -- match the best-in-class toolkit

- **P1.1 Player props +EV (start NBA).** Pull prop markets, devig vs sharp anchor,
  surface +EV props; lean on our NBA modeling for a model-EV column. *How:* extend
  `parse_event_books` to prop market keys; reuse devig path; new prop board view.
- **P1.2 Prop hit-rate research (L5/L10/L20 + DVP).** Match Props.Cash/Outlier:
  color-coded hit-rate windows + defense-vs-position from our existing player data.
  *How:* aggregate from existing game logs/atlases into a hit-rate view; we already
  have the data on disk.
- **P1.3 Middling + low-hold + alt lines.** Add alt-line ingestion, a middle finder
  (two-sided gap detector), and a low-hold/negative-hold sort. *How:* generalize
  `detect_arb` to alt-line pairs; add hold/middle pure functions.
- **P1.4 Alerts.** Real-time +EV/arb/line-move/CLV alerts to a channel. *How:* diff
  successive snapshots; push to Discord/Telegram webhook + email; user thresholds.
- **P1.5 Click-to-bet deep links.** Map book -> deep-link URL template, pre-fill the
  slip where supported. *How:* per-book URL builder; render a Bet button per row.
- **P1.6 Live / in-game odds + our in-game conditional number.** Ingest live markets;
  show our calibrated in-game conditional projection beside the live price (label as
  calibration). *How:* live market keys + reuse the in-game projector; this is our
  measured edge surface.

## P2 -- premium / differentiating polish

- **P2.1 SGP correlation EV engine.** Turn our existing playstyle-correlation research
  into priced SGP value vs book SGP price. *How:* feed correlation matrices into a
  joint-prob SGP pricer; compare to book SGP. (Only OddsJam has this -- and we have a
  head start.)
- **P2.2 Promo / bonus-bet conversion tools.** Bonus-bet, profit-boost, second-chance
  converters + an "is this boost +EV" scorer. *How:* small conversion calculators
  (CrazyNinja/DarkHorse pattern); boost-EV = devigged-fair vs boosted price.
- **P2.3 Auto bet tracking (screenshot/CSV import).** Reduce manual ledger entry via
  screenshot parse or CSV import to feed the CLV ledger. *How:* OCR/CSV importer ->
  ledger; account-link is out of scope (compliance).
- **P2.4 Historical odds archive + line-movement charts.** Persist snapshots over time
  for opening->close movement + CLV context. *How:* retain P0.1 snapshots; chart per
  market.
- **P2.5 Mobile-friendly UI / app.** Make the board responsive first; native app
  later. *How:* responsive web; consider PWA before native.
- **P2.6 DFS pick'em integration (PrizePicks/Underdog).** Place DFS lines next to
  sportsbook lines (Props.Cash pattern). *How:* add DFS sources to the prop board.

## Cross-cutting honesty guardrails (apply to all of the above)

- Frame model output as **calibration, not a $ edge**; +EV vs a soft book is an
  **execution** opportunity, never a beat-the-close claim (already encoded in
  odds_shop's honesty contract).
- CLV is the honest yardstick; never re-endorse the inverted CLV sign.
- No fabricated prices on feed failure (status="unavailable" already enforced).
- Keep all of this local-only; never push to public origin; no secrets in code.

---

## Source notes / caveats

- OddsJam book count varies 100-300 and pricing varies across review sites; the iOS
  listing is the most authoritative pricing source.
- Outlier's bet-tracker, live-odds, and alt-lines are undocumented (treated as gaps).
- Unabated base-tier price and add-on structure are inconsistent across sources;
  Premium $199/mo and Concierge $799/mo are the stable confirmed figures.
- DarkHorse and Sharp App pricing come from third-party reviews, not their own pages.
- OddsPortal book count conflicts (~30 geo-filtered vs 60-80 global).
- BetBurger publishes no USD pricing and no formal devig-method label.
- Juice Reel auto-sync coverage (300+ odds feed vs ~11-30 auto-sync books) is
  ambiguous in 2026 reviews.
