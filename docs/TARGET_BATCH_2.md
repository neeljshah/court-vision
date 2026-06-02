# Outreach Target Batch #2 — researched 2026-06 (real companies, tailored messages)

> **Before you send anything:** (1) VERIFY there's a current opening + that the company is still active (30 sec on
> their careers page / LinkedIn). (2) VERIFY the exact handle / careers URL is still live — handles and pages move.
> (3) **Never email a guessed address.** Where no real public email is listed, the channel below says "DM the
> founder" — do that, don't invent an address. (4) **Referral-first** always: a warm intro converts 5–10× a cold
> message; if you know anyone at/near these, ask for the intro before DMing cold.
>
> Lead with the engineering + the self-auditing validation methodology; never the retracted numbers. Track replies,
> not sends.
>
> **Dedupe note:** Companies already in [TARGET_BATCH_1](TARGET_BATCH_1.md) are intentionally omitted here —
> SkillCorner, Bron, PlayVision, SPORTLOGiQ, NEX/HomeCourt, Genius Sports, Second Spectrum. (Several appeared again in
> this round's research; they're dropped to avoid duplicate outreach.) Companies that surfaced in more than one
> category below are listed once, in their best-fit category, with a cross-fit note.

---

## A. Sports CV / broadcast-video tracking

### ⭐ A1. ReSpo.Vision (Warsaw) — *bullseye: single-broadcast-camera → 3D tracking, with LIVE CV reqs*
**What:** Deep-tech startup extracting hyper-accurate 3D positional + skeletal tracking (50+ body points/player)
from a SINGLE broadcast-style camera. FIFA-certified, ~$5M raised (2025). Football today, expanding.
**Why it fits you:** The closest single-camera-broadcast match to your pipeline — monocular video → court/3D
coordinates, multi-object tracking, re-ID, homography/calibration on moving broadcast cameras. Their open
Principal/Senior ML Engineer reqs literally name video tracking, broadcast tech, YOLO/Detectron2, detection,
segmentation, 3D reconstruction, PyTorch, real-time/low-latency. CTO Wojciech Rosiński is a Kaggle Master who hires
on demonstrated CV output, not credentials. Basketball isn't their sport (football), but the skills map 1:1.
**Best channel:** Apply via the careers form (Principal ML Engineer, Warsaw, hybrid) — verify the live URL, listed as
`respovision.com/careers`. For the warm CV-hiring decision, DM **CTO Wojciech Rosiński** (find via the ReSpo.Vision
LinkedIn company page: `linkedin.com/company/respo-vision`). CEO/co-founder Paweł Österreicher:
`linkedin.com/in/pawel-osterreicher-98872114/`. Real public email: `contact@respo.vision`. Site: `respo.vision`.
**Tailored hook:**
> I built the same monocular-broadcast-to-3D problem you've productized — YOLOv8 detection, SIFT homography for
> moving-camera court calibration, Kalman+Hungarian tracking and OSNet re-ID — solo, end to end, with a walk-forward /
> shadow-logging validation harness that catches my own overclaims before they ship. Your single-broadcast-camera
> tracking stack is the exact problem I've been obsessed with for ~3 months. Repo: github.com/neeljshah/court-vision

### A2. Track160 (Tel Aviv) — *single fixed-camera → 3D skeletons + ball + event tagging*
**What:** CV startup (Series A, ~$5M) reconstructing games in 3D from a single fixed-viewpoint camera — players as 3D
skeletons, ball tracking, automatic event tagging, no wearables/operators. Football-first, FIFA-backed.
**Why it fits you:** Single-camera 3D player+ball tracking with skeleton/pose extraction and auto event tagging is
squarely your wheelhouse (tracking, pose, re-ID, homography). Chairman Miky Tamir is a 30-year CV serial founder
(SportVU, Pixellot) — a team that respects raw CV capability over pedigree.
**Best channel:** Real public email `info@track160.com`. Warmer: DM chairman **Miky Tamir** or CEO **Eyal Ben Ari**
via the Track160 company page `linkedin.com/company/track160`. Profile: startup-nation-central finder page for
"track160-ltd".
**Tailored hook:**
> Your single-viewpoint 3D skeleton reconstruction is exactly what I built solo from NBA broadcast video —
> Kalman+Hungarian tracking, OSNet re-ID, homography to court space — and I'd love to push it on your optical tracking
> stack.
**Caveat:** A few years post-Series A; headcount may be tight. Confirm they're actively hiring before investing heavily.

### A3. SportsVisio (Boston, fully remote) — *basketball-first CV stats + highlights from a phone*
**What:** Fully-remote CV sports-stats startup (~$9.3M raised; $3.2M seed extension Jun 2025; Sony Innovation Fund,
Sapphire) generating real-time player stats + automated highlights from phone/single-camera video — BASKETBALL-FIRST.
Founded by ex-DARPA engineers.
**Why it fits you:** Basketball-priority + your exact domain (any-camera/broadcast video → player stats + highlights
via detection, tracking, re-ID, action recognition), arguably harder than clean broadcast (consumer phone footage),
so your unknown-camera homography + re-ID transfer directly. Fully remote → a no-degree US builder is hireable on output.
Strongest basketball + remote combination in this round.
**Best channel:** Careers page `sportsvisio.com/careers` (watch their LinkedIn `linkedin.com/company/sportsvisio` —
they say to follow it; reqs come and go). DM founder/CEO **Jason Syversen** (ex-DARPA) via the company LinkedIn, or use
the `sportsvisio.com/contact` form. **No public personal email found — do not fabricate one.**
**Tailored hook:**
> You're building basketball stats + highlights from a single phone camera — I built the full broadcast-video-to-court-
> coordinates CV pipeline for NBA games solo (YOLOv8, SIFT homography, tracking, OSNet re-ID) and would be a
> force-multiplier on your CV team.
**Caveat:** Careers page may show zero open roles — this is a get-on-the-radar / network-in play, not always an immediate apply.

### A4. SportAI (Oslo) — *camera-agnostic CV-analysis API over existing feeds*
**What:** CV/ML startup (~$5.7M raised; $3M round late 2025; advisor/investor Casper Ruud, Magnus Carlsen) offering
camera-agnostic technique analysis, match stats, tactical insight and auto-highlights as an API layered over existing
court-camera/broadcast feeds. Racket-sports-first, expanding.
**Why it fits you:** Camera-agnostic, API-first CV over broadcast/court feeds matches your CV-pipeline + ML-serving
profile (you built both). Small (~10-person) team where a builder owning pose/technique CV + the backend API is
high-leverage. Honest caveat: core CV is single-athlete pose/technique, not multi-object tracking + homography +
re-ID, so it's a partial-skills match; recent hiring has skewed B2C product, not CV-eng.
**Best channel:** Real public email `contact@sportai.com`. DM CEO/co-founder **Lauren Pedersen**
(`linkedin.com/in/laurenmartinpedersen/`); CTO **Felipe Longe** is the CV-technical decision-maker (find via company
page `linkedin.com/company/sportai-com`). Site: `sportai.com`.
**Tailored hook:**
> Your camera-agnostic API that overlays AI analysis on existing feeds is the productized version of what I built solo —
> broadcast video to behavioral features plus the full ML serving stack — and I can own both the CV and the backend.
**Caveat:** Verify the role TYPE is CV/backend engineering, not product, before investing.

### A5. Sportlight Technology (Bicester/Oxford, UK) — *LiDAR + CV athlete tracking, most of the EPL*
**What:** Sports-tech startup (~£4M+ raised) using patented LiDAR + AI/CV for hyper-accurate athlete tracking, load
management, tactical analysis; working with most of the English Premier League.
**Why it fits you:** Has a dedicated CV department building detection/tracking algorithms (LiDAR fused with CV), so
your tracking / sensor-fusion / ML-validation stack is directly relevant. CEO Raf Keustermans is a repeat founder
(Plumbee, acquired by Sony) who hires builders. Looser fit (LiDAR-led, football, not pure broadcast-CV or basketball) —
flagged honestly.
**Best channel:** DM CEO **Raf Keustermans** via LinkedIn (he writes for VentureBeat under Sportlight — easy to
verify), or the CV-team lead. Company LinkedIn `uk.linkedin.com/company/sportlighttechnology`. Site/careers
`sportlight.ai`. **No public hiring email found — LinkedIn DM is the realistic channel.**
**Tailored hook:**
> Your CV team fuses LiDAR with vision for athlete tracking — I built a full broadcast-vision tracking pipeline
> (detection, Kalman+Hungarian, re-ID, homography) solo and would bring strong multi-object-tracking and ML-validation
> rigor to that fusion problem.

### A6. Muybridge (Oslo) — *real-time "weightless" virtual broadcast cameras, deployed in the NBA*
**What:** Deep-tech startup (Series A ~$16M round / ~$24.8M total, ~30 people) building a software-defined
multi-camera system that generates virtual broadcast angles in real time via CV + volumetric capture; deployed across
NBA, NHL, ATP, PGA.
**Why it fits you:** Real-time CV, camera calibration/geometry and volumetric reconstruction across live sports
(including the NBA) overlap heavily with your homography/calibration + real-time tracking work. Bigger/better-funded =
more structured hiring; explicitly scaling the team. Honest caveat: recent public hiring emphasis was
sales/partnerships — confirm an open CV/engineering req.
**Best channel:** DM a founder — **Håkon Espeland** or **Anders Tomren** (referenced in Fast Company coverage) — or the
CV/engineering lead, via LinkedIn. Site `muybridge.com/about` + `muybridge.com`. **No public hiring email confirmed.**
**Tailored hook:**
> Your weightless-camera system lives and dies on real-time camera geometry and reconstruction — the same
> calibration/homography and tracking math I built solo to turn moving NBA broadcast feeds into court coordinates, and
> I'd love to work on it at live-broadcast scale.

---

## B. Sports-betting / quant ML

### ⭐ B1. Kalshi (US) — *bullseye: regulated prediction exchange with a LIVE Sports Operations Engineer req*
**What:** Regulated US prediction-market exchange (events, economics, fast-growing sports vertical) with an affiliated
market-making/quant desk.
**Why it fits you:** Strongest fit in the category. Open roles for **Sports Operations Engineer** (sports data
pipelines, scheduling, sports logic), **Software Engineer, Data**, and **Quantitative Developer** (autonomous
market-making + forecasting). Your exact stack — sports data pipelines, leak-free walk-forward validation, model
serving, EV/edge thinking vs live lines — maps onto pricing sports event markets; the QR/MM JD even names
prediction/sports-betting market experience as ideal. No-degree is hireable here on output (strongest with a referral).
**Best channel:** Apply on the Greenhouse board (Sports Operations Engineer / SWE, Data / Quant Dev):
`job-boards.greenhouse.io/kalshi`. Optional short note to a hiring eng/quant lead via `kalshi.com/careers`.
**Tailored hook:**
> I built an end-to-end NBA model that prices player props against live books with walk-forward, leak-detecting
> validation that catches my own overclaims — the same edge discipline your sports markets desk needs to price event
> contracts; I'd love to talk to your Sports Operations Engineering team. Repo: github.com/neeljshah/court-vision

### ⭐ B2. Billy Bets (pre-seed) — *AI agent that surfaces +EV across Kalshi/Polymarket and auto-executes*
**What:** Pre-seed startup ($1M led by Coinbase Ventures, Sept 2025) building an AI agent for sports prediction
markets — proprietary ML + a natural-language terminal that surfaces +EV bets across Kalshi/Polymarket and
auto-executes; built on Base. *(Also fits "applied-ML startups" — listed once here.)*
**Why it fits you:** Tiny, very early team built around "ML models that surface +EV opportunities in real time across
prediction markets." That IS your project: model → EV → execution vs live markets. At pre-seed they hire purely on
output; a solo builder who shipped a full CV→ML→betting platform with rigorous validation is exactly the
founding-modeling profile. Your platform is essentially a working prototype of what they're building.
**Best channel:** Founders are active on X/LinkedIn — Exec Chairman **Jared Augustine** (X `@jaredaugustine`,
`linkedin.com/in/jaugustine/`); CEO **Joe O'Rourke** (`linkedin.com/in/josephorourke/`). Company
`linkedin.com/company/billy-bets`. **No verified public email — pitch the founder directly, don't apply (no careers page).**
**Tailored hook:**
> Saw Billy is turning "show me plus-EV NFL props tonight" into live execution across Kalshi/Polymarket — I solo-built
> an NBA prop model with leak-free walk-forward validation that does exactly that edge-detection step (and that caught
> my own "+18%" as a market-follow artifact rather than shipping it), and I'd love to help sharpen Billy's pricing layer.
**Caveat:** Confirm the company is still active before investing time; one trade-press source for the raise.

### B3. Polymarket — *world's largest prediction market; sports is a growing category*
**What:** Largest prediction-market platform ($21B traded in 2025); sports is major and growing. Hiring quant traders,
data analysts, data-infra engineers.
**Why it fits you:** Sports event pricing is a quant/ML problem on live markets — aligned with your model+EV+risk work
+ data-systems backend. Your CV/sports-domain depth differentiates you for sports-vertical pricing/features.
**Best channel:** Ashby board (filter data/quant/sports) `jobs.ashbyhq.com/polymarket` + `careers.polymarket.com`;
LinkedIn jobs `linkedin.com/company/polymarket/jobs`.
**Tailored hook:**
> Polymarket's sports category is fundamentally a live-pricing problem — I built an NBA model that prices props against
> moving books with shadow-logging and walk-forward checks that flag my own miscalibration, and I'd love to bring that
> to your sports markets.
**Caveat:** Large applicant pool may favor credentialed quants; a referral helps the no-degree path.

### B4. Unabated Sports (Boston area) — *sharp fair-value / no-vig pricing tools*
**What:** Sports-betting analytics company building true-price / no-vig fair-value calculators, market-making-derived
line models, EV/arbitrage tooling for serious bettors.
**Why it fits you:** Their whole product is fair-value pricing + EV detection vs the market — exactly your wheelhouse
(de-vig, true-line modeling, edge vs closing line, CLV). Small enough that output-first hiring matters; founder Dan
Fabrizio is an accessible, builder-friendly operator. Your CLV-correctness + calibration-vs-EV insights resonate
immediately.
**Best channel:** DM co-founder/president **Dan Fabrizio** — X `@DanFabrizio` (`x.com/danfabrizio`),
`linkedin.com/in/daniel-fabrizio-05a96121/`. Company `linkedin.com/company/unabated-sports` (domain `unabated.com` —
**find a real address there rather than guessing one**).
**Tailored hook:**
> Unabated's fair-value/no-vig engine is exactly the discipline I care about — I built an NBA prop model where I
> learned the hard way that calibration helps the stats you LOSE to Vegas but destroys the ones you beat it on, and
> that CLV must be measured as better-number-than-close; I'd love to compare notes.
**Caveat:** No public careers page found — approach as a warm founder DM, not an application.

### B5. OddsJam — *real-time odds aggregation across 100+ books → +EV / arb / DFS tools*
**What:** Founded 2020 by Stanford engineers; real-time odds aggregation across 100+ sportsbooks powering +EV,
arbitrage, and DFS/PrizePicks optimizers (10k+ arb opportunities/month).
**Why it fits you:** High-throughput data + EV-modeling shop (ingest 100+ books, compute fair value, surface +EV/arb).
Your backend/data-systems strength + freshness obsession (you found and fixed a UTC-date freshness bug silently
serving stale lines) + EV modeling fit the core engineering. Engineer-founded → rewards builders over credentials.
**Best channel:** Careers (Notion) `vampolo.notion.site/OddsJam-Careers-...` (verify the live link). Founder/contact
context via Crunchbase `crunchbase.com/organization/oddsjam`.
**Tailored hook:**
> OddsJam lives or dies on real-time freshness across 100+ books — I caught (and fixed) a UTC-date freshness bug in my
> own live NBA odds pipeline that was silently serving stale lines, and I'd love to bring that obsession with same-day
> data integrity to your +EV engine.
**Caveat:** Careers page exists but specific reqs not confirmed — verify an open role.

### B6. Rithmm (Boston) — *seed-stage AI app: customizable predictive models for NBA/NFL props*
**What:** Seed-stage ($2M seed, 2023) AI sports-betting app — customizable predictive-analytics models for NFL/NBA
props and picks for retail bettors; MIT-grad team.
**Why it fits you:** Seed-stage, small, model-centric, building "customized personal algorithms" for prop predictions —
directly your NBA prop modeling + serving experience. Consumer-facing predictions = your full build (data → model →
served picks → validation) covers the whole stack. Self-taught builder fits a lean seed team hiring on shipped work.
**Best channel:** Site `rithmm.com` (look for careers/contact). DM CEO **Megan Lanham** via LinkedIn (search "Megan
Lanham Rithmm"); company LinkedIn for founder/eng-lead DM.
**Tailored hook:**
> Rithmm's customizable per-user prediction models are exactly what I've been building for NBA props — including the
> unglamorous part, like rigorously validating that an edge survives out-of-sample and isn't a single-window peak — and
> I'd love to help make Rithmm's picks provably sharp.
**Caveat:** No confirmed open req (seed-stage) — warm founder DM.

### B7. Swish Analytics (San Francisco) — *B2B pricing + risk engine behind the book*
**What:** B2B sports-betting/analytics company (founded 2014, ~$29M raised, ~120–170 employees) — predictive models,
real-time odds/pricing, trading/risk-management tech sold to sportsbooks/operators. *(Also fits "applied-ML
startups" — listed once here.)*
**Why it fits you:** The "pricing + risk engine behind the book" play — predictive modeling, live odds generation,
risk management — a natural home for ML-modeling+validation + data-systems strength. Roles incl. **Basketball Data
Scientist** and **ML Engineer**; your per-stat calibration, edge-vs-Vegas validation, and basketball depth fit tightly.
More established (more structured hiring, real DS team incl. PhDs) → demonstrated senior work stands in for a degree,
but a more conventional bar than the seed startups.
**Best channel:** Careers `swishanalytics.na.teamtailor.com` (also Wellfound `wellfound.com/company/swish-analytics`,
TeamWork Online). Apply to the basketball-data-scientist role + link the repo + a short validation write-up. Founders
for outreach: CEO **Joseph Hagen**, Head of Engineering **Corey Beaumont** (LinkedIn).
**Tailored hook:**
> Swish prices and risk-manages markets for operators — I built the full bettor-side mirror of that (NBA prop models +
> EV + a self-auditing validation harness that catches my own overclaims), and I'd be excited to apply that
> modeling+risk discipline on the book side at Swish.
**Caveat:** Several roles list a degree preference — a stretch on the no-degree axis. Worth applying; set expectations.

---

## C. CV / applied-ML startups & data-ML platforms

### ⭐ C1. Voxel51 (remote-first) — *bullseye: CV data-curation/eval platform (FiftyOne), open ML+CV reqs*
**What:** Open-source + enterprise data platform (FiftyOne) for curating, debugging, analyzing CV datasets and model
outputs. Series B $30M (Bessemer), ~51–200 people, remote-first.
**Why it fits you:** Single closest data-platform fit. Your whole project IS a CV-data platform: video → structured
features → dataset curation → model eval → shadow-logging/leak-detection. FiftyOne is tooling for the dataset-quality
+ model-debugging discipline you already practice solo; your walk-forward/leak-detection rigor maps to their "find
detrimental mistakes in datasets/models" value prop. Remote-first → judged on output.
**Best channel:** Careers `voxel51.com/careers` (ML Engineer + CV Engineer, remote-first). DM co-founder **Jason
Corso** (academic, responsive to technical builders) on LinkedIn with the repo; CEO **Brian Moore** also on LinkedIn.
Apply via careers AND send Corso a note.
**Tailored hook:**
> I built a solo broadcast-video → court-coordinate → behavioral-feature CV pipeline (YOLOv8, SIFT homography,
> Kalman+Hungarian, OSNet re-ID) and a leak-detection/walk-forward harness that catches my own dataset and model errors —
> which felt like building my own FiftyOne for one hard domain, so Voxel51 is the team I most want to do this with at scale.

### ⭐ C2. Roboflow — *bullseye: CV dev platform that publishes basketball-tracking content; active ML reqs*
**What:** Developer platform to build/train/label/deploy CV models; 250k+ developers, half the Fortune 100. YC S20,
$60M+ raised (GV, Craft, Sam Altman, Lachy Groom).
**Why it fits you:** Their bread and butter — detection, tracking, video → structured data — is your stack, and they
even publish write-ups on detecting/tracking/identifying basketball players, so your domain is on-brand. Famously
builder-first / portfolio-over-pedigree. Hiring ML Research Engineer + platform engineers; your end-to-end ownership
(CV + serving + data) fits.
**Best channel:** Careers `roboflow.com/careers` + YC jobs `ycombinator.com/companies/roboflow/jobs`. DM/tweet CTO
**Brad Dwyer** (X `@braddwyer`, `linkedin.com/in/brad-dwyer-b6b4136/`, engages with builders) the repo; CEO **Joseph
Nelson** `linkedin.com/in/josephofiowa/`. Apply to ML Research Engineer.
**Tailored hook:**
> I read your write-up on detecting and tracking basketball players with CV — I built the full thing solo for NBA
> broadcast (YOLOv8 + SIFT homography + Kalman/Hungarian + OSNet re-ID into a behavioral feature store), and I'd love to
> bring that production-tracking experience to Roboflow's platform.

### C3. Encord (London + SF) — *physical-AI data layer: annotation, dataset mgmt, model quality*
**What:** CV/"physical AI" data layer: annotation, dataset management, model-quality tooling. YC company, Series B
$30M (Next47, CRV, Crane). ~150 people.
**Why it fits you:** Same category as Voxel51 — the data/quality layer under CV models. Hires Forward Deployed
Engineers + full-stack/data-integration engineers where shipping evidence beats credentials; your skill at turning
messy raw inputs (broadcast frames) into clean queryable data + honest validation is exactly what a data-layer company
values. They explicitly hire non-traditional backgrounds (Associate SWE track) → no CS degree is not a blocker.
**Best channel:** Careers `wellfound.com/company/cord-9/jobs` + Built In; YC `ycombinator.com/companies/encord`. DM
founders **Eric Landau** (CEO) or **Ulrik Stig Hansen** (President) on LinkedIn with the repo, + apply to an FDE/SWE role.
**Tailored hook:**
> Your thesis that the data layer — not the model — is what makes physical-AI work matches what I learned building an
> NBA CV pipeline solo: 90% of the wins came from dataset hygiene, homography/re-ID correctness, and a leak-detection
> harness that refutes my own overclaims, not from a fancier model.
**Caveat:** ~36 roles listed — verify the specific FDE/SWE req is still open.

### C4. Peripheral Labs (Toronto) — *broadcast feeds → navigable 3D volumetric video, fresh seed, growing eng*
**What:** Seed startup ($3.6M led by Khosla Ventures, Dec 2025) converting standard broadcast feeds into navigable
photorealistic 3D volumetric video in near real-time using AI/sensor techniques from self-driving — cutting cameras
from 100+ to ~32.
**Why it fits you:** Turning N broadcast feeds into a consistent 3D world is multi-view geometry + homography/calibration
+ multi-object tracking + cross-view re-ID — your exact toolkit. Founders from the U of T self-driving team + Tesla →
"demonstrated senior work" culture. Fresh seed earmarked to grow a ~10-person technical team → excellent timing.
**Best channel:** DM CEO/co-founder **Kelvin Cui** `linkedin.com/in/kelvinwcui/` (small team, founder-led hiring);
co-founder **Mustafa Khan** also on LinkedIn. Crunchbase `crunchbase.com/organization/peripheral-labs-...`. **No public
careers email confirmed — reach Kelvin directly.**
**Tailored hook:**
> Your broadcast-feed → navigable 3D volumetric pipeline is the multi-view extension of what I built solo for NBA
> (per-camera homography to court coords + Kalman/Hungarian tracking + OSNet re-ID to keep identities consistent), and
> the self-driving-perception lineage of the team is exactly the engineering DNA I taught myself over ~3 months.

### C5. AlgoX2 — *seed real-time data-streaming OS with microsecond AI-feature streaming*
**What:** "The Data Streaming OS" — one fault-tolerant engine unifying ingestion, ordering, fan-out, transformation,
durable storage (Iceberg/Delta/Hudi), with microsecond AI-feature streaming. Ex-NYSE/HFT engineers. $3.5M seed
(Bessemer), Oct 2025.
**Why it fits you:** Pure real-time data infra at seed stage — earliest, most output-hireable, aligned with your
applied-ML/quant + backend-data-systems strengths. Their pitch literally includes "AI feature streaming with
microsecond delivery" + real-time feature/backtest infra, overlapping your scrapers→store→feature→serving + walk-forward
backtesting world.
**Best channel:** Careers `algox2.com/careers` + `algox2.com/contact`; company LinkedIn `@algox2`. DM **George Levin**
(CBO, `linkedin.com/in/george-levin/`, posts publicly about AlgoX2 — most reachable) with the repo + a note on your
real-time serving/backtest harness. Founders **Alexei Lebedev** (CEO), **Vladimir Parizhsky** (CTO).
**Tailored hook:**
> Your microsecond AI-feature-streaming + backtest engine is the production-grade version of what I hacked together
> solo — a real-time feature/serve path with a walk-forward, shadow-logged backtest harness that flags its own
> look-ahead leaks before they hit live inference.
**Caveat:** Seed-stage, tiny headcount — treat as a warm intro, not a posted role.

### C6. Bucket Robotics (San Francisco, YC S24) — *deployable CV defect-detection for manufacturing (non-sports)*
**What:** YC-backed seed startup building deployable CV defect-detection for manufacturing — CAD + synthetic/sample
data → production-ready vision models on existing cameras/edge hardware, no manual labeling.
**Why it fits you:** Non-sports option proving the skills transfer broadly. Your detection (YOLO), running models on
real camera feeds, edge/real-time constraints, and rigorous validation map onto industrial defect detection. A
5-person YC team hiring 2 engineering roles is exactly the "hireable on output, degree irrelevant" environment.
**Best channel:** Apply via YC Work at a Startup `workatastartup.com/companies/bucket-robotics` (2 eng roles) or
`ycombinator.com/companies/bucket-robotics/jobs`. DM CEO/co-founder **Matt Puchalski**
`linkedin.com/in/matt-puchalski/` (best for a 5-person team).
**Tailored hook:**
> I spent ~3 months solo turning messy real-world camera feeds into reliable, validated CV output (NBA broadcast →
> court coordinates, YOLOv8 + tracking + re-ID, with a walk-forward harness that catches my own overclaims) — that
> "make vision models that hold up on real cameras and edge hardware" discipline is exactly what defect detection from
> CAD + samples demands.
**Caveat:** Different domain — perception+edge+validation skills transfer, but it's adjacent, not core.

---

## D. YC founding-engineer / earliest-stage (highest no-degree yield)

### ⭐ D1. OnDeck AI (YC S25) — *bullseye: founding ML role, no-degree-friendly language, messy-footage CV*
**What:** Infrastructure making Vision-Language Models scalable for enterprise video — find any object/behavior/event
in any footage with no training/labels; decomposes + recombines VLM components into a general visual-reasoning system
served via API. Customers in defense/robotics/security/port-monitoring.
**Why it fits you:** Explicitly hiring BOTH a Founding Engineer and a Founding ML Engineer; the ML posting prizes "a
track record of building novel applied research projects" and "excellent empirical intuition" over a degree —
tailor-made for a no-degree builder judged on output. Your from-scratch video CV pipeline (detection + tracking +
re-ID on messy real footage) + empirical validation are exactly what they screen for.
**Best channel:** Apply via YC Work at a Startup — founding ML role
`ycombinator.com/companies/ondeck-ai/jobs/Mkr4kZN-founding-machine-learning-engineer`; founding-eng
`workatastartup.com/jobs/81971`. Founders **Alexander Dungate** & **Sepand Dyanatkar** on LinkedIn; company
`linkedin.com/company/ondeckai`. **Note: in-person Vancouver BC (option to relocate to SF later).**
**Tailored hook:**
> You rip apart VLMs to find any object/behavior in any footage without training data — I built the from-scratch
> version of that for NBA broadcast (detection → homography → tracking → re-ID → behavioral features on messy real
> video) and a self-auditing walk-forward harness that flags my own false positives; I'd love to do your work-trial.

### ⭐ D2. The Forecasting Company (YC, Paris) — *bullseye: founding-MLE for time-series foundation models*
**What:** Building foundation models for time-series forecasting — a plug-and-play platform (their t_0 model)
predicting any business time series without per-dataset tuning. Founders are ML PhDs (Berkeley BAIR, Edinburgh;
ex-Amazon Forecasting Science, Google Brain, Bloomberg, JPMorgan ML CoE).
**Why it fits you:** Purest "forecasting + founding MLE + validation rigor" fit. Open 2nd founding-MLE role:
implement-from-literature, train/deploy large forecasting architectures, push SOTA. Your ML modeling + genuinely
rigorous walk-forward/leak-detection validation is exactly what a forecasting-foundation-model company lives or dies on.
**Best channel:** Apply via YC jobs `ycombinator.com/companies/the-forecasting-company/jobs` (founding MLE listed). DM
CTO **Joachim Fainberg** `linkedin.com/in/jfainberg/`. Public email format is `{first-initial}@theforecastingcompany.com`
per their site — **treat as inferred; verify before relying on it, don't send blind.**
**Tailored hook:**
> Your bet is foundation models that forecast any series without per-dataset tuning — I've spent a year doing leak-free
> walk-forward validation on noisy sports time series, and my methodology routinely catches my own model's overclaims,
> which is exactly the discipline a forecasting foundation model needs.
**Caveat:** Paris-based — clarify remote/relocation.

### D3. Terranox AI (YC W26) — *founding AI/ML: CV from scratch on messy, sparsely-labeled data → production*
**What:** AI-powered uranium discovery — trains CV/ML models on 70+ years of sparse, messy, weakly-labeled geophysical
data to find high-grade deposits, with production pipelines that drive real drilling decisions. Backed by General
Catalyst, 776 Ventures, YC.
**Why it fits you:** The Founding AI/ML Engineer role centers on "training CV models from scratch on messy,
sparsely-labeled data and shipping them into a production pipeline" — a one-to-one description of your ~3 months
(homography/tracking/re-ID on noisy broadcast frames, then serving). Your leak-detection/walk-forward discipline
differentiates for high-stakes geophysical predictions.
**Best channel:** Real public email `founders@terranox.ai`. Role
`ycombinator.com/companies/terranox-ai/jobs/Yi5VAYy-founding-ai-ml-engineer`. DM CEO **Jade Checlair** (PhD
geophysics) `linkedin.com/in/jade-checlair/`; CTO **Leeav Lipton** (ex-NASA JPL, ex-Borealis AI). Site `terranox.ai`.
**In-person SF.**
**Tailored hook:**
> Your founding role is "train CV models from scratch on messy, sparsely-labeled data and ship them into a production
> pipeline that drives real decisions" — precisely what I did solo for ~3 months turning noisy NBA broadcast frames into
> court coordinates and behavioral features, with a validation harness built to catch my own overclaims before they
> reach production.
**Caveat:** JD lists 5+ yrs — a strong portfolio + work-trial often overrides that at this stage; set expectations.

### D4. Novig (YC S22) — *commission-free sports betting/prediction exchange, quant-heavy*
**What:** Commission-free, high-frequency sports betting/prediction-markets exchange — users trade against the market,
not the house; quant-style pricing + internal market making. Founders ex-Jane Street / Bank of America.
**Why it fits you:** Applied-ML/quant on live sports markets — your exact wheelhouse, including the CLV/edge-validation
and calibration thinking from your platform. Founders evaluate on real modeling/trading output and intellectual
honesty. Roles span quant researchers, traders, SWEs.
**Best channel:** DM CEO **Jacob Fortinsky** `linkedin.com/in/jfortinsky/` (himself a sharp bettor before founding it —
he'll appreciate the edge-validation framing). Careers via Work-at-a-Startup / `ycombinator.com/companies/novig`.
**Tailored hook:**
> You built a real exchange because the books ban winners and misprice markets — I've built my own NBA prop pricing +
> CLV-tracking stack and learned the hard way that most "edges" are market-follow artifacts until you validate
> out-of-sample, which is the kind of honesty your trading desk runs on.
**Caveat:** Later-stage than the seed sweet spot (raised an $18M Series A + a reported $75M Series B / Pantera) — still
founder-led and a strong applied-ML/quant home.

### D5. Kero Sports / Kero Gaming (Miami) — *real-time in-game micro-betting; open Senior DS/MLE req*
**What:** White-label real-time in-game micro-betting engine: ingests live play-by-play, uses ML to surface curated
micro-bets every 15–45s for 180+ sportsbooks and 20 US franchises. Series A (~$4M; $3M Series A May-2025).
**Why it fits you:** Real-time inference + ranking/forecasting on live sports streams — your in-game/live-projection
work (live possession-sim + snapshot projector) maps directly onto generating/pricing micro-bets play-by-play. Small
team explicitly hiring a **Senior Data Scientist / ML Engineer** for the betting model; lives on model quality over
pedigree.
**Best channel:** Public posting on Wellfound ("Senior Data Scientist / ML Engineer — Sports Betting Startup at Kero
Sports", US/Canada/remote) — apply + reference the live-feed modeling. Company `wellfound.com/company/kero-sports`. DM
CEO **Tomash Devenishek** on LinkedIn for a direct founder note.
**Tailored hook:**
> Your engine turns live play-by-play into a fresh micro-bet every 15–45 seconds — I built a real-time NBA in-game
> projector and possession sim that re-prices player lines snapshot-by-snapshot, so generating and calibrating
> sub-minute in-game markets is exactly the problem I've been obsessing over.
**Caveat:** Verify that specific req is still open today.

### D6. Weave (YC W25) — *founding ML/AI eng (applied-ML, not CV); higher traction/funding fallback*
**What:** ML/AI platform that understands and improves how software-engineering teams work; 150+ customers (Rho, 11x,
Browserbase), $4.2M seed (Moonfire, Burst, YC), double-digit MoM growth. SF.
**Why it fits you:** Actively hiring a Founding ML Engineer ($150–215K + 0.2–1% equity) + Founding AI Engineer. Not CV,
but a strong applied-ML/data-systems + modeling fit — your backend/data-stack chops + rigorous validation
(walk-forward, leak detection, shadow-logging) map to building ML systems on behavioral signal data. Good fallback for
a higher-traction, better-funded team where the bar is demonstrated ML/systems output.
**Best channel:** Apply via YC `ycombinator.com/companies/weave-3/jobs/ZPyeXzM-founding-ml-engineer` (also Ashby
`jobs.ashbyhq.com/workweave`). Founders **Andrew Churchill** & **Adam Cohen** (LinkedIn). Company
`ycombinator.com/companies/weave-3`.
**Tailored hook:**
> Your founding-ML job is to turn messy signals about engineering work into systems people trust — I built an
> end-to-end ML stack (modeling + serving + data) on noisy real-world data with a self-auditing walk-forward/
> leak-detection harness designed to refute my own predictions before they ship, which is the discipline that keeps an
> ML product trustworthy as it scales.
**Caveat:** Adjacent (applied-ML/data), not core CV.

### D7. Dragoneye (YC W24, NYC) — *CV-infra API for custom video/image detection; cold outreach*
**What:** Developer API to build custom video/image detection models in <5 minutes with zero-shot CV and no manual
annotation — auto-labels data, picks/finetunes a foundation model, serves via REST. Founder ex-Jane Street/Facebook.
**Why it fits you:** Pure CV-infra company, output-over-credentials culture; product (video detection on arbitrary
footage) overlaps your detection/tracking expertise. Tiny team (~2) with one founding engineer → a CV specialist is a
natural next hire.
**Best channel:** DM founder **Alex Liao** (search "Alex Liao Dragoneye"); company `linkedin.com/company/dragoneyeai`;
site `dragoneye.ai`; YC `ycombinator.com/companies/dragoneye`. **No public hiring email found — DM the founder, don't guess.**
**Tailored hook:**
> You let any developer spin up a custom video detection model in five minutes — I went the hard, hand-built route for
> NBA broadcast (YOLOv8 + homography + tracking + OSNet re-ID → behavioral features) and learned exactly where zero-shot
> detection breaks on real footage; if you're adding CV depth to the team I'd love to share the repo.
**Caveat:** No open role found (0 listed) — treat as cold/proactive outreach; the founding-eng seat may already be filled.

---

## Channel reality (where effort converts)
1. **Referral** — ask anyone you know at/near these. 5–10× the response of cold.
2. **Founder/recruiter DM on LinkedIn/X** — best for seed/YC (Billy Bets, Peripheral Labs, OnDeck, Terranox, Kero, Dragoneye, AlgoX2).
3. **Careers application WITH the repo + evidence packet linked** — your repo IS the take-home (Kalshi, Voxel51, Roboflow, Encord, ReSpo.Vision, Bucket, OnDeck, Forecasting Co, Weave, Swish).
4. **Cold email** — ONLY where a real public email is listed (`contact@respo.vision`, `info@track160.com`,
   `contact@sportai.com`, `founders@terranox.ai`). The Forecasting Co address is INFERRED — verify first.
   Everywhere else, DM the founder. **Never guess an address.**

> Reminder before each send: confirm the opening still exists + the handle/URL is current (30 sec), and lead with the
> engineering + the self-auditing validation methodology — never the retracted numbers.
