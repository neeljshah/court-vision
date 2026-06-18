# Productization + Go-To-Market -- "Make It Something" as Calibration-Rigor Decision-Support

_Synthesis. 2026-06-16. Reads the three GTM briefs (gtm-comparables, gtm-trust-artifacts, gtm-distribution-monetization), `docs/research/competitive-landscape.md`, `briefs/ai-product-moats.md`, and Section 4 of `05-elevation-roadmap.md`. This is the concrete go-to-market: what the product IS, who to emulate, what trust artifacts ship first, the sequenced path from open calibration record -> audience -> B2B, the ranked honest monetization options with the regulatory line, and a 90-day plan that ties back to the eval-gate + track-record ledger blueprints. The binding constraint runs through every section: this is decision-support, NOT a picks/profit/edge service, and it NEVER implies a guaranteed dollar edge or ROI._

---

## 0. The non-negotiable that governs this entire document

The market this project competes against is efficient on price (proven 4/4 sports; pregame CLV ~ 0). The product is therefore NOT a bet, a pick, a tout, or an "edge." It is the **discipline made visible**: a calibrated multi-sport probability forecaster whose proof-of-work is a publicly auditable, timestamped, leak-free calibration record. The moment any public copy implies a guaranteed dollar edge or ROI, the trust moat collapses and the wrong audience arrives. That rule overrides every monetization temptation below. Honest "no edge detected; market-efficient here" is a **product feature**, not an apology.

---

## 1. What the product IS + the one-sentence positioning

### The one-sentence positioning

> **A four-sport calibrated probability forecasting system with transparent out-of-sample validation and in-game state conditioning -- decision-support for analysts, media, and sports organizations who value rigor, not picks.**

### What it concretely IS

- A **calibrated predictor**, not a picks engine. It outputs probabilities (and intervals), reliability diagrams, and a Brier score against the devigged market baseline -- never a "best bet."
- A **self-auditing track record**. Every prediction is logged before the event into an append-only, timestamped (git-committed) ledger, then scored against the closing line. The ledger is the centerpiece artifact, not the algorithm.
- A **decision-support tool around one hero interaction**: the pregame -> in-game probability update ("Pregame 47% | current state Q3, +8: 71% [interval]"). This is the single place the system measurably departs from the pregame close, because in-game state is information the close never had.
- A **proprietary-data substrate**: own broadcast-CV possession data (~$0.10/game vs six-/seven-figure vendors), a 660-player / 30-team intelligence vault, and the compounding prediction ledger -- an 18-36 month data flywheel a competitor starting today cannot buy.
- A **one-command reproducible proof** (`predict_matchup` + committed fixtures reproducing in < 60s, calibration context printed on startup) so a skeptic verifies the claim rather than trusting it.

### What it is explicitly NOT

- Not a "picks" or "best bets" service. Not a betting-edge / +EV / ROI pitch. Not a sportsbook-facing odds-origination API (regulatory + official-data blocks -- see Section 4). Not a broad sports-data aggregator competing with Sportradar/SportsDataIO on the data commodity. The differentiation is the model + calibration layer on top of public data, never the data itself.

---

## 2. Credible comparables + which to emulate as a solo operator

The one thing ALL credible comparables share: they publish the Brier score (or equivalent calibration metric) BEFORE any market-facing claim. That metric is the admission ticket to the credible tier; without it the product sits in the "AI picks" category regardless of technical quality.

| Comparable | What they sell | Trust mechanism | Solo-emulable? |
|---|---|---|---|
| **Silver Bulletin (Nate Silver)** | Freemium Substack probabilistic journalism (314K+ subs) | Personal brand + transparent "Model Talk" methodology + committing to a number and standing behind it | **YES -- the publication pattern is directly replicable** |
| **Good Judgment Inc.** | Calibrated forecasts to gov/enterprise; training/consulting | Public free track record (Good Judgment Open) -> earns the right to sell enterprise; 0.01 calibration error | **YES -- the freemium-funnel STRUCTURE, not the 40-person panel** |
| **Metaculus** | Institutional partnerships / commissioned forecasting | Published Brier 0.111 + proper scoring rules + WHO/CDC endorsement | **Partly -- the TRUST pattern (headline metric), not the free-to-user business model** |
| **Kalshi** | Regulated prediction-market exchange | CFTC regulation + auditable market prices | **As a BASELINE, not a model** -- devig Kalshi/closing lines as the calibration reference |
| **Zelus / Teamworks Intelligence** | Roster/contract/load models to 30+ front offices | 25+ PhDs + named endorsements (Billy Beane) + exclusivity | **Same BUYER, different SKU** -- can't replicate the org; can target the analytics director |
| **Sportlogiq** | CV-from-broadcast hockey/soccer metrics (97% NHL) | Penetration + patented CV + published validated-metric counts | **Structural parallel** -- "same signal, far cheaper infrastructure" is the exact pitch |
| **Second Spectrum / Genius Sports** | Official optical tracking to leagues/books | "Official" league designation | **NO -- this is the market ceiling, not a solo template**; never position on tracking accuracy, only cost/access |
| **Stats Perform / Opta** | Official data feeds + models to media/books | Decades of use + standard-setter + mandatory regulated-market status | **NO on official rights** -- borrow the "standardized definitions" rigor only |
| **Swish Analytics** | B2B parlay-pricing API to sportsbooks | MLB official distributor + named books + quant-credibility transfer | **The prediction-as-API ARCHITECTURE, not the sportsbook buyer** -- target media/DFS/research instead |

### Which to emulate as a solo operator -- ranked

1. **Silver Bulletin (publication pattern) -- emulate first and most directly.** Freemium personal site/Substack: free tier = methodology posts + one calibration update per cycle; paid/gated tier = full dashboard and history. No edge framing anywhere. Requires zero institutional backing and builds the audience that converts to B2B leads. Gotcha: ad-supported free probabilistic journalism is not durable (FiveThirtyEight closed 2025) -- go direct-reader/B2B, never ad-subsidized.
2. **Good Judgment (freemium -> enterprise funnel) -- emulate the structure.** Public free calibration record earns the right to sell advisory/licensing. The sports analog: public Brier scores on 4 sports -> credibility -> sell analytics access / B2B data / consulting. Cannot replicate the 40-superforecaster panel or 15 years of academic backing -- so never imply that scale.
3. **Metaculus (headline-metric trust) -- emulate the artifact discipline.** One auditable calibration number is the first thing any visitor sees. Pursue ONE institutional endorsement early (the "WHO uses Metaculus" equivalent: a single named analytics director or media org). Do not copy the free-to-user revenue model -- a solo operator needs revenue.
4. **Sportlogiq (CV-from-broadcast framing) -- emulate the cost argument.** "Possession-level NBA tracking from broadcast video at ~$0.10/game vs six-figure Sportradar/Second Spectrum contracts." Structurally identical, credible, and the right line in any B2B conversation. Cannot replicate 97% league penetration or patents.
5. **Swish (prediction-as-API architecture) -- emulate the shape, swap the buyer.** A clean API returning calibrated probabilities, sold to media/DFS/research orgs (lower regulatory bar), never to sportsbooks (official-data + compliance block solo access).

**Do NOT try to emulate:** Second Spectrum / Stats Perform official-data go-to-market, or any "official rights" positioning -- structurally blocked for a solo operator. Frame on cost-effective derivation from public broadcast signals instead.

---

## 3. The trust artifacts to ship first (and the tout anti-patterns to avoid)

Ship these in order. Each one is something no tout can fake; the contrast is itself the pitch. These map directly to the eval-gate (N1) and ledger (X3) blueprints in `05-elevation-roadmap.md`.

### Ship-first artifacts (ranked by credibility-per-effort)

1. **The reliability diagram (calibration curve).** Predicted probability vs observed frequency, >= 10 bins, sample count (n) per bin, sparse bins (n < 30) flagged, CORP-style uncertainty bands. Computed strictly on the OOS walk-forward holdout, per-sport AND per-market-type (ML vs totals separately -- aggregating hides miscalibration). This is the single most credible visual; it requires a real, large, undoctored history and cannot be fabricated. NOAA/ECMWF publish exactly this as their accountability artifact.
2. **Brier score vs the devigged market baseline.** "NBA pregame Brier 0.208; devigged market-implied close 0.198." Auditable, decomposable (Murphy: Reliability / Resolution / Uncertainty), cherry-proof. Report the event base rate alongside it, and a Brier Skill Score vs both climatology (raw skill) and the close (edge or its honest absence). This says more than any ROI screenshot ever could.
3. **The append-only, timestamped prediction ledger.** Every prediction logged BEFORE the event: timestamp (git commit hash = cryptographic proof), event id, predicted probability (a number, not a "lean"), market line at prediction time, outcome (filled after), per-row Brier contribution. Immutability via git commit history + branch protection (no force-push). This single practice destroys the entire tout industry -- none can produce one covering even a full season.
4. **One-command reproducible proof.** A committed fixture with inputs locked at a pre-game timestamp; `predict_matchup --fixture <date>` reproduces the calibrated probability + Brier contribution in < 60s on commodity hardware. Methodology-as-code beats any methodology document, because a document can describe a different system than what runs.
5. **Principled abstention surfaced in the UI.** "Market-efficient here; pregame Brier within measurement error of the close. No predicted edge; use for calibration context only." Documented (what test, what corpus, what significance level) so it is principled, not lazy silence.
6. **Methodology + KNOWN_LIMITATIONS transparency.** OOS methodology written explicitly (which seasons holdout, walk-forward, N games); a known-limitations doc (what the model does NOT know, where it fails, which markets are untested); data provenance with availability timestamps (rules out lookahead); calibration-technique choice per sport/market. The honest retraction record (+18.38% market-follow artifact, endQ3 0.119 Q4-leak, +54% L5-proxy) stays visible -- it is the proof a dishonest product could never publish.
7. **Calibration drift monitor.** Rolling 30/90-game Brier + ECE vs a stored baseline per sport, with public alerts ("Brier +0.008 from baseline; recalibrating"). Institutional-grade self-auditing; requires a stable baseline locked at launch to drift from.

### Tout anti-patterns to avoid (audit all public copy against this)

- **Language:** "lock," "units," "hot streak / 7-3 last 10," "+EV guaranteed," "inside information," "only X spots left," "money-back if under 55% ATS," "67% ATS this season" (vig-adjusted breakeven always unstated). None of these appear anywhere.
- **Artifacts:** phone ROI screenshots, ATS records with no start date, "verified by [affiliate site]," parlay win screenshots (survivorship bias), retroactively edited claims, "proprietary algorithm" with zero methodology.
- **Structure:** always having a prediction (never abstaining), never publishing calibration, subscription urgency over methodology, follower-count social proof over scored history.
- **The definitive test the product passes and every tout fails:** can you produce an append-only timestamped ledger covering a full season, scored against the close, with Brier on the OOS holdout? Yes -> credible tier. The tout's "no" is the entire competitive separation.

---

## 4. The sequenced GTM path + honest monetization, ranked + the regulatory line

### The sequence is non-negotiable: credibility -> audience -> revenue

Monetizing before a public calibration track record exists produces near-zero conversion. The track record IS the product; it enables every monetization path. The path that actually converts:

**Open calibration record -> niche community authority -> inbound B2B (media / analytics shops / teams) -> consulting or licensing deal.** Direct-to-consumer "picks" subscriptions are the wrong audience AND carry regulatory risk; they are excluded.

**Stage 1 (months 0-6) -- Open calibration record + audience.** Publish the append-only ledger publicly (repo or Substack), in the format: "NBA G6: NYK 47.3% (Brier baseline 0.208 | devigged market 0.198 | OOS walk-forward, no leakage)." Write 2-3 methodology posts (the funnel, the honest-reject discipline, the in-game conditioning layer) -- these are what B2B buyers vet before reaching out. ONE channel only for the first 90 days (Twitter/X -- the sports-analytics community, journalists, and team analytics people concentrate there); one thread per week minimum. Volume consistency beats channel breadth, and going quiet for 3 months destroys the compounding.

**Stage 2 (months 6-12) -- First revenue: consulting + small API deals.** Target a sports-media editorial engagement (a 4-week calibration analysis of a playoff/major event, $2K-$8K) -- revenue + a public case study + a media relationship. Open an API waitlist (form capturing the buyer's use case); serve the first 2-3 clients manually (file/email delivery) while hardening the API surface. Apply to the Sloan Sports Analytics Conference with a methodology paper/poster -- the single highest-credibility signal in the ecosystem.

**Stage 3 (months 12-24) -- B2B licensing + career optionality.** Close 2-4 B2B API clients at $1K-$3K/month each (by now the record is 12+ months old; reproducible proofs cut buyer risk to near zero). Evaluate the credibility->career path in parallel -- the two are not mutually exclusive and both benefit from the same record. Add a sponsored-research tier only after ~5K relevant followers or a Sloan-level signal.

### Honest monetization options -- ranked by solo-operator fit

1. **Credibility -> career (highest total ROI).** A solo-built, auditable, multi-year calibrated system with CV tracking is a stronger hiring signal than most credentials. Analytics roles at NBA/MLB teams ($150K-$300K), ML roles at sports-tech firms ($180K-$350K TC + equity), media analytics (ESPN/The Athletic). The Voulgaris precedent (solo NBA modeler -> Mavericks) is canonical. Not "monetization" in the SaaS sense, but the dominant ROI path -- and a team/media move often unlocks a licensing deal for the underlying system.
2. **Consulting + sponsored research (fastest time-to-revenue, 3-9 months).** 4-6 week engagements ($5K-$25K) building a calibrated layer on a client's data; co-authored media pieces; conference white papers. Closes on trust alone, no SLA. Gotcha: linear (time-for-money), caps builder capacity -- hard limit ~15 hrs/week, max 2-3 active engagements; use the revenue to buy time to build the API product, not to optimize consulting itself.
3. **B2B API / data licensing (highest ceiling, slowest close, 12-24 months).** Hybrid pricing: base access ($500-$2,000/month/client) + usage overage. Buyers: sports media (calibrated game probabilities for broadcast/editorial), analytics boutiques wanting a proprietary signal layer, DFS/fantasy platforms (calibrated prop projections framed as decision-support), mid-market books wanting in-game state modeling. Solo ceiling: 3-8 clients at $1K-$5K/month = $3K-$40K MRR; above ~$40K MRR clients expect SLAs that require a second person. Do NOT underprice -- a $200/month API competing with Sportradar's $50K+ contracts signals a toy; price to value (40+ analyst hours/month saved), not to compute cost.

**Realistic solo ceiling (18-36 months):** $5K-$20K MRR from a mix of API + 1-2 licensing deals + consulting. Scaling past ~$30K MRR solo typically needs a team or a media/data platform deal. Good Judgment and Parrot Analytics each took 4-7 years to meaningful B2B revenue -- compress with a rigorous public audit trail from day one, but do not promise a 12-month path to $100K ARR.

**What does NOT work (and why):** consumer picks subscriptions (regulatory risk + wrong audience + 60-80% annual churn + destroys the trust moat -- evaluated by the subscriber's P&L, not calibration); broad data aggregation vs Sportradar/SportsDataIO (official-data moat is unacquirable solo); a free dashboard with no conversion trigger (generates users, no revenue -- it must link explicitly to a B2B contact/paid tier); sponsored content as a primary channel before ~50K subscribers / 100K followers.

### The regulatory / positioning line: decision-support, NOT betting advice

Framing as **"decision-support + calibrated probability forecasting" is legally clean in the US**; framing as "betting advice" or a "picks service" triggers state gambling-advice regulations and potential SEC/CFTC scrutiny if financial instruments are involved.

- **Safe (decision-support):** "calibrated probability forecasting for sports outcomes," "AI-powered decision-support for media, analytics, and team operations," "walk-forward validated game-probability model with transparent OOS metrics," "in-game state conditioning: pregame 47% -> Q3 update 71%."
- **Unsafe (gambling advice):** "best bets tonight," "we give you an edge over the sportsbook," "ROI-positive picks," any claim of guaranteed profit or dollar edge.
- The reference framings are Sportradar's ("making betting more understandable and consumable," not edge generation) and NBC Peacock's "Performance View" ("predictive insights"). Any client-facing language that could read as individual gambling advice -- especially if consumers in regulated states can access it -- should be lawyer-reviewed before publication. The decision-support framing is not just marketing; it is legally material.

---

## 5. The 90-day "first credible public artifact" plan

Goal: in 90 days, have ONE public artifact a skeptic can audit and reproduce -- the open calibration ledger backed by the eval gate -- plus the audience seed that converts to inbound. This ties directly to blueprints N1 (Brier-Skill-Score CI gate + golden dataset) and X3 (calibration drift monitor + public track-record ledger) in `05-elevation-roadmap.md`. Nothing here implies a dollar edge; the deliverable is a calibration record, full stop.

### Weeks 0-2 -- Lock the measurement (eval gate, the keystone)
- Build the **Brier-Skill-Score CI gate** (N1): a pytest/`promptfoo` gate that runs the walk-forward backtest and fails (exit 1) if BSS vs the **devigged** close (Shin devig, not multiplicative on lopsided markets) drops below threshold on EITHER of two corpora. Bake in walk-forward + purge (same-team 48h) + embargo (3-day); assert `feature_availability_date < game_date` for every feature; report Brier +/- 95% CI clustered by game_id; DM test p-value vs the close.
- Build the **golden dataset**: ~100 game states in `tests/fixtures/` (true WP from PBP replay, post-game stats), git-tracked.
- This is the keystone: nothing downstream is credible until the number it publishes is gate-enforced and leak-free.

### Weeks 2-4 -- Build the ledger + the reproducible proof
- Stand up the **append-only, timestamped ledger** (X3): one CSV, one row per prediction logged BEFORE the event (timestamp/commit hash, event id, predicted prob, market line at prediction, outcome, per-row Brier). Enable branch protection / disable force-push so it is genuinely append-only.
- Wire the **calibration drift monitor**: rolling 30/90-game Brier + ECE vs a baseline locked now.
- Harden `predict_matchup --fixture` to the **< 60s reproducible proof** with calibration context printed on startup ("last OOS Brier: X; last recalibration: date").

### Weeks 4-8 -- Build the public-facing calibration page + start the cadence
- Produce the **reliability diagram per sport AND per market-type** (CORP bands, n-per-bin, sparse bins flagged), the **Brier-vs-devigged-baseline** headline, and the **honest-reject / market-efficient** statements -- as a single public page (the live board or a static site). Headline copy: "NBA pregame Brier 0.208 (devigged market 0.198) | honest OOS walk-forward, 2 corpora | in-game conditioning is the measured gap."
- Convert the existing KNOWN_LIMITATIONS + JOB_EVIDENCE_PACKET (with the retraction record visible) into a public methodology page.
- Begin the **Twitter/X cadence**: one thread per week -- a methodology breakdown, a calibration finding, or an honest miss ("predicted X, outcome Y, here is what the model missed and why"). One channel only.

### Weeks 8-12 -- Publish, invite scrutiny, seed inbound
- **Go public with the ledger + calibration page + reproducible proof scripts** so a skeptic can clone and verify (puts the burden of proof on them, not you).
- Publish the **first end-to-end methodology post**: the funnel, the honest-reject discipline, and the pregame->in-game hero interaction, citing the in-game literature ([Bayesian in-game NBA WP, arXiv 2207.05114](https://arxiv.org/abs/2207.05114); [Statsurge state-dependent framework](https://statsurge.substack.com/p/a-state-dependent-framework-for-basketball)).
- Open the **API/consulting waitlist** (use-case form) linked from the calibration page -- the only conversion trigger on an otherwise-free artifact.
- Optionally issue a **public challenge** ("here is the holdout; our NBA pregame Brier is 0.208; beat it") -- the strongest third-party-verification invitation.

### The 90-day definition of done
A public, append-only, gate-enforced calibration ledger; a per-sport/per-market reliability diagram with a devigged-baseline Brier headline; a < 60s reproducible proof anyone can run; a visible methodology + known-limitations + retraction record; and 8-12 weeks of consistent public cadence. That bundle is the "first credible public artifact" -- the Good Judgment Open / Metaculus-grade entry ticket that earns the right to everything in Section 4. It claims rigor and calibration quality; it claims no dollar edge or ROI, because the honest result is that the pregame market is efficient and the measured departure lives only in the in-game and freshness layers.

---

## Sources / References (preserved from the source briefs and roadmap)

**Comparables (gtm-comparables.md):**
- [Silver Bulletin / Nate Silver](https://www.natesilver.net/about) - [Good Judgment Inc.](https://goodjudgment.com/) - [Good Judgment Project (Built In)](https://builtin.com/data-science/superforecasters-good-judgement) - [Metaculus Review 2026](https://predictionmarketsreviews.com/reviews/metaculus) - [Metaculus FAQ](https://www.metaculus.com/faq/) - [Teamworks Acquires Zelus](https://teamworks.com/blog/teamworks-acquires-zelus-analytics/) - [Teamworks Intelligence](https://teamworks.com/intelligence/) - [Teamworks Acquires Sportlogiq](https://teamworks.com/blog/teamworks-acquires-sportlogiq/) - [Sportlogiq Hockey](https://www.sportlogiq.com/hockey/) - [Genius Sports Acquires Second Spectrum](https://www.geniussports.com/newsroom/genius-sports-acquires-second-spectrum-the-official-data-tracking-and-analytics-provider-of-the-epl-nba-and-mls/) - [Swish Analytics](https://swishanalytics.com/about.php) - [Swish Bet Request (SBC Americas)](https://sbcamericas.com/2021/04/12/swish-analytics-using-bet-request-to-drive-sky-bets-us-sports-engagement/) - [FiveThirtyEight (Wikipedia)](https://en.wikipedia.org/wiki/FiveThirtyEight) - [Stats Perform + Second Spectrum data pool](https://www.statsperform.com/news/stats-perform-and-second-spectrum-launch-premier-leagues-most-comprehensive-data-pool/) - [Good Judgment forecasting practices (AI Impacts)](https://aiimpacts.org/evidence-on-good-forecasting-practices-from-the-good-judgment-project/)

**Trust artifacts (gtm-trust-artifacts.md):**
- [Stable reliability diagrams (PNAS)](https://www.pnas.org/doi/10.1073/pnas.2016191118) - [Reliability diagrams + score decompositions (arXiv 2008.03033)](https://arxiv.org/pdf/2008.03033) - [Brier Score (Emergent Mind)](https://www.emergentmind.com/topics/brier-score) - [Reliability Diagrams (NOAA Rapid Refresh)](https://ruc.noaa.gov/stats/prob/beta/reliabilitydiagrams/) - [Forecast Verification MDL Lab (NOAA)](https://vlab.noaa.gov/web/mdl/fv) - [The Science of Superforecasting (Good Judgment)](https://goodjudgment.com/about/the-science-of-superforecasting/) - [Good Judgment Open](https://www.gjopen.com/) - [Metaculus Pro Forecasters](https://www.metaculus.com/pro-forecasters/) - [Avoiding Sportsbetting Scams (WIN DAILY)](https://windailysports.com/avoiding-sportsbetting-scams-how-to-spot-fake-tips/) - ["Calibeating" (arXiv 2209.04892)](https://arxiv.org/abs/2209.04892)

**Distribution + monetization (gtm-distribution-monetization.md):**
- [Sportradar Sports Tech Momentum 2025 (SportsPro)](https://www.sportspro.com/analysis/betting/sportradar-sports-tech-innovation-nba-mlb-ioc/) - [Parrot Analytics Sports Demand](https://www.parrotanalytics.com/insights/parrot-analytics-unveils-sports-demand-powering-the-future-of-sports-analytics-strategy-and-valuation-globally/) - [Sports Analytics Market (Precedence Research)](https://www.precedenceresearch.com/sports-analytics-market) - [Sports Analytics Market (Mordor)](https://www.mordorintelligence.com/industry-reports/sports-analytics-market) - [API Monetization in the AI Age (L.E.K.)](https://www.lek.com/insights/tmt/us/ei/seats-calls-why-api-monetization-next-pricing-frontier-ai-age) - [AI-First B2B SaaS Economics 2026 (Monetizely)](https://www.getmonetizely.com/blogs/the-economics-of-ai-first-b2b-saas-in-2026) - [B2B Software Monetization 2025 (Nalpeiron)](https://nalpeiron.com/blog/fascinating-insights-into-b2b-software-monetization-in-2025) - [Building SaaS In Public (PayPro Global)](https://blog.payproglobal.com/building-saas-in-public) - [2026 Sports Industry Outlook (Deloitte)](https://www.deloitte.com/us/en/insights/industry/technology/technology-media-telecom-outlooks/sports-industry-outlook.html) - [Solo-Founder Renaissance 2026 (ByTheMag)](https://bythemag.com/the-solo-founder-renaissance-in-2026/)

**Moats + landscape + roadmap (internal + briefs):**
- `briefs/ai-product-moats.md` - `docs/research/competitive-landscape.md` - `05-elevation-roadmap.md` Section 4 - [AI Moats 2026 (Valtorian)](https://www.valtorian.com/blog/ai-moats-2026) - [Data Flywheel Moat (Rohit Prabhakar)](https://www.rohitprabhakar.com/blog/market-of-one-data-flywheel-competitive-moat/) - [Bayesian in-game NBA WP (arXiv 2207.05114)](https://arxiv.org/abs/2207.05114) - [Statsurge state-dependent framework](https://statsurge.substack.com/p/a-state-dependent-framework-for-basketball)
