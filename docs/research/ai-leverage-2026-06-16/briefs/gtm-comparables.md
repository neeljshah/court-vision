# GTM Comparables: Calibration-First Forecasting Products
_Researched 2026-06-16. Scope: FiveThirtyEight-style public probabilistic forecasting; Good Judgment / superforecasting brands; Metaculus / Kalshi; sports-analytics B2B (Zelus/Teamworks, Sportlogiq, Second Spectrum, Stats Perform, Swish Analytics); prediction-as-API plays. For each: what they sell, who pays, how they build trust, and what a solo operator can credibly emulate vs not._

---

## TL;DR (highest-leverage takeaways)

- **The trust moat IS the product for calibration-first forecasters.** FiveThirtyEight, Silver Bulletin, Good Judgment, and Metaculus all built their entire brand on ONE thing: a publicly auditable, multi-year calibration record with transparent methodology. The product is the proof-of-work, not the algorithm.
- **Good Judgment is the closest structural comparable.** They sell calibrated probability forecasts to government/enterprise clients. The moat = a public track record + named superforecasters + rigorous methodology docs. A solo operator cannot replicate their human panel, but CAN replicate the credibility pattern: timestamped OOS predictions, published Brier scores, honest abstention.
- **Metaculus's 0.111 Brier score is its entire sales pitch.** They built institutional trust (CDC, WHO commissioning forecasting work) purely on published calibration metrics and auditable scoring rules. Zero "picks" framing.
- **B2B sports analytics (Zelus/Teamworks, Sportlogiq, Second Spectrum) sells to TEAMS, not bettors.** The trust model is PhD team credibility + league official data rights + named team clients. Pricing is enterprise (undisclosed, likely $100K-$500K+/year). A solo operator cannot replicate this go-to-market but can target the same BUYERS (analytics departments, media orgs) with a different entry point: open methodology + public calibration proof.
- **Swish Analytics is the clearest prediction-as-API comparable.** B2B API to sportsbooks (FanDuel, DraftKings) for odds origination + parlay pricing. They built trust via MLB official data distributor status + live market customers. Solo operator equivalent: a clean prediction API with published calibration, targeting media/DFS/research clients rather than sportsbooks.
- **The Silver Bulletin pattern is directly replicable by a solo operator.** Substack-based, freemium, 314K+ subscribers, trust via personal brand + transparent methodology + regularly-updated models. Sports + elections = two verticals, same credibility pattern. No "edge" framing -- pure forecasting.
- **The one thing ALL credible comparables share:** they publish the Brier score (or equivalent) BEFORE they publish any market-facing claim. Calibration metrics are the admission ticket to the credible tier; without them, the product sits in the "AI picks" category regardless of technical quality.

---

## Comparable 1: FiveThirtyEight / Silver Bulletin (Nate Silver)

### What they actually sell
- FiveThirtyEight (closed March 2025 after ABC restructuring): free probabilistic journalism -- election forecasts, sports elo ratings, polling averages. Revenue = display advertising + ABC ownership subsidy.
- Silver Bulletin (post-FiveThirtyEight, Substack): paid subscription (~$700/year equivalent for full access). Free tier = some articles. Paid = daily-updated models, full archives, elections + sports + poker + economics analysis. 314K+ subscribers as of 2025. Plans to relaunch NBA/NFL models.

### Who pays
FiveThirtyEight: advertisers (not readers). Silver Bulletin: direct readers via Substack subscriptions. No B2B licensing, no API, no enterprise.

### How they build trust
- 2008 Obama election: correctly called 49/50 states.
- 2012: 50/50 states correctly called.
- Published methodology for every model ("Model Talk" columns).
- 2016: gave Trump 29% (most other forecasters gave <2%) -- the HIGHER number was more calibrated, and Silver used this to build a "we're honest about uncertainty" brand.
- Transparent about what models get wrong and why.
- Track record is the only product. No editorial hedging ("we can't say who will win") -- they commit to a number and stand behind it.

### What a solo operator can emulate
- The Substack-first publication model: freemium, model updates visible to paid subscribers, free tier builds audience. Directly replicable.
- Publishing calibration curves and Brier scores alongside every prediction cycle. Directly replicable.
- "Model Talk" methodology columns: written, specific, honest about failure modes. Directly replicable.
- Principled abstention ("this race is within our model's uncertainty bound") as a brand signal. Directly replicable.

### What a solo operator CANNOT emulate
- The 15-year public track record. You build this over time, not by launching with it.
- The personal brand (Silver had a book, a team, ABC backing). You build audience from zero.
- The election-cycle volume of forecasting questions that creates calibration data fast.

### Key gotcha
FiveThirtyEight's closure in 2025 is instructive: ad-supported free probabilistic journalism is not a durable business model. Silver's pivot to paid Substack is the correct solo-operator pattern -- direct reader revenue, not advertising.

---

## Comparable 2: Good Judgment Inc. / Superforecasting

### What they actually sell
Good Judgment Inc. (commercial spinout of Tetlock's IARPA-funded Good Judgment Project) sells three things:
1. **FutureFirst:** subscription service giving access to Superforecaster insights on dozens of newsworthy questions across geopolitics, policy, markets. Targeted at corporate strategy / government / think tanks.
2. **Custom forecasting contracts:** clients submit questions, Good Judgment frames them precisely, assigns ~40 superforecasters, aggregates probabilities using proprietary algorithms, delivers daily-updated forecasts. Specialty = "low- or messy-data questions" where quant models fail.
3. **Training/consulting:** "superforecasting" methodology workshops for corporate decision-makers.

### Who pays
Government agencies (including intelligence community via IARPA origin), corporate strategy departments, non-profits, foundations. NOT individual bettors. NOT media. Enterprise contracts, not subscription tiers for consumers.

### How they build trust
- Tetlock's decades of published academic research (starting 1984) establishes the intellectual foundation.
- IARPA forecasting tournament result: superforecasters outperformed intelligence analysts with access to classified information. That result is the sales pitch.
- Calibration metric: superforecasters achieved 0.01 average calibration error (difference between stated probability and observed frequency). This is the proof of work.
- Public track record on Good Judgment Open (free platform) generates the credibility data that enterprise clients buy.
- Named methodology: "actively open-minded thinking," incremental updating, team aggregation.

### What a solo operator can emulate
- The pattern of building a public free platform (calibration record on open questions) to earn the right to sell enterprise/advisory work. This is exactly the right GTM for a calibrated sports predictor.
- Principled question-framing ("will X happen by date Y, defined as...") -- brings forecasting discipline to sports markets that usually use vague language.
- Publishing the calibration calibration curve across many questions as the trust artifact.
- The "honest about uncertainty" brand: "our superforecasters said 35%, which is more accurate than most pundits who said 90%."

### What a solo operator CANNOT emulate
- A panel of ~40 human superforecasters. You are one person.
- 15+ years of published academic research backing the methodology.
- IARPA/government institutional endorsement.
- "Classified information" baseline to beat -- you don't have that comparison.

### Key insight for this project
Good Judgment's freemium funnel is directly applicable: publish calibrated predictions publicly (the free "Good Judgment Open" equivalent) -> build a proven track record -> sell advisory access or enterprise contracts to orgs that need the forecasting. The sports prediction equivalent: public Brier scores on NBA/MLB/soccer/tennis -> earn credibility -> sell analytics dashboards or B2B data access to media/DFS/research orgs.

---

## Comparable 3: Metaculus

### What they actually sell
Metaculus is a crowd-sourced probabilistic forecasting platform. Revenue model = institutional partnerships, grants, and commissioned forecasting projects (NOT user subscriptions -- individual access is free). Organizations sponsor forecasting competitions or commission custom question sets relevant to their decision-making.

### Who pays
Institutions: CDC, WHO, academic research orgs, foundations, policy think tanks. Enterprise clients commission private forecasting on their specific questions. Tournament sponsors fund prize pools.

### How they build trust
- Published Brier score of 0.111 across thousands of resolved questions -- this is the entire trust pitch.
- Proper scoring rules (Brier + log score) reward calibration specifically, not just accuracy. This is technically rigorous.
- Individual calibration curves published for every forecaster -- transparent at the person level.
- Institutional endorsements (WHO, CDC using the platform for real decision support) = the equivalent of a "MLB official data distributor" badge.
- Regular academic collaborations (e.g., AI Forecasting Benchmark Series with $175K prize pool in 2025-2026).

### What a solo operator can emulate
- Publishing a single headline calibration metric (Brier 0.111 equivalent) that is the first thing any visitor sees.
- Transparent, auditable scoring methodology (not "our model says X" but "here is the scoring rule, here is the record, here is the calibration curve").
- Pursuing one institutional endorsement early -- even a single notable sports analytics department or media org using the platform creates the "WHO uses Metaculus" equivalent proof.

### What a solo operator CANNOT emulate
- Community-sourced aggregation across thousands of forecasters. You are one model.
- Established relationship with health/government institutions.
- Grant funding.

### Key gotcha
Metaculus's free-to-user model is NOT directly replicable for a solo operator who needs revenue. The relevant takeaway is the TRUST pattern (published Brier, auditable scoring, institutional endorsement) not the business model.

---

## Comparable 4: Kalshi (prediction market)

### What they actually sell
Kalshi is a regulated prediction market exchange (CFTC-regulated, launched 2021). Users trade binary contracts ("will X happen"). Revenue = transaction fees on each contract traded. Not a forecasting product -- a market infrastructure.

### Who pays
Retail traders who want to speculate or hedge. Some institutional participants (SIG/Nellie Analytics, Jump Trading -- see competitive-landscape.md) trade at scale on game-level contracts.

### How they build trust
- CFTC regulation is the trust signal ("legal, regulated, not a sportsbook").
- Publicly auditable market prices as the implicit calibration metric.
- Official launch of sports contracts (NBA, NFL, soccer) creates a liquidity pool.

### What a solo operator can emulate
- Using Kalshi market prices as a CALIBRATION BASELINE: if your predicted probability differs significantly from Kalshi's market price, either your model has information the market lacks, or your model has an error. This is a rigorous reality check.
- Framing your product as "calibrated probability forecasting" that is complementary to, not competing with, prediction markets.

### What a solo operator CANNOT emulate
- A regulated exchange. Not relevant -- this is infrastructure, not a forecasting product.

### Key gotcha
Kalshi market prices on sports are the strongest available "devigged market probability" baseline. Publishing your model's deviation from Kalshi (or closing sportsbook lines) with honest commentary on why is a credibility signal -- it shows you take the market seriously as a prior.

---

## Comparable 5: Zelus Analytics (now Teamworks Intelligence)

### What they actually sell
Acquired by Teamworks in September 2024 and rebranded as Teamworks Intelligence. Sells sport-specific predictive models to pro sports front offices for: player evaluation, roster construction, contract valuation, matchup analysis, load management. Serves 30+ front offices including NFL, NBA, MLB, NHL, international soccer, Olympics. One team per MLB division; three per NBA conference (exclusivity model).

### Who pays
Pro sports front offices (general managers, analytics departments). Enterprise SaaS pricing (undisclosed, likely $150K-$500K+/year based on team budget norms). Not media, not bettors, not consumers.

### How they build trust
- 25+ PhDs on staff + 12 former R&D leads from top sports organizations.
- Named endorsements from credible figures (Billy Beane).
- Exclusivity model (one team per division) creates scarcity/prestige.
- Acquisition by Teamworks (the dominant enterprise SaaS for pro sports operations) provides institutional backing.

### What a solo operator can emulate
- The BUYER is the same: sports analytics departments. The entry point is different.
- Solo operator equivalent: one rigorous sport done deeply (NBA), published methodology, one named team/org endorsement, even informal. A single "an NBA analytics director cited our model" is structurally similar to Zelus's "Billy Beane endorsement."
- Calibration-first framing positions against Zelus, not alongside Sportradar. Zelus sells roster decisions; a calibrated predictor sells probabilistic game intelligence. Different SKU, same buyer.

### What a solo operator CANNOT emulate
- 25+ PhD staff.
- Teamworks institutional distribution (Teamworks already has relationships with 90%+ of pro sports orgs).
- Exclusivity contracts that lock out competitors per division.
- The breadth: multi-sport, multi-league, roster + contract + load management.

### Key gotcha
Zelus/Teamworks is not a threat -- they target a different buyer pain (front office roster decisions, not game-level probability forecasting). The risk is being dismissed as "too small" by the same buyer. The counter is: DEPTH on NBA game-level calibration that no $300K/year Teamworks contract addresses. Different product, different conversation.

---

## Comparable 6: Sportlogiq

### What they actually sell
Computer vision + ML tracking from standard broadcast footage -- advanced hockey and soccer metrics. iCE platform: 300+ metrics for coaching, scouting, player development. Clients: 97% of NHL teams (31/32), 220+ clients worldwide, 42 NCAA hockey programs, IIHF, US Soccer. Acquired by Teamworks in January 2026 alongside Zelus, further consolidating the B2B sports analytics stack.

### Who pays
Pro and collegiate sports teams (coaching and analytics departments). Not bettors, not media primarily. Enterprise SaaS.

### How they build trust
- 97% NHL penetration is itself the trust signal. When 31 of 32 NHL teams use your platform, you are the standard.
- Patented CV technology (not just licensed Sportradar data -- own tech).
- Inside Edge partnership for NHL coverage.

### What a solo operator can emulate
- The CV-from-broadcast approach is the EXACT structural parallel to this project. Sportlogiq built a moat by extracting tracking data from publicly available broadcast video that every team already licenses. This project does the same for NBA.
- Publishing accuracy metrics for CV extraction (what percentage of events are correctly detected) is the technical credibility equivalent of Sportlogiq's "300+ validated metrics."

### What a solo operator CANNOT emulate
- 31/32 NHL team penetration (a decade of BD work).
- Patented technology (takes years + legal resources).
- Multi-league scale (NHL + soccer + American football + Teamworks integration).

### Key insight
Sportlogiq's moat is "we track things Sportradar doesn't, from the same broadcast video you already have." This project's moat pitch should be the same: "possession-level NBA intelligence from broadcast CV at $0.10/game vs. six-figure Sportradar contracts." Same structural argument, different sport. This is a credible pitch.

---

## Comparable 7: Second Spectrum / Genius Sports

### What they actually sell
Second Spectrum (acquired by Genius Sports May 2021) is the official optical tracking provider for the NBA, EPL, and MLS. Sells: official tracking data feeds to teams + leagues + broadcasters + betting operators; video augmentation (AR overlays, automated clips); real-time analytics APIs. Revenue = league official data rights contracts (likely $10M-$50M+/year deals with leagues) + downstream API licensing to betting operators and media.

### Who pays
Leagues (NBA, EPL, MLS pay for the official tracking infrastructure), broadcasters (ESPN, TNT pay for augmentation), betting operators (FanDuel, DraftKings pay for official real-time data feeds), pro sports teams (subscribe to the analytics platform).

### How they build trust
- OFFICIAL league designation is the entire trust model. "Official NBA tracking provider" = every other tracking product is unofficial by definition.
- Genius Sports' publicly traded status and league relationships provide institutional credibility.
- Technical superiority (optical tracking from dedicated arena cameras, not broadcast video) vs. competitors.

### What a solo operator can emulate
- Nothing about Second Spectrum's go-to-market is replicable by a solo operator. They sell official data at institutional scale.
- The relevant frame: Second Spectrum is the CEILING of what this market looks like when it matures. A solo operator building broadcast-CV tracking today is building toward the point where Genius Sports or Sportradar either acquires the capability or licenses it.

### Key gotcha
Second Spectrum uses dedicated arena camera arrays, not broadcast video. That is a $1M+ installation cost per arena. This project uses broadcast video, which is a fundamentally different (lower cost, more scalable, less accurate) approach. Never position directly against Second Spectrum on tracking accuracy. Position on COST and ACCESSIBILITY: "same signal, 1000x cheaper infrastructure."

---

## Comparable 8: Stats Perform / Opta

### What they actually sell
Stats Perform (owns Opta brand) sells: official sports data collection + feeds for 60+ football actions in 3,000+ competitions; AI-powered predictions and models; media content (automated written summaries); betting feed APIs (real-time odds data, prediction models). Opta data is the industry standard for European football.

### Who pays
Media organizations (broadcast rights holders), betting operators (official data rights required for in-play betting in regulated markets), pro teams (scouting and performance data). Enterprise contracts.

### How they build trust
- "Decades of use" in professional clubs, leagues, and media is the trust pitch.
- Standardized event definitions across global competitions -- the credibility of a standard-setter.
- Mandatory status in many regulated betting markets (official data rights laws in UK, Germany, etc.).

### What a solo operator can emulate
- Using Opta/Stats Perform data as a supplementary input (for training or validation) is viable and signals methodology rigor.
- The "standardized definitions" pattern: precisely defining what your model measures (not vague "team strength" but specific operationalized metrics) is the solo equivalent of Opta's event definition rigor.

### What a solo operator CANNOT emulate
- Official data rights. These are exclusive contracts with leagues and cost millions.
- Regulatory mandatory status in betting markets.

---

## Comparable 9: Swish Analytics

### What they actually sell
Founded 2014, San Francisco. B2B API for US sports betting operators: odds origination, risk management, and trading software for NBA, NFL, MLB, NHL. Core product: "Bet Request" -- a parlay pricing engine delivering real-time odds for almost any combination of markets via API or trader console. Also: player prop projections and lines.

### Who pays
Sportsbooks (FanDuel, DraftKings, Sky Bet/international operators) -- this is a B2B API play where the customer is the book, not the bettor. MLB official authorized data distributor designation.

### How they build trust
- MLB official authorized data distributor = institutional data endorsement.
- Named sportsbook clients (FanDuel, DraftKings, Sky Bet).
- Founded by Capital One / financial institution data scientists -- quant credibility transfer.
- Focus on parlay pricing accuracy as the specific technical trust claim (not generic "we have good models").

### What a solo operator can emulate
- The prediction-as-API architecture: a clean API endpoint that returns calibrated probabilities is a real product that media/DFS/research orgs can integrate. Swish did this for sportsbooks; the solo equivalent targets media dashboards or DFS platforms.
- Specificity of trust claim: "our Brier score on NBA team totals is X" is the solo equivalent of Swish's "our parlay pricing engine handles any combination of markets in real-time."
- Financial services background as credibility transfer: Swish used "we are data scientists from Capital One" to establish rigor. This project's equivalent: "walk-forward OOS validated, 2-corpus tested, not an in-sample backtest."

### What a solo operator CANNOT emulate
- MLB official data distributor designation (requires an official partnership with MLB Advanced Media -- not available to solo operators).
- Live sportsbook integrations (regulatory, compliance, and contract requirements block solo access).
- Real-time odds origination at the speed required for live betting markets.

---

## How THIS project should apply it: concrete actions ranked by leverage

### 1. Adopt the Silver Bulletin publication pattern immediately.
Substack or similar: free tier = methodology posts + one calibration update per game cycle; paid tier = daily model updates, full calibration dashboard, historical records. No "edge" framing anywhere. Frame as "probabilistic game intelligence, 4 sports." This is directly replicable, does not require institutional backing, and builds the audience that converts to enterprise leads.

### 2. Publish the Brier score + calibration curve as the homepage headline.
"NBA pregame Brier 0.208 | Walk-forward OOS, 2 corpora | In-game conditioning is the measured gap." This is the Metaculus 0.111 pattern: the calibration number IS the product positioning. Every potential buyer (analytics dept, media, DFS platform) needs to see this before they read anything else.

### 3. Build the public track record ledger now, not later.
Every prediction (timestamped, inputs logged, calibrated probability, eventual outcome) should go into an append-only public record from the first game forward. This is the Good Judgment Open pattern: the free public track record earns the right to sell enterprise access. A 6-month auditable record is worth more than any algorithm upgrade in a sales conversation.

### 4. Frame the CV-from-broadcast approach as the Sportlogiq comparable.
"Possession-level NBA tracking from broadcast video at $0.10/game vs. six-figure Sportradar/Second Spectrum contracts." Sportlogiq built its moat this way for hockey. The structural argument is identical and credible. Use this in any B2B conversation with analytics departments.

### 5. Target the SAME buyer as Zelus/Teamworks (analytics departments) but with a different SKU.
Zelus sells roster/contract/load decisions. This project sells GAME-LEVEL probabilistic intelligence with in-game conditioning. Same buyer (director of analytics at an NBA team), different conversation. The entry point: "we publish our Brier score publicly, and it is competitive with the market on pregame. In-game conditioning is the differentiation. Would you want to see the walk-forward results?"

### 6. Use Kalshi / sportsbook closing lines as the calibration baseline in all public communications.
"Our pregame probabilities match the devigged closing line within [X]% across [N] games." This is honest (you have proven pregame market efficiency), it demonstrates rigor (you compared against the strongest available benchmark), and it positions in-game conditioning as the additive layer that beats the pregame prior. This is the "we beat the intelligence analysts" IARPA result equivalent.

### 7. Pursue ONE institutional endorsement early.
Good Judgment got IARPA. Metaculus got WHO/CDC. Sportlogiq got the NHL. The solo equivalent: a single named sports analytics director, media org, or DFS platform that uses the product publicly. Even an informal "an NBA team's analytics department reviewed our methodology" is structurally significant. This is the unlock that moves the product from "solo side project" to "credible analytics platform" in any B2B conversation.

### 8. Frame "honest abstention" as the explicit product differentiator vs. AI picks services.
None of the credible comparables output picks. FiveThirtyEight published probabilities. Good Judgment outputs calibrated odds. Metaculus outputs crowd-aggregated Brier-scored forecasts. The "AI picks" tier (SportSphere HQ, Verdikt, CalibrSports) is a different, lower-credibility market. Explicit published abstention ("no edge detected; market-efficient on this market") is what earns placement in the FiveThirtyEight/Good Judgment credibility tier.

---

## Gotchas

- **Track record takes time; there is no shortcut.** Every comparable built their trust moat over 5-15 years of public calibration data. The honest pitch is: "we have [N months] of timestamped, auditable OOS results and are building the record." Overclaiming the record before it is long enough is a fast path to credibility destruction.
- **"Official data" designations are structurally blocked for solo operators.** Swish's MLB authorization and Second Spectrum's NBA official status require institutional relationships and compliance infrastructure. Never frame the product as competing on official data -- frame on COST-EFFECTIVE DERIVATION from public broadcast signals.
- **B2B sports analytics pricing is opaque and enterprise-gated.** Zelus/Teamworks, Sportlogiq, Stats Perform do not publish pricing. Assume $100K-$500K+/year for pro team contracts. Solo operator equivalent: tiered pricing starting at a price point accessible to media orgs and DFS research teams ($500-$5,000/month), not pro team contract scale.
- **The "beat the market" framing actively destroys the trust moat** with the calibration-first buyer (analytics depts, media, research). Use it and you get compared to SportsBettingDude.com, not Good Judgment Inc. The pregame market IS efficient (proven, 4 sports). The honest framing = in-game conditioning is the additive signal; pregame = match the close.
- **Solo operator brand requires consistent public output to compound.** Silver Bulletin works because Nate Silver publishes weekly. Good Judgment Open works because forecasters update daily. A solo operator who publishes a model and then goes quiet for 3 months destroys the compounding. Commit to a public cadence before launching.
- **Swish-style sportsbook API is inaccessible without regulatory compliance.** Selling a prediction API directly to sportsbooks requires being an authorized data provider (MLB, NBA, etc.) and passing compliance checks. The accessible buyers are media platforms, DFS operators (lower bar), and research orgs -- not the sportsbooks themselves.

---

## Sources

- [Silver Bulletin / Nate Silver - About](https://www.natesilver.net/about)
- [Good Judgment Inc - Superforecasting](https://goodjudgment.com/)
- [How Good Judgment Project Uses Superforecasting (Built In)](https://builtin.com/data-science/superforecasters-good-judgement)
- [Metaculus Review 2026 (Prediction Markets Reviews)](https://predictionmarketsreviews.com/reviews/metaculus)
- [Metaculus FAQ](https://www.metaculus.com/faq/)
- [Teamworks Acquires Zelus Analytics](https://teamworks.com/blog/teamworks-acquires-zelus-analytics/)
- [Teamworks Intelligence - Advanced Analytics for Pro Sports](https://teamworks.com/intelligence/)
- [Teamworks Acquires Sportlogiq (January 2026)](https://teamworks.com/blog/teamworks-acquires-sportlogiq/)
- [Sportlogiq Hockey Platform](https://www.sportlogiq.com/hockey/)
- [Genius Sports Acquires Second Spectrum](https://www.geniussports.com/newsroom/genius-sports-acquires-second-spectrum-the-official-data-tracking-and-analytics-provider-of-the-epl-nba-and-mls/)
- [NBA and Genius Sports / Second Spectrum Expanded Partnership](https://pr.nba.com/nba-genius-sports-second-spectrum-expanded-partnership/)
- [Swish Analytics - Intelligent US Sports Betting Solutions](https://swishanalytics.com/about.php)
- [Swish Analytics: Using Bet Request to drive Sky Bet engagement (SBC Americas)](https://sbcamericas.com/2021/04/12/swish-analytics-using-bet-request-to-drive-sky-bets-us-sports-engagement/)
- [FiveThirtyEight Wikipedia](https://en.wikipedia.org/wiki/FiveThirtyEight)
- [Polling Aggregators Compared 2026 (USPollingData)](https://uspollingdata.com/news/polling-aggregators-compared/)
- [Stats Perform / Second Spectrum Premier League Data Pool](https://www.statsperform.com/news/stats-perform-and-second-spectrum-launch-premier-leagues-most-comprehensive-data-pool/)
- [Top 21 Sports Analytics Companies (Inven)](https://www.inven.ai/company-lists/top-21-sports-analytics-companies)
- [Evidence on Good Judgment forecasting practices (AI Impacts)](https://aiimpacts.org/evidence-on-good-forecasting-practices-from-the-good-judgment-project/)
- [Good Judgment + Metaculus Collaboration](https://goodjudgment.com/owidproject/)
