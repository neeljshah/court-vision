# GTM Trust Artifacts: Building Credibility for a Probabilistic Forecasting Product
_Researched 2026-06-16. Scope: What concrete artifacts build lasting trust for a calibrated multi-sport prediction platform, the anti-patterns that destroy it, and how "honest reject" becomes a product feature. Maps to this project's existing artifacts._

---

## TL;DR (highest-leverage takeaways)

- **The reliability diagram is the single most credible visual artifact.** A published calibration curve (predicted probability vs. observed frequency, with sample counts per bin) that hugs the diagonal is a proof no tout can fake -- it requires a real, large, undoctored prediction history.
- **Brier score vs. a market baseline is the single most credible number.** "Our NBA pregame Brier = 0.208; market-implied close = 0.198" says more than any ROI screenshot. It is auditable, decomposable, and cannot be cherry-picked without statistical detection.
- **An append-only timestamped ledger is the backbone of the trust moat.** Every prediction logged before the event with a timestamp (ideally a git commit hash) is immune to post-hoc survivorship bias. The entire tout industry is destroyed by this single practice -- they cannot produce one.
- **Principled abstention ("market efficient here; no signal") is the strongest credibility differentiator available.** Every serious forecasting institution (NOAA, Metaculus, Good Judgment) publishes its abstentions and its misses. Touts never do. Saying "we found nothing here" in public is proof of rigor.
- **One-command reproducible proofs turn methodology claims into verifiable facts.** A skeptic who can run `predict_matchup --fixture 2026-06-10` and get the same Brier-scored output in under 60 seconds has no reason to doubt the broader methodology.
- **The anti-patterns that scream "scam" are easy to catalog and easy to avoid.** Units, ROI screenshots, hot-streak language, "lock," "+EV guaranteed," urgency tactics, and opaque methodology are the exact opposite of what this product does. The contrast itself is the pitch.
- **Calibration over time (drift monitoring) signals institutional-grade self-auditing.** A product that publicly tracks its own degradation is the one that earns long-term trust from analysts, media, and pro orgs.

---

## Key Findings

### 1. The Reliability Diagram: What It Is and Why It Cannot Be Faked

A reliability diagram (also called a calibration curve) plots predicted probability on the x-axis against observed frequency on the y-axis across binned probability intervals. Perfect calibration = all points on the diagonal. Deviation above the diagonal = under-confident (predicting 60% when it happens 80% of the time). Deviation below = over-confident.

**Why it cannot be fabricated:**
- It requires a large, undoctored corpus of predictions made BEFORE outcomes were known.
- Statistical uncertainty bands (bootstrap or asymptotic) expose sparse or cherry-picked bins immediately.
- The CORP approach (Consistent, Optimally-binned, Reproducible) generates provably valid bins with uncertainty quantification -- a published CORP diagram with the code is essentially self-certifying.
- NOAA and the European Centre for Medium-Range Weather Forecasts (ECMWF) publish reliability diagrams for public weather forecast verification as the primary accountability artifact. This is the scientific standard.

**Construction best practices:**
- Use at least 10 probability bins; show sample count (n) per bin -- sparse bins with n < 30 must be flagged.
- Add a reference histogram (sharpness) below the main diagram to show how often the model commits to extreme probabilities.
- Pair with ECE (Expected Calibration Error): sum of |predicted - observed| weighted by bin size. Elite threshold: < 0.05.
- Always compute on the OOS walk-forward holdout, never on training data.
- Run per-sport and per-market-type separately -- a well-calibrated NBA model may be miscalibrated on totals vs. moneylines; aggregating hides this.

### 2. Brier Score vs. Market Baseline: The Auditable Number

The Brier Score (BS = mean squared error of probability predictions, lower = better, 0.25 = coin flip for balanced binary outcomes) is the primary single-number credibility signal for probabilistic forecasting. It decomposes into three interpretable components via Murphy decomposition:

- **Reliability:** how close predicted probabilities are to observed frequencies (calibration error component).
- **Resolution:** how much the predictions deviate from the climatological base rate in the right direction (skill component).
- **Uncertainty:** the irreducible variance in outcomes (fixed by the sport/market).

**The market baseline is the honest comparison.** Publishing "our Brier = 0.208 vs. market-implied Brier = 0.198" is simultaneously honest (we do not beat the close pregame) and credible (we are within 5% of the theoretical lower bound that efficient markets can achieve). It signals:
- We know what market efficiency means.
- We computed the comparison correctly (devigged implied probabilities, same holdout set).
- We are not hiding a gap.

**Brier Skill Score (BSS)** = 1 - (BS / BS_reference) benchmarks against a specific reference. BSS vs. climatology shows raw skill; BSS vs. market-implied close shows edge (or its absence). Reporting both gives experts a full picture.

**Important:** Brier score interpretation depends on base rate. Always report the event base rate alongside BS. A BS of 0.20 on a 50/50 binary is very different from 0.20 on a 10% rare event. Contextualize per market type.

### 3. The Append-Only Timestamped Ledger: The Backbone

The defining difference between a credible forecaster and a tout is a timestamped, uneditable prediction record. Superforecasting research (Good Judgment Project, GJP) found that:
- Forecasters who systematically scored their own predictions showed year-over-year correlation of 0.65 in accuracy (it is a measurable, stable skill).
- Superforecasters achieved average calibration of 0.01 -- the average difference between their stated probability and actual frequency -- provably only achievable through real, scored predictions over time.
- Accountability was the key mechanism: "It is harder to weasel out of" a precise probabilistic prediction than a vague claim.

**What the ledger must contain (minimum):**
- Prediction timestamp (before event start).
- Game/event identifier.
- Predicted probability (not a "pick" or "lean" -- a number).
- Market line at time of prediction (for CLV context).
- Outcome (filled after).
- Brier score contribution per row.

**Immutability options ranked by credibility:**
1. Git commit of the prediction file before the game (commit hash = cryptographic timestamp proof).
2. Append-only CSV with a hash chain (each row hashes the previous row + content).
3. Public GitHub file with commit history (open for auditors to check).
4. Third-party timestamping (e.g., OpenTimestamps on a daily hash of the ledger file).

Even option 3 alone defeats every tout in existence. No manual editing of a git commit history goes undetected.

### 4. One-Command Reproducible Proofs: Methodology as Code

A reproducible proof is a test that a skeptic can run and get the same number. For a prediction platform this means:

- A committed fixture (a specific past game with inputs locked at a pre-game timestamp).
- A single CLI command that reproduces the prediction from those inputs.
- The output includes the calibrated probability AND the Brier score contribution on that game.
- Execution time under 60 seconds on commodity hardware.

This is the "show your work" standard in the scientific community. NOAA's Forecast Verification Lab publishes the code and the verification datasets together. The Good Judgment Project published methodology papers alongside the scored prediction archives.

**Why this matters more than a methodology document:** A methodology document can describe a different system than what runs in production. Reproducible code that produces the verified number cannot.

### 5. Metaculus/Good Judgment Model: Calibration Leaderboards and Transparent Failure

Metaculus and Good Judgment Open have built the most credible forecasting trust models in existence. Their pattern:
- Every forecast is scored on a proper scoring rule (Brier + log score).
- Calibration curves per user are public.
- Pro Forecaster status requires demonstrating excellent calibration AND writing detailed reasoning for predictions -- the reasoning must survive public scrutiny.
- Misses are as public as hits. There is no "delete the bad call."
- The leaderboard combines peer accuracy, baseline accuracy (vs. market/prior), and commentary quality -- rewarding rigorous reasoning, not just outcomes.

**The credibility mechanism:** Because the scoring is continuous and public, a forecaster who is genuinely well-calibrated looks dramatically different from one who cherry-picks. The track record is self-auditing.

### 6. Calibration Over Time: Drift Monitoring as a Trust Signal

A product that monitors its own calibration degradation and publishes the results is demonstrating institutional-grade self-auditing. This matters because:
- Models drift as sports change (roster moves, rule changes, coaching changes).
- A product that flags its own drift before users notice it is credible in a way no tout can mimic.
- Weekly drift alerts ("Brier increased 0.008 from baseline; recalibrating") are a trust feature, not an operational detail.

**What to track:**
- Rolling 30-game and 90-game Brier vs. historical baseline per sport.
- ECE drift per probability bin (which region is degrading?).
- Calibration curve shape change (are we becoming over-confident at high probabilities?).
- Brier decomposition drift: is it calibration (fixable with recalibration) or resolution (model knowledge) degrading?

### 7. Methodology Transparency: What Earns Expert Trust

Domain experts (sports analytics teams, media, pro org analysts) need to evaluate methodology before trusting outputs. The trust-building artifacts in order of impact:

1. **OOS validation methodology written up explicitly:** which seasons are holdout, which walk-forward, how many games.
2. **Known limitations document:** what this model does NOT know, where it fails, which markets are explicitly untested.
3. **Honest error analysis:** where does the model over-predict? Under-predict? On which market shapes?
4. **Data provenance:** where does each input come from, and when was it available (to rule out lookahead bias)?
5. **Calibration technique documentation:** Platt Scaling vs. Isotonic vs. Beta -- why this choice for this sport/market, and what is the holdout set for calibration?

The KNOWN_LIMITATIONS pattern (this project already has `docs/KNOWN_LIMITATIONS.md`) is the highest-signal transparency artifact for an expert audience. It is the one thing a dishonest product could never publish.

### 8. Third-Party / Independent Verification

The strongest possible credibility artifact is a third party who can reproduce your numbers without your help. Options:
- **Academic co-author or collaborator** who validates the methodology independently.
- **Public GitHub with full validation scripts** that a skeptic can clone and run.
- **An open-access holdout dataset** (anonymized) that any forecaster can benchmark against.
- **A public challenge** (e.g., "our NBA pregame Brier is 0.208; here is the holdout dataset; beat it and we will pay attention to your method").

Even without formal third-party review, publishing the code and the holdout dataset puts the burden of proof on the skeptic, not on you.

---

## The Anti-Patterns: How Touts Destroy Trust

These are the specific signals that immediately mark a service as a tout/scam and must be avoided entirely:

**Language patterns that scream "fake":**
- "Lock" (implies certainty; probability prediction has no locks)
- "Units" (implies a standardized betting unit system optimized for ROI)
- "Hot streak" or "7-3 last 10" (cherry-picked window, survivorship bias, no context)
- "+EV guaranteed" (logically impossible to guarantee positive expected value)
- "Inside information" (regulatory risk + logical impossibility in efficient markets)
- "Only X spots left" (urgency without substance)
- "Money-back guarantee if we go under 55% ATS" (implies ATS is the metric; real forecasters use calibration)
- "Our model is 67% ATS this season" (what is the vig-adjusted breakeven? Almost always unstated)

**Artifact anti-patterns:**
- ROI screenshots from a phone (unverifiable, unaudited, cherry-picked)
- ATS record without a starting date (when does the clock start? What was the variance?)
- "Verified by [site name]" from an affiliate site (the verifier is paid by the tout)
- Parlay screenshots (parlays have high variance; showing only winners is survivorship bias)
- "3-0 on CBB last night" without a prediction ledger going back more than 2 weeks
- Hiding misses by changing the claim retrospectively ("I said under 218, the line moved to 217.5, so I win")
- No methodology description at all -- just "proprietary algorithm"

**Structural anti-patterns:**
- Always having a prediction (never abstaining)
- Never publishing calibration metrics
- Subscription urgency over methodology transparency
- Social proof (follower counts, screenshots of subscriber messages) over scored prediction history

**The definitive test:** Can the tout produce an append-only timestamped prediction ledger covering at least one full season, scored against the closing line, with Brier computed on the OOS holdout? Zero tout services in existence can pass this test.

---

## "Honest Reject / Market Efficient Here" as a Credibility Feature

The single biggest differentiator from any tout service is publishing when the model finds nothing.

**Why this works:**
- It is direct evidence of honest OOS methodology. A tout cannot say "we found no edge here" because their revenue model depends on always having a pick.
- It signals market efficiency awareness -- the sophisticated audience (analytics teams, media, pro orgs) respects this framing.
- It is mathematically consistent with the product's claims. If markets are efficient pregame (proven: 4/4 sports), saying so is not a weakness -- it is the accurate description of a well-calibrated system operating at the boundary of information.
- It limits liability. A product that says "we do not claim to beat the market" cannot be accused of misleading bettors.
- It builds the right audience. Users who value "honest reject" are analytics professionals and rigorous analysts. That audience values calibration over picks, pays for access to the methodology, and does not churn when a prediction loses.

**How to frame it in the UI:**
- "NBA pregame moneyline: market-efficient. Our pregame Brier (0.208) is within measurement error of the market-implied Brier (0.198). No predicted edge; use for calibration context only."
- "In-game probability update available: pregame 47% -> Q3+8 74% [calibrated, 0.31 Brier improvement over pregame baseline on similar states]."

The pregame -> in-game delta is where the measurable, calibrated signal lives. That is the hero output. The honest reject on pregame makes the in-game update more credible, not less.

---

## How This Project Already Has the Artifacts (Mapping)

| Trust Artifact | This Project's Implementation | Gap / Enhancement |
|---|---|---|
| Reliability diagram | Calibration curves computed per sport in walk-forward validation (season_backtest.py) | Publish to the live board as the hero visualization; add CORP-style uncertainty bands |
| Brier vs. market baseline | NBA pregame Brier 0.208 vs. market 0.198 (from season backtest 2026-06-10); 4/4 sports computed | Add per-market-type decomposition (ML vs. totals); add Brier Skill Score vs. market |
| Append-only timestamped ledger | vault/Improvements/ logs per game; git commit history exists | Formalize as a single append-only CSV with commit hash per row; make it the product's public artifact |
| One-command reproducible proofs | predict_matchup + committed fixtures reproduce in <60s; proofs committed per sport | Add a CLI startup banner printing "last OOS Brier: X; last recalibration: date" |
| Methodology transparency | KNOWN_LIMITATIONS.md; JOB_EVIDENCE_PACKET.md (adversarially audited); honest retraction of +18.38% ROI | Convert JOB_EVIDENCE_PACKET to a public-facing methodology page; keep retraction section visible |
| Known limitations | docs/KNOWN_LIMITATIONS.md exists | Make it a prominent link from the live board; update per sport after every major recalibration |
| Principled abstention | "Market efficient; 60/60 REJECT platform-wide" is the product's honest claim | Surface in the live board per-market; frame as "calibration context mode" not failure |
| Calibration drift monitoring | Not yet systematic | Add weekly Brier drift check script; surface alert on the board when drift exceeds threshold |
| Third-party verification | Not yet | Publish the walk-forward holdout scripts to the public repo; any skeptic can verify |
| Anti-pattern avoidance | No units, no ROI claims, no locks anywhere in the codebase or docs | Audit README and any public-facing copy for inadvertent tout language |

---

## Gotchas

- **Brier score is not enough alone.** A model can achieve a low Brier score by being well-calibrated on common outcomes but terrible at extreme probabilities. Always publish the full calibration curve AND the Brier decomposition.
- **Sample size gates everything.** A reliability diagram with fewer than ~500 predictions is not statistically meaningful. Each probability bin needs n >= 30 for the uncertainty bands to be honest. Do not publish curves from small samples without clearly flagging the uncertainty.
- **Calibration on training data is theater.** The holdout must be strictly OOS -- ideally a full separate season, not just a random split of the same corpus. This is the single most common failure mode in published sports model credibility artifacts.
- **"We beat the market" framing destroys the trust moat even if technically true.** The moment the product sounds like a tout, the right audience leaves and the wrong audience arrives. Brier vs. market baseline is the right frame -- it describes the relationship accurately without implying exploitability.
- **Abstention must be principled, not lazy.** Saying "market efficient here" is credible only if the methodology is documented (what test was applied, what corpus, what significance level). An undocumented abstention is just silence.
- **Drift monitoring requires a stable baseline to drift from.** Establish the baseline Brier/ECE per sport at launch and store it. Without a reference point, drift monitoring is meaningless.
- **Third-party verification requires the holdout dataset to be shareable.** If it contains PII or licensed data it cannot be published. Plan data provenance from the start so the verification holdout is clean.
- **The ledger must be truly append-only.** Any ability to retroactively edit predictions (even accidentally) invalidates it. A git repo with force-push enabled is not append-only. Use branch protection rules on the public prediction ledger branch.

---

## Sources

- [Stable reliability diagrams for probabilistic classifiers (PNAS, Kuchibhotla & Pati)](https://www.pnas.org/doi/10.1073/pnas.2016191118)
- [Evaluating probabilistic classifiers: Reliability diagrams and score decompositions revisited (arXiv 2008.03033)](https://arxiv.org/pdf/2008.03033)
- [Brier Score in Probabilistic Forecasting -- Emergent Mind topic summary](https://www.emergentmind.com/topics/brier-score)
- [Probability Verification -- Reliability Diagrams (NOAA Rapid Refresh)](https://ruc.noaa.gov/stats/prob/beta/reliabilitydiagrams/)
- [Forecast Verification -- MDL Virtual Lab (NOAA)](https://vlab.noaa.gov/web/mdl/fv)
- [Evidence on good forecasting practices from the Good Judgment Project (AI Impacts)](https://aiimpacts.org/evidence-on-good-forecasting-practices-from-the-good-judgment-project/)
- [The Science of Superforecasting (Good Judgment)](https://goodjudgment.com/about/the-science-of-superforecasting/)
- [Good Judgment Open -- forecasting platform](https://www.gjopen.com/)
- [Metaculus Pro Forecasters -- methodology and selection](https://www.metaculus.com/pro-forecasters/)
- [Metaculus FutureEval Methodology](https://www.metaculus.com/futureeval/methodology/)
- [Avoiding Sportsbetting Scams: How to Spot Fake Tips (WIN DAILY Sports)](https://windailysports.com/avoiding-sportsbetting-scams-how-to-spot-fake-tips/)
- [Navigating Sports Betting App Scams (Bolster AI)](https://bolster.ai/blog/betting-app-scams)
- ["Calibeating": Beating Forecasters at Their Own Game (arXiv 2209.04892)](https://arxiv.org/abs/2209.04892)
- [Predictor-Rejector Multi-Class Abstention: Theoretical Analysis (arXiv 2310.14772)](https://arxiv.org/pdf/2310.14772)
- [Play Money and Reputation Systems (Scott Alexander / Astral Codex Ten)](https://www.astralcodexten.com/p/play-money-and-reputation-systems)
