# Outreach Kit

> **Before you use anything in here — read this.**
>
> **Lead with engineering, methodology, and honesty. In that order. Never lead with the betting returns.**
>
> The three pillars you are selling are:
> 1. **Production computer vision** — broadcast video → court coordinates → behavioral features (YOLOv8, SIFT homography, Kalman + Hungarian tracking, OSNet re-ID), running on a consumer GPU at ~$0.10/game.
> 2. **System breadth** — a ~6,000-file platform built solo in one git history: FastAPI service (~49 endpoints), 9 daemons, scrapers, PostgreSQL, dashboards, CI/CD.
> 3. **ML validation rigor + intellectual honesty** — walk-forward CV, shadow-logging, leak detection, an agentic discovery loop with hard ship gates that *caught your own overclaims*.
>
> **Do NOT quote these numbers — they are known-broken and citing them undercuts the entire honesty pitch:**
> - ~~+18.38% pre-game ROI~~ → it was a **market-follow artifact**; real ROI vs. closing lines is **roughly −2% to −5%**.
> - ~~endQ3 Brier 0.119~~ → inflated by a **Q4 data leak**.
> - ~~+54% in-play ROI~~ → measured against an **L5 line proxy**, not real in-play lines.
>
> The self-skepticism — *you caught and documented these yourself* — is the senior-hire signal. The artifact is the credential: **github.com/neeljshah/court-vision**.
>
> When the betting domain comes up, frame it as the *problem space* (an adversarial, ground-truth-rich grader that forced rigor), not the product. The skills travel anywhere.

---

## Table of contents

1. [Positioning & one-liners](#1-positioning--one-liners)
2. [Cold-email templates (by role)](#2-cold-email-templates-by-role)
3. [Resume bullets](#3-resume-bullets)
4. [LinkedIn / About copy](#4-linkedin--about-copy)
5. [Interview-prep talking points](#5-interview-prep-talking-points)
6. [Target roles & where to apply](#6-target-roles--where-to-apply)
7. [The no-degree framing](#7-the-no-degree-framing)

---

## 1. Positioning & one-liners

### Elevator pitch — 30 seconds (spoken)

> I'm Neel. For the last year I've solo-built an NBA analytics platform end to end — and the part I'm proudest of is the pipeline that turns raw broadcast video into court coordinates: YOLO detection, homography, multi-object tracking and player re-ID, running on one consumer GPU for about ten cents a game.
>
> On top of that I built the ML and serving stack — around 6,000 files, a FastAPI backend, a handful of daemons — with walk-forward validation and shadow-logging.
>
> Honestly, the thing I value most is that my own process catches my mistakes — I've documented data leaks and a fake ROI signal in my own results before they shipped. No CS degree; I just learned to build real systems and not lie to myself about them.

*Lands at ~30–35 sec at a natural pace. Lead with the CV pipeline, then breadth, then the honesty close — pause before that last line. Drop the middle paragraph for a tighter ~20s version. No betting returns.*

### Project taglines (pick by audience)

1. **(Plain / resume header)** Solo-built a ~3-month computer-vision → ML → betting platform: broadcast video to court coordinates to behavioral features, ~$0.10/game on a consumer GPU.
2. **(Engineering-forward)** ~6,000-file system — YOLOv8 + SIFT homography + Kalman/Hungarian tracking + OSNet re-ID, behind a 49-endpoint FastAPI and 9 daemons — designed, written, and operated by one person.
3. **(Methodology-forward)** An NBA prediction stack built around the validation, not the prediction: walk-forward CV, shadow-logging, and leak detection with hard ship gates that block features that don't earn their place.
4. **(Honesty / senior-signal)** The rigor I'm proudest of is what it taught me to throw away — I caught and documented my own data leaks and a market-follow ROI artifact rather than ship the inflated numbers.
5. **(Agentic-loop angle)** An autonomous Opus/Sonnet discovery loop that proposes signals and an adversarial verifier that tries to refute them — surviving features cleared independent corpora; most got rejected, by design.
6. **(Conversational / LinkedIn)** Turned NBA broadcasts into tracking data and a full prediction-and-betting system, solo — and learned the hard way that the engineering and the skepticism are the real product, not the betting returns.

*Pick by audience: #1 resume/GitHub, #2 technical/eng, #3 ML/data-science, #4 the honesty pitch (strongest senior signal), #5 discovery-loop tooling, #6 casual/LinkedIn.*

### One-line hook per buyer

- **Sports-tech / CV startup:** "I built a single-broadcast-feed tracking pipeline — YOLOv8 + SIFT homography + Kalman/Hungarian + OSNet re-ID — running at ~$0.10/game on a consumer GPU."
- **Applied-ML / quant:** "I built a research loop with hard ship gates that caught its own false positive — I killed a backtest after proving it was a market-follow artifact, not edge."
- **Dev-tools / agentic:** "I ran an Opus/Sonnet agentic discovery loop under correctness gates across a ~6,000-file system, and shipped the gating, not the hype."

*Pick the buyer's dominant pain, lead with that one line, and let the other two skills be the depth they discover in conversation.*

---

## 2. Cold-email templates (by role)

> **Usage rules for all templates:** Replace every `[bracket]`. Keep the body under ~150 words. One hook + one clear ask. Verify the GitHub URL slug before sending. Send 5 well-researched, tailored emails over 50 generic ones. Track replies, not sends.

### 2.1 — ML engineering hiring manager

> **Subject:** Solo-built a production CV→ML pipeline — and caught my own data leaks
>
> Hi [Name],
>
> Over ~3 months I built an end-to-end NBA system solo: broadcast video → court coordinates → behavioral features → ML predictions, served behind a FastAPI app. The CV path is the part I'm proudest of — YOLOv8 detection, SIFT homography for court rectification, Kalman + Hungarian tracking, and OSNet re-ID — running on a consumer GPU at ~$0.10/game.
>
> But the reason I'm writing is the validation methodology. I run walk-forward CV with shadow-logging and hard ship-gates, and the loop's job is to refute its own findings. It's caught real failures of mine: a data leak that inflated an in-game metric, and a "profitable" ROI result that turned out to be a market-follow artifact (truly ~−4%). I'd rather kill a finding than ship a fake one.
>
> Code: github.com/neeljshah/court-vision
>
> Worth a 20-minute call to see if the rigor fits your team?
>
> Thanks,
> Neel Shah · neeljshah22@gmail.com

### 2.2 — Computer-vision team / engineer

> **Subject:** Broadcast NBA video → court coordinates → behavioral features, on a $300 GPU
>
> Hi [Name],
>
> I spent the last ~3 months solo-building a pipeline that turns raw broadcast NBA footage into tracking data without licensed optical feeds. The stack: YOLOv8 detection → SIFT homography (RANSAC + EMA smoothing) to map each frame onto a court panorama → Kalman + Hungarian tracking → OSNet re-ID to hold player identity through occlusion and similar uniforms. Out the other end: defender distance, spacing, contested-shot rate, and play type — per player, per possession.
>
> It runs at roughly $0.10/game on a consumer RTX 4060, versus six-figure Sportradar/Second Spectrum licensing. Code and a frame-by-frame writeup: github.com/neeljshah/court-vision.
>
> I don't have a CS degree — the work and my own leak/overclaim audits are the resume. I'd love 15 minutes to hear how [Team] handles homography drift on moving broadcast cameras.
>
> Thanks,
> Neel Shah · neeljshah22@gmail.com

*Note: don't add a specific OSNet embedding-dim number here — the repo docstring (256-dim) and CLAUDE.md (512-dim) disagree; leave it unstated unless you check.*

### 2.3 — Founding / early engineer

> **Subject:** Solo-built a CV→ML→serving system end-to-end — founding eng?
>
> Hi [Name],
>
> I build whole systems alone and ship fast. Over the last ~3 months I solo-built an NBA prediction platform end-to-end: a computer-vision pipeline that turns broadcast video into court coordinates and behavioral features (YOLOv8, SIFT homography, Kalman+Hungarian tracking, OSNet re-ID) on a consumer GPU at ~$0.10/game, feeding ML models served behind a FastAPI backend (~49 endpoints, 9 daemons, PostgreSQL, CI/CD) — one git history, ~6,000 files.
>
> The part I'd actually bring to your team is validation discipline: walk-forward CV, shadow-logging, leak detection, and an agentic discovery loop with hard ship gates. It's caught my own overclaims — I documented a data leak and a market-follow ROI artifact in my own results rather than ship them.
>
> Repo: github.com/neeljshah/court-vision. No CS degree; the work speaks for itself.
>
> Are you hiring an early engineer who owns the full stack plus its validation? Happy to walk you through any piece.
>
> Neel · neeljshah22@gmail.com

### 2.4 — Data / ML Platform engineering

> **Subject:** Solo-built ML data platform (scrapers → Postgres → serving) — would love your read
>
> Hi [Name],
>
> I spent ~3 months solo-building the data platform behind an NBA prediction system, and the spine is exactly what your team runs: scrapers feeding PostgreSQL, a feature store, 9 long-running daemons, and ~49 FastAPI endpoints for serving — one git history, reproducible pipelines end to end.
>
> The part I'm proudest of is the discipline, not the demo. Every model change ships through walk-forward CV and shadow-logging before it touches serving, with hard gates. That rigor caught two of my own bad results — a data leak and a market-follow ROI artifact — which I documented rather than shipped. I'd rather kill my own number than trust a broken one.
>
> No CS degree; this is all demonstrated work. Repo: github.com/neeljshah/court-vision.
>
> Could I send a 10-minute walkthrough of the pipeline, or grab 15 minutes this week?
>
> Thanks,
> Neel Shah · neeljshah22@gmail.com

### 2.5 — Applied Scientist

> **Subject:** Applied scientist — I built an ML system that caught its own data leaks
>
> Hi [Name],
>
> For ~3 months I solo-built an NBA prediction platform (CV → ML → decisioning) and the part I'm proudest of isn't a model — it's the validation harness that kept me honest.
>
> It does walk-forward CV, shadow-logging, and automated leak detection inside an agentic discovery loop with hard ship-gates. Concretely, it caught my own overclaims: a "profitable" ROI that turned out to be a market-follow artifact (real ≈ −4%), and a calibration score inflated by a fourth-quarter data leak. I documented both as failures rather than ship them.
>
> The upstream is real production CV: broadcast video → court coordinates → behavioral features (YOLOv8, SIFT homography, Kalman+Hungarian tracking, OSNet re-ID) on a consumer GPU at ~$0.10/game. Code: github.com/neeljshah/court-vision.
>
> I don't have a CS degree — I have a system that distrusts itself. Could I show you the leak-detection harness in 20 minutes?
>
> Best,
> Neel Shah · neeljshah22@gmail.com

### 2.6 — Sports analytics / NBA team analytics group

> **Subject:** Behavioral features from broadcast video, ~$0.10/game
>
> Hi [Name],
>
> I built a pipeline that turns raw broadcast NBA video into court-coordinate behavioral features — no tracking-data license, no special camera feeds. It's YOLOv8 detection, SIFT homography to map pixels to the court, Kalman + Hungarian tracking, and OSNet re-ID for player identity through occlusions. Runs on a single consumer GPU at roughly $0.10 per game.
>
> I solo-built the whole stack over ~3 months — the CV layer plus the ML and serving systems around it (FastAPI, daemons, Postgres) — with walk-forward validation and shadow-logging throughout. I'm equally proud of what I threw out: I caught and documented my own data leaks and a ROI artifact rather than ship them.
>
> Could I send a 2-minute clip of tracked output from a broadcast frame? Happy to run it on a game of your choosing.
>
> Best,
> Neel Shah · github.com/neeljshah/court-vision

### 2.7 — Referral / intro ask (warm-ish contact)

> **Subject:** Quick ask — would you point me at the right person?
>
> Hi [Name],
>
> [Personal opener — e.g. "Hope the move to [Team] is going well" / "Loved your recent post on X."]
>
> I've spent the last ~3 months solo-building a computer-vision + ML platform that turns broadcast NBA video into court-coordinate tracking data — YOLOv8 detection, SIFT homography, Kalman + Hungarian tracking, OSNet re-ID — running on a single consumer GPU at about $0.10 a game, then layering walk-forward-validated models on top of it.
>
> The part I'm proudest of isn't a metric, it's the discipline: shadow-logging, leak detection, and a discovery loop with hard ship gates that has caught and killed several of my own overclaims (a market-follow ROI artifact, a data-leaked metric). I'd rather find my own bugs than ship them.
>
> Repo: github.com/neeljshah/court-vision
>
> I'm looking at [CV / ML-infra] roles and would love an intro to whoever owns that hiring at [Company] — or just your read on whether it's a fit. Happy to send a tighter writeup.
>
> Thanks either way,
> Neel

### 2.8 — Follow-up (5 days after an unanswered cold email)

> **Subject:** Re: NBA computer-vision platform — quick follow-up
>
> Hi [Name],
>
> Following up on my note from last week, in case it slipped past a busy inbox.
>
> Short version: over ~3 months I solo-built an end-to-end NBA platform — broadcast video to court coordinates to behavioral features (YOLOv8, SIFT homography, Kalman + Hungarian tracking, OSNet re-ID) running on a consumer GPU at ~$0.10/game — feeding an ML and betting stack (FastAPI, ~49 endpoints, 9 daemons, Postgres) in one git history.
>
> The part I'd most want to talk through isn't a return number — it's the validation discipline. I run walk-forward CV with shadow-logging and hard ship gates, and the work that taught me most was catching my own overclaims: a data leak and a market-follow ROI artifact I'd initially believed.
>
> Worth a 20-minute call? Happy to send the repo or walk through the pipeline.
>
> Best,
> Neel · github.com/neeljshah/court-vision

*Send as a reply on the same thread (keep "Re:" + original subject so it threads).*

### 2.9 — LinkedIn connection note (<300 chars)

> Hi [Name] — solo-built a ~3-month NBA platform: broadcast video → court coords (YOLOv8, SIFT homography, Kalman+Hungarian tracking) → ML props, ~$0.10/game on one GPU. The part I'm proudest of is the validation rigor — walk-forward CV and leak detection that caught my own overclaims. Would love to connect.

*~296 chars; re-count after swapping [Name]. If over 300, drop "broadcast " or "Kalman+Hungarian". For a recruiter, trim tracker internals to "broadcast video → court coordinates → ML props" to leave room for a role-specific phrase.*

### 2.10 — X DM to an engineer (conversation opener, no ask)

> hey [name] — been following your work and the [specific thing they built, e.g. "tracking writeup"] stuck with me, so figured I'd say hi.
>
> I've spent the last ~3 months solo-building an NBA pipeline: broadcast video → court coordinates → behavioral features (YOLOv8, SIFT homography, Kalman+Hungarian tracking, OSNet re-ID), running on a consumer GPU at ~$0.10/game. The part I'm proudest of isn't the model accuracy — it's the validation harness that keeps catching my own overclaims. It's flagged a couple of my "wins" as data leaks and a ROI number as a market-follow artifact. Killing my own results has been the most useful thing I built.
>
> No ask — just wanted to nerd out with someone who clearly thinks hard about this stuff. How do you handle leak detection in your own pipelines? Always curious how other people keep themselves honest.

*Fill the bracketed reference to their specific work — the personalized hook is what makes it land. Intentionally low-pressure; ends on a question to invite a reply.*

---

## 3. Resume bullets

> **Usage:** Every number below is defensible from the repo. Use the blocks that match the role. The "caught my own overclaims" lines are load-bearing — do not cut them to look more impressive; they are the senior-hire differentiator. No inflated betting metrics appear anywhere.

### 3.1 — Resume summary / objective (3 paragraphs)

Self-taught engineer who solo-built and operates a production NBA computer-vision and ML platform (~6,000 files, single git history): broadcast video → court coordinates → behavioral features via YOLOv8 detection, SIFT homography, Kalman + Hungarian tracking, and OSNet re-ID, running on a consumer GPU at ~$0.10/game.

Designed the full system around it — FastAPI service (~49 endpoints), 9 background daemons, scrapers, PostgreSQL, dashboards, and CI/CD — plus a rigorous ML validation stack: walk-forward cross-validation, shadow-logging, leak detection, and an agentic discovery loop with hard ship gates.

Strongest signal is intellectual honesty: the validation harness is built to catch its own overclaims, and I documented my own data leaks and a market-follow ROI artifact rather than ship them. I optimize for what survives out-of-sample, not what looks good in a deck.

### 3.2 — CourtVision project block (lead with this for CV/ML/systems roles)

**CourtVision — Computer Vision & ML Sports-Analytics Platform** | Solo project, ~3 months | *Python, PyTorch, FastAPI, PostgreSQL* | github.com/neeljshah/court-vision

- Built an end-to-end pipeline turning broadcast NBA video into court-space behavioral features: YOLOv8 player/ball detection, SIFT-homography court registration, Kalman + Hungarian multi-object tracking, and OSNet re-identification — running on a single consumer GPU at ~$0.10/game.
- Engineered the full system solo: ~6,000-file monorepo with a FastAPI service (~49 endpoints), 9 background daemons, web scrapers, a PostgreSQL store, live dashboards, and CI/CD — all in one continuous git history.
- Designed a rigorous ML validation discipline — walk-forward cross-validation, shadow-logging of live predictions, automated leak detection, and hard ship-gates — so that no model reaches production without out-of-sample evidence.
- Created an agentic discovery loop (Opus/Sonnet) that proposes and tests features against those ship-gates, treating verifiers adversarially (they must try to *refute* each claim) to suppress false positives from small-sample noise.
- Caught and documented my own overclaims: a headline ROI that turned out to be a market-following artifact (true ROI ≈ −4% vs. real closing lines), a calibration win driven by a fourth-quarter data leak, and an in-play edge that was a proxy-line artifact — all corrected in the repo rather than buried.
- Distilled the lesson into a reusable principle: validate against the real economic baseline (closing lines), not against MAE or in-sample backtests — and trust orthogonality and effect-size evidence over point estimates from a single favorable window.

*Trim to 4 bullets (keep 1, 2, 3, 5) if space is tight.*

### 3.3 — Computer Vision (detailed, 4 bullets)

**Computer Vision — broadcast video to court-space behavioral features (solo, production)**

- Built an end-to-end CV tracking pipeline that turns raw NBA broadcast video into court-coordinate player/ball tracks on a single consumer GPU at **~$0.10–0.13 per game** — vs. six-/seven-figure annual licensing for Sportradar/Second Spectrum tracking feeds. Stack: **YOLOv8n** detection → **SIFT + RANSAC homography** (court rectification) → **Kalman + Hungarian** multi-object tracking → **OSNet re-ID** → **OCR** for scoreboard/jersey reads.
- Implemented court rectification by extracting **SIFT** features and solving a frame-to-court **homography with `cv2.findHomography` (RANSAC, 5px reprojection threshold)**, stabilized with EMA smoothing and an inlier-count quality gate that rejects noisy frames — mapping pixel detections into metric court coordinates needed for downstream spacing/distance features.
- Engineered the multi-object tracker for occlusion robustness: per-track **Kalman filters** predict position through missed detections, globally optimal **Hungarian assignment** (`scipy.optimize.linear_sum_assignment`, with a `lapx` fast path) eliminates greedy ID switches, and a **256-dim OSNet-x0.25 appearance embedding** (PyTorch, hand-implemented; MobileNetV2 → HSV-histogram fallback chain) drives a lost-track gallery to re-ID players who exit and re-enter frame. Added **PaddleOCR→EasyOCR** scoreboard/jersey reading for game-state and identity binding.
- Derived court-space behavioral features (`defender_distance`, `spacing_entropy`, `fatigue_decay`, `paint_dwell_pct`) from the tracks for downstream prop models; tracked **85 games end-to-end with 7 at full feature extraction**. Honest gap, documented in `docs/KNOWN_LIMITATIONS.md`: stable **per-player** identity attribution stays low (~4%) across long occlusions, so I scoped CV output to **aggregate team-/position-level** features (which are ship-ready) rather than overclaim per-player tracking.

*Bullet 4 front-loads the per-player ~4% limitation as an honesty signal — keep it. Drop the fallback-chain parenthetical in bullet 3 if space is tight; merge bullets 2+3 for a 3-bullet version.*

### 3.4 — ML modeling + validation methodology (4 bullets)

**ML Validation & Modeling — NBA Prop Prediction System** (solo, Python / XGBoost / scikit-learn)

- Built a **walk-forward backtesting harness** (train on [start, T], predict the next week, roll forward) scoring every prediction against **real DK / FanDuel / Pinnacle closing lines** — not flat-odds fiction — reporting ROI, hit rate, Sharpe, and closing-line value (CLV) bucketed by data-confidence, so model quality is measured the way the bet actually settles.
- Engineered a **leak-detection gate** into the retrain pipeline: an automated train-vs-holdout R² gap check (configurable threshold, hard CI fail) plus a holdout time-gap validator, after auditing and **catching my own data leaks** (a Q4-contaminated in-play model, a closing-line feature feeding back into training targets).
- Implemented **per-stat post-hoc calibration** (isotonic / out-of-fold) and found the non-obvious result that calibration *helps* stats the model loses to the market on but *destroys* the one it beats (assist props) — so calibration is applied selectively, validated on ROI-vs-market rather than MAE, and shipped behind a default-off flag.
- Stood up a **shadow-logging system** that records new signals live without affecting served predictions, gated behind an agentic discover→validate→ship loop with hard ship criteria (orthogonality, ≥2 independent corpora, cross-season replication); the discipline **caught and retired my own overclaims** — most notably a headline ROI that I traced to a market-follow artifact (closer to break-even on real odds) and documented openly rather than shipped.

*Drop bullet 3 (calibration) for a generalist eng role. If a recruiter wants a single line, lead with bullet 2.*

### 3.5 — Backend / Systems (4 bullets)

**Backend & Distributed Systems — NBA Analytics Platform (solo, ~~3 months)**

- Built and operated a FastAPI service exposing 100+ endpoints (live game state, model predictions, line-shopping, CLV, risk/execution) backing a real-time betting dashboard — sub-second prediction serving with a feature-flag-gated calibration layer so model changes ship byte-identical-by-default and roll out behind env switches.
- Designed a fleet of 17 long-running Python daemons (multi-sportsbook odds scrapers, injury/lineup feeds, line-move and arbitrage detectors, settlement/bankroll monitors) coordinated by a registry-driven watchdog that tracks per-daemon heartbeats and auto-restarts any process whose heartbeat exceeds 3x its expected interval.
- Engineered the persistence layer on PostgreSQL with idempotent schema migrations and a transparent SQLite fallback that shares one cursor interface, so the full stack runs locally with zero database setup and unchanged in production — plus Docker/docker-compose images for API, dashboard, and CV workers.
- Stood up CI/CD on GitHub Actions (ruff lint, multi-version pytest matrix, ~580 test files, enforced coverage gate) and ran the production stack on a single consumer GPU at roughly $0.10/processed game by decoupling the GPU-bound CV pipeline from the always-on CPU serving daemons.

*"100+" endpoints is the honest floor (119 routed); 17 daemons per `daemon_registry.json`. Trim to 3 by dropping the CI/CD line. Keep the $0.10/game figure only if defensible, else cut the trailing clause.*

### 3.6 — AI agents / autonomous ML systems (3 bullets)

**AI agents / autonomous ML systems — selected bullets**

- Built an autonomous discovery loop that uses Claude agents (Opus orchestrating, Sonnet writing code) to mine model residuals, propose candidate prediction signals, and ship or retire them without a human in the loop — every candidate must clear a 5-criterion "honest gate" (all walk-forward folds improve, beats a shuffled-label null, positive marginal lift when ablated against the *full* production feature matrix, calibration, and closing-line value) with Benjamini–Hochberg correction across all tested signals and a held-out set touched exactly once.
- Engineered the loop's hard ship gates specifically to defeat the failure mode of automated research — false positives from multiple comparisons and data leakage: the gate scores marginal lift against the full model (not the signal in isolation), defaults to DEFER rather than SHIP when data coverage is insufficient, and runs leak-safe as-of feature construction. The same rigor caught my *own* overclaims — I traced a headline ROI result to a market-following grading artifact (real ≈ −4%) and documented it rather than shipping it.
- Ran a 21-agent adversarial code-audit sweep over the live prediction-and-betting serve path in which verifier agents were required to *refute* each finding with a runnable probe before it counted — surfaced 8 confirmed correctness bugs (e.g., a feature-slot misalignment feeding 5/85 features to the wrong model inputs on every live prediction; a covariance sign-flip overstating parlay EV ~3×). Shipped each fix gated default-OFF and byte-identical until A/B-validated, since the path moves real money.

*For a tighter resume, keep bullets 1 and 3 and fold the leak point into bullet 1. The bug examples in bullet 3 can be dropped.*

---

## 4. LinkedIn / About copy

### 4.1 — Headline options (all under ~220 chars)

**Option 1 — CV + ML systems (skills-first):**
ML Systems Engineer | Computer vision in production (YOLOv8, SIFT homography, Kalman/Hungarian tracking, OSNet re-ID) | Built a 6,000-file FastAPI platform: video → court coordinates → features → predictions

**Option 2 — Methodology + honesty signal:**
Solo-built an end-to-end NBA CV→ML→serving platform (49 endpoints, 9 daemons, walk-forward CV, leak detection) | I find and document my own overclaims | Self-taught, senior-level systems engineer

**Option 3 — Tight, breadth + rigor:**
Full-stack ML engineer: broadcast video → tracking → behavioral features → real-time inference | YOLOv8 · homography · re-ID · FastAPI · walk-forward validation | Rigorous about leakage and what's actually real

*Option 1 for keyword-scanning recruiters; Option 2 foregrounds the honesty differentiator (strongest for senior/research audiences); Option 3 is the balanced one-liner. Swap "Self-taught" in/out of Option 2 to taste.*

### 4.2 — About section

I spent the last ~3 months solo-building an NBA analytics platform end-to-end: broadcast video in, structured predictions out. No CS degree — just a problem I couldn't put down and a habit of checking my own work.

The computer vision runs in production on a consumer GPU at roughly $0.10 a game: YOLOv8 detection, SIFT homography to map plays to court coordinates, Kalman + Hungarian tracking, and OSNet re-ID. On top of that sits a real system — FastAPI with ~49 endpoints, 9 daemons, scrapers, PostgreSQL, dashboards, CI/CD — all in one git history of ~6,000 files.

What I'm most proud of isn't a number. It's the validation discipline: walk-forward CV, shadow-logging, leak detection, and an agentic discovery loop with hard ship gates that has caught my own overclaims — including a data leak and a ROI artifact I'd initially believed.

The domain is betting. The skills — CV, rigorous ML, systems — travel anywhere. Happy to talk shop.

### 4.3 — GitHub profile README

```markdown
# Hi, I'm Neel 👋

I build end-to-end ML systems. For the last ~3 months I've been solo-building **CourtVision** — a pipeline that turns broadcast NBA video into court coordinates, behavioral features, and predictions, then validates whether any of it is actually edge.

No CS degree. The work is the credential.

---

### 🏀 CourtVision — broadcast video → coordinates → features → predictions
**[github.com/neeljshah/court-vision](https://github.com/neeljshah/court-vision)**

A single git history spanning computer vision, ML, data engineering, and serving — ~6,000 files built and maintained alone.

**Computer vision (the hard part), running on one consumer GPU at ~$0.10/game:**
- YOLOv8 player/ball detection → Kalman + Hungarian tracking → **OSNet re-ID** to keep identities through occlusion
- **SIFT homography** to rectify the broadcast frame to real court coordinates
- Jersey/scoreboard OCR, possession + play-type classification, defensive-scheme detection
- Coordinates feed ~20 behavioral analytics modules (spacing, drives, pick-and-roll, passing networks, rebound positioning)

**Systems breadth:**
- **FastAPI** backend, ~49 endpoints across 12 routers (tracking, predictions, lines, CLV, live game, dashboards)
- **9 background daemons**, web scrapers, **PostgreSQL**, React dashboards, CI/CD
- A self-improving agentic discovery loop (Opus/Sonnet) that proposes features and gates them behind hard ship criteria

---

### 🔬 What I actually care about: validation that catches its own mistakes

Most of the engineering effort went into *not fooling myself*. The pipeline uses **walk-forward cross-validation**, **shadow-logging** (new signals run silently in prod before they ship), **leak detection**, and **feature flags defaulted OFF** so nothing changes behavior until it's earned it.

It works — because it has caught me:
- I traced a headline "betting ROI" back to a **market-follow artifact** (the grader was quietly betting the book's own favorite at fictional odds). Real number was negative. I documented it and retired the claim.
- I found a **Q4 data leak** inflating an in-game win-probability metric, and an in-play result that was really an L5 proxy, not live lines.

I'd rather ship one honest +5% signal than five that evaporate out-of-sample. Out of ~40 experiments in the latest sweep, most got **rejected** — by design.

---

### 🛠️ Tech
`Python` · `PyTorch` · `OpenCV` · `YOLOv8 / OSNet` · `NumPy / Pandas` · `FastAPI` · `PostgreSQL` · `React` · `Docker` · CV · time-series ML · walk-forward validation

### Honest gaps
Betting was the **problem space**, not the product — the transferable wins are the CV pipeline, the systems design, and the validation discipline. The model is roughly market-efficient on most props; the durable edges are narrow and I size them as such. Cross-season generalization is still partly unproven, and I say so in the docs.

📫 neeljshah22@gmail.com
```

*Paste into a repo named `neeljshah` to make it your profile landing page. Confirm the repo is public at the URL and update counts if changed.*

### 4.4 — Portfolio one-pager (attach/link as PDF)

> **# Neel Shah — ML Systems & Computer Vision**
> neeljshah22@gmail.com · github.com/neeljshah/court-vision
>
> Self-taught engineer (no CS degree). For ~3 months I solo-built **CourtVision**: an end-to-end platform that turns broadcast NBA video into court coordinates, behavioral features, and validated predictions. One person, one git history. The betting domain is just the forcing function — the transferable work is production CV, rigorous ML validation, and systems breadth.
>
> **What it does:** Broadcast video → player/ball tracking → court-space features → ML models → a live FastAPI dashboard. Built to run on a single consumer GPU at roughly **$0.10/game**.
>
> **Defensible highlights:**
> - **Computer vision in production.** A full tracking stack — YOLOv8 detection, SIFT homography for court rectification, Kalman + Hungarian tracking, OSNet re-ID, jersey OCR — that maps a 2D broadcast feed into real court coordinates and per-player behavioral features. (`src/tracking/`: ~20+ purpose-built modules.)
> - **System breadth, end to end.** FastAPI service with ~90 routes across a dozen routers, plus background daemons, scrapers, a PostgreSQL store, dashboards, Docker images, and CI — all integrated in a single repo. I own every layer from frame decode to served endpoint.
> - **ML validation methodology I actually trust.** Walk-forward / rolling-origin CV, shadow-logging, explicit leak detection, orthogonality screening, and feature flags gated OFF by default so nothing ships byte-changing without an A/B. I treat held-out ROI vs. real closing lines — not in-sample MAE — as the bar.
> - **An agentic discovery loop with hard ship gates.** A self-improving loop (orchestrated Opus/Sonnet agents) proposes features, then must clear independent-corpus gates before anything is recommended. Most candidates are honestly *rejected*.
> - **Intellectual honesty as a feature.** I've caught and documented my own overclaims: a headline ROI that turned out to be a market-follow artifact (real ≈ −4%), and model-skill numbers inflated by a data leak. The audit trail of refuted hypotheses is in the repo — I'd rather kill a result than ship a mirage.
>
> **Honest gaps:** Live betting edge is thin-to-negative on most stats; the durable signals are narrow and regime-dependent. The defensible claims are the engineering and the methodology, not the returns.
>
> **Links:** Code → github.com/neeljshah/court-vision · Architecture & audit notes in-repo (`ARCHITECTURE.md`, `docs/_audits/`).

---

## 5. Interview-prep talking points

> These are prep notes to internalize, **not scripts to read verbatim**. Lead with the short version, then go deep on whichever thread the interviewer pulls. The honesty beats are the actual hire signal — keep them to a sentence or two and don't spiral. **Never quote the +18.38% / Brier-0.119 / +54% numbers as wins** — they appear only as artifacts you caught.

### 5.1 — "Walk me through your CV pipeline end-to-end" (~75 sec)

The input is a broadcast NBA clip — the same TV feed you'd watch at home — and the output is per-player court coordinates and behavioral features. No camera rig, no tracking-chip data. Runs on a consumer GPU at ~$0.10/game. **Five stages: detect → homography → track → re-ID → events/features.**

- **1. Detection.** Each frame → YOLOv8 for players, ball, rim. I gate frames first: if YOLO sees too few people it's a replay/commercial, so I skip and cache that decision instead of burning GPU on dead air.
- **2. Homography (the hard part).** A pixel detection is useless; I need court space — feet from the baseline. The broadcast camera pans/zooms constantly, so I stitch a stable panorama of the court once per clip, then register each frame back to it with SIFT + a FLANN matcher, solving the homography with RANSAC. The honest problem: broadcast frames give only 5–7 good inliers, so a raw per-frame solve jitters and drifts. Three fixes: a minimum-inlier gate that falls back to the last good matrix, an EMA so the matrix can't snap frame-to-frame, and a periodic court-line re-anchor to catch slow drift over a ~60,000-frame game. I also suspend homography on scene cuts via an SSIM/brightness check.
- **3. Tracking.** Per-player Kalman filter for motion prediction + Hungarian assignment each frame, cost = a blend of IoU and appearance distance, run as two passes (tight appearance-aware, then loose IoU-only recovery).
- **4. Re-ID.** When a track is lost and reappears, IoU fails, so I match on OSNet appearance embeddings (learned features, not color histograms — critical when both teams wear similar colors), with an EMA-smoothed gallery per player and jersey-number OCR as a tiebreaker. Serves a TensorRT FP16 engine when available, falls back to PyTorch then a color histogram, so it degrades instead of crashing.
- **5. Events/features.** EasyOCR reads jersey numbers and game clock, an event detector flags shots/makes, and downstream I turn tracks into the behavioral features that are the point — defender distance, spacing, fatigue proxies, play type.

*Honesty beat:* the CV layer is solid on the games I've processed; the biggest open limitation is scaling to a full season of footage — that's documented, not hidden. The fallbacks aren't over-engineering; broadcast video genuinely doesn't give clean inliers.

**Drill-in answers:** *Why a panorama not a fixed template?* — the camera moves every frame; registering to a stitched panorama of that clip gives a reference the live frame actually overlaps. *Why OSNet over histograms?* — histograms fail exactly when you need re-ID (similar colors, crossings); learned features separate them; kept histogram as last-resort fallback. *What breaks it?* — low-inlier homography drift (hence the gate/EMA/re-anchor) and occlusion clusters that mis-swap players (hence appearance cost + OCR tiebreaker). *How do you know it's right?* — cross-validate derived stats against the public NBA Stats API and run a frame-level benchmark on a fresh clip each iteration.

### 5.2 — Hardest technical problem: stabilizing broadcast → court homography

**One-liner:** The hardest problem wasn't a model — it was a *stable* mapping from a moving broadcast camera to fixed court coordinates. Everything downstream is a geometric measurement, so a few pixels of drift quietly corrupts every behavioral feature. Per-frame SIFT homography is easy; a per-frame homography that doesn't jitter, teleport, or slowly drift over a 48-minute game was the real work.

**Why it's hard:** `cv2.findHomography` gives an independent matrix per frame, so the court "breathes." Features are distances in feet (converted against the panorama's 94-ft axis), so homography error propagates linearly into every distance field. Three distinct failure modes — high-frequency jitter, single-bad-match teleport, slow accumulating drift — each need a different fix. And it has to run at ~$0.10/game, so no heavy per-frame deep matcher.

**What I built:** (1) Anchor to a per-clip panorama, not frame-to-frame, so error can't compound — gotcha caught: very long stitched panoramas (~30:1 aspect) actually break SIFT registration, so a short stable stitch window beats a longer one. (2) A three-tier inlier gate on the RANSAC result: below threshold → reject, hold last good matrix; ≥40 inliers → hard-reset the smoother to discard drift; in between → EMA-blend. (3) Drift re-anchoring: project the four court boundary lines back through the inverse homography and measure how many land on actual white court-line pixels; low alignment → snap to the freshest clean match. (4) A coupled-matrix invariant `M1 = M1_raw_clip @ inv(M_ema)` re-derived on every smoother update (with a singular-matrix guard) — getting it wrong silently rotates the whole court. (5) Cost engineering: scene-change histogram gate skips matching when there's no cut, SIFT runs on a downsampled ROI with the top 30% (scoreboard/crowd) cropped, heavy matcher runs on an interval while Kalman carries positions.

*How I knew it worked:* the back-projection white-pixel alignment check doubles as a self-consistency eval that needs no hand labels; cross-validated against NBA Stats API where they overlap. Source of truth: `src/pipeline/unified_pipeline.py` (`_get_homography`, `_check_court_drift`, `_build_panorama`, the `M1` invariant), `_px_to_ft`, and `src/tracking/osnet_reid.py`.

*Pick the inlier gate + drift re-anchoring + the M1 invariant if you only have time for three — they're the most senior-sounding. Always land the honesty beat at the end.*

### 5.3 — "How do you know your model works? How do you validate?"

**30-sec version:** I treat every result as guilty until proven innocent. The whole system is built around catching myself being wrong: walk-forward validation so I never test on the past, shadow-logging so a new model has to prove itself on unseen live data before it's trusted, and explicit leak detection. The proof the methodology works is that it caught two of my own overclaims — a data leak inflating one model's scores, and a "profitable" backtest that turned out to be following the market, not beating it. I'd rather kill my own result than ship a number I can't defend.

**Four pillars (go deep on any one):**
1. **Walk-forward / OOS by construction.** Train only on games before a cutoff, test forward, roll the origin. No random K-fold — a random split lets the model see a season's future.
2. **Shadow-logging before trust.** A new model runs in parallel logging against live games it never trained on; it earns promotion only by beating the incumbent on genuinely unseen data.
3. **Explicit leak detection — and it has fired on me.** An in-game win-prob model looked excellent at end-of-Q3 until I traced the inputs and found Q4 information bleeding into a "pre-Q4" feature. Real score, meaningless model. Documented as a leak rather than kept.
4. **Validate against the right target — the market, not just MAE.** Minimizing MAE pulls forecasts toward the conditional mean = toward the line, so better "accuracy" can *destroy* edge on exactly the markets you beat. I validate betting claims against real closing odds (ROI vs. Vegas), not accuracy metrics.

**The self-caught overclaim (the story):** My headline backtest showed a strongly profitable prop strategy. When I reverse-engineered where the edge came from, the grader was effectively betting the market's own implied favorite (model unused), with in-sample-tuned filters and idealized −110 pricing. At real book odds the edge was break-even-to-negative — the model was following the market, not beating it. I wrote that up against my own prior claim. An impressive number is a hypothesis, not a result; the job is to attack it until it survives or dies.

**Guardrails:** hard pre-registered ship gates across ≥2 independent corpora; default-OFF byte-identical flags; recommend-don't-auto-apply for real-money logic; distrust single-window peaks (check cross-regime replication before believing magnitude). *One-liner to close on:* "I can't promise every model I build will work. I can promise I'll know whether it does — and I'll tell you the truth either way."

### 5.4 — "What's your actual edge? Does it make money?"

**Honest one-liner:** My model is competitive with the market but doesn't reliably beat the closing line — and the most valuable thing I built was the validation discipline that let me *prove* that to myself instead of believing my own backtest.

**90-sec answer:** The headline ROI looked like a money printer. It wasn't, and finding out why is the part I'm proud of. The headline was a **market-follow artifact** (grader bet the market's devig favorite, in-sample filters, flat −110 fiction) — priced against real DK/FD/MGM closes it's roughly **break-even to slightly negative**. Two other "wins" had leaks: a Brier score leaking Q4 into the Q3 prediction, and an "in-play" edge graded against an L5 proxy. What survives honest OOS testing: the model is genuinely accurate, but accuracy isn't edge; the closing line is efficient on the stats I tested; no pregame matchup conditioner I built beats it OOS at real odds. The one signal that repeatedly survives is small and regime-dependent — a modest assists lever, **~5% durable** (not the ~19% peak my first cut showed), and it collapses in the playoffs, so I size on the 5%. **Does it make money?** Not durably against closing lines — and I can defend that number. The realistic edge, if any, lives in **same-day freshness** (betting an opener before a roster move shifts the line), not a cleverer closing-line feature.

**Follow-ups:** *Why build it if it doesn't beat the close?* — the transferable product is the CV pipeline and a validation methodology that holds up; an efficient market is the hardest possible grader for "is my signal real," which forced the rigor. *How do you know your validation isn't also fooling you?* — that's why I require independent corpora and grading against real prices, not flat −110; two positive corpora once misled me into a "ship," the third refuted it. *What would you need to make money?* — lower-latency same-day info against opening lines and the plumbing to act before the market — not a better closing-line feature.

### 5.5 — The sports-betting domain (problem space vs. product)

**One-sentence framing:** I picked sports betting because it's a brutally honest problem space — a live market of professionals on the other side of every prediction, so you can't fool yourself about whether your model works. The skills are the product: computer vision, ML validation, systems engineering. Betting was the forcing function that kept me rigorous.

- **Why betting:** adversarial, ground-truth-rich, punishes self-deception immediately (overfit → the market takes your money), and is genuinely hard end-to-end (video in, a defensible probabilistic decision out).
- **The pivot:** "Don't evaluate me on betting returns — evaluate me on the engineering and the methodology." Then name the CV stack, the system breadth (~6,000 files, ~49 endpoints, 9 daemons), and the validation methodology.
- **The honesty proof (volunteer it):** "My most impressive result was a fake." The pregame ROI was a market-follow + flat-pricing artifact; real ≈ negative. Plus the Q4 leak and the proxy-line in-play edge. I documented all three. I trust MAE/orthogonality over headline ROI because small-sample returns are noise-dominated.
- **Risk/ethics (say proactively):** I never operated this as a gambling business — no users, no scaled real-money operation; it's a research/engineering platform, betting is the benchmark. I'm clear-eyed about gambling's social harm, which is exactly why I'd apply the same skills somewhere constructive — fraud detection, sports analytics, video understanding, sensor/tracking systems.

**Soundbites:** "The market is an adversary that's already priced in what you know — best calibration check in the world." · "My most impressive result was a fake, and finding that is the result I'm proudest of." · "Betting is the problem space. CV, ML rigor, and systems are the product."

### 5.6 — "What would you do differently / what did you learn?"

Structure each as decision → what went wrong → lesson → how I work now.

1. **Trusted a great-looking ROI before the methodology that produced it.** When I rebuilt the harness the "edge" largely vanished (market-follow + flat-odds fiction). Lesson: a backtest is software with flattering bugs; the headline metric is the least trustworthy number until adversarially attacked. Now: build the eval harness *before* the model, grade against real historical closes from day one, never report ROI without the exact odds source and bet-selection rule.
2. **Let validation leak — silently.** A Q4-into-pre-Q4 leak; an "in-play edge" measured against an L5 proxy. Lesson: leaks show up as *good* results. Now: temporal/as-of correctness is a tested invariant, and any metric jump triggers a leak audit before celebration.
3. **Over-trusted small-sample point estimates.** Two confirming corpora said "ship"; a third refuted it. Even the assists edge was a regime-inflated peak. Lesson: trust mechanism-level evidence (MAE, orthogonality, why the signal should exist) over flashy aggregates. Now: pre-register the gate, require an independent third corpus, size on the conservative durable estimate.
4. **Separated "more accurate" from "actually profitable" too late.** Minimizing error pulls predictions toward the line, so calibration helps stats I lose to Vegas and *hurts* the one I beat. Lesson: optimize the metric that matches the goal — MAE is not ROI. Now: define the true objective up front, apply accuracy gains selectively.
5. **Moved too fast on an undocumented, untracked codebase.** Hallucinated an API and overwrote untracked files; recovered from surviving tests. Lesson: read the real interface and tests before editing. Now: everything under version control, gated default-off byte-identical flags so risk is opt-in.
6. **Meta-lesson: the skill that compounded was skepticism, not modeling.** My best work was catching my own overclaims. The honest negative ("this edge isn't real") is a deliverable, not a failure. "I'd rather tell you a number is −4% and true than +18% and wrong."

*Lead with point 6 or point 1 if you only have time for one.*

### 5.7 — "Why solo for ~3 months / how do you collaborate?"

**30-sec:** I went solo to own the whole stack and learn it for real — nobody hands you a CV-to-production problem at this scope, so I built it: ~6,000 files, one git history, CV on a consumer GPU at ~$0.10/game. The thing I'm proud of isn't a return — it's that the system is built to catch its own mistakes, and I've killed several of my own results. That's the discipline I'd bring to a team, and a team is exactly what I'm looking for now.

- **Why solo (own it):** it was the only way to get the scope; it forced real ownership (when a daemon dies at 2am there's no one else); I treated my own work adversarially (the discovery loop's whole job is to keep me from fooling myself, and it caught a Q4 leak and the market-follow artifact).
- **How I collaborate (reframe):** solo was a season, not a preference — I've hit the ceiling of what one person should do alone, and review/division-of-labor/people who challenge me are upgrades I want. I already work like a good teammate: small commits, written decision records, auditable ship gates, documenting what *didn't* work. I take review well because I review myself harder.
- **Honest gaps (volunteer them):** I haven't worked in a multi-engineer codebase with shared on-call, sprint cadence, or someone else's architecture — that's new, and part of why I want this role. On a team I'd default to asking and aligning earlier.
- **"Isn't solo a red flag for teamwork?"** The risk with solo builders is they can't take feedback. My evidence is the opposite — I built a system whose job is to tell me I'm wrong and I publish my own refutations. I'm not looking to keep working alone; I want people who'll make the work better.

### 5.8 — Recruiter / hiring-manager objection handling

Each rebuttal: concede, then pivot to demonstrated evidence.

1. **"No CS degree — can he engineer at a senior level?"** The work is the credential. One git history holds a full CV → ML → serving platform (YOLOv8, SIFT homography, Kalman+Hungarian, OSNet re-ID at ~$0.10/game; FastAPI ~49 endpoints, 9 daemons, scrapers, Postgres, CI/CD). That's the surface a senior IC owns. Judge the repo, not the transcript.
2. **"Solo project — maintainable code, or code that works for one person?"** Fair — no large-team-process claim. But: module boundaries that let features ship behind default-OFF byte-identical flags, regression suites gating changes, shadow-logging before cutover. That's hand-off discipline; it just hasn't been stress-tested by reviewers yet, and he'd treat code review as a benefit.
3. **"A betting bot — serious engineer or gambler?"** Betting is the problem space — adversarial, low-signal, forces rigor. The transferable product is the methodology (walk-forward CV, leak detection, ship gates, OOS across independent corpora), which moves directly to fraud, forecasting, recommendations.
4. **"Will I get inflated numbers?"** No — and it's the strongest signal. He caught and *documented* his own overclaims (market-follow ROI artifact, data-leak-inflated skill claim, proxy-line in-play result) before anyone audited him. An engineer who refutes his own best result is who you want validating revenue-touching models.
5. **"~3 months solo with AI — is the depth real, or did agents think for him?"** The hard parts are human judgment: homography surviving camera cuts, re-ID through occlusion, separating edge from leakage, designing gates that *reject* most candidates. He uses agentic loops as a breadth multiplier while owning architecture, validation design, and the kill calls. Orchestrating agents *and* not trusting their output blindly is a forward-looking strength.

**One-line close:** The product isn't the betting returns — it's a built-from-scratch CV/ML/systems platform and the rare honesty to say which of its own results don't hold up.

### 5.9 — First 90 days (leave-behind after a strong interview)

*Scope/dates are placeholders to rewrite with the manager on day one. The goal is to de-risk the hire.*

- **Days 0–30 (land, ship small, build judgment):** ship a real PR in week one to learn review culture / CI / deploy; map the system before changing it and turn confusion into onboarding docs; reproduce a core result the team already trusts; set up a weekly what-I-shipped / what-I-got-wrong loop with the manager. *Why fast:* ~3 months solo-operating a system in this shape (FastAPI, daemons, scrapers, Postgres, a CV inference path, CI) means the architecture won't be foreign.
- **Days 30–60 (own a vertical slice; bring the rigor):** own one component end-to-end off the critical path; add validation rigor where it's missing (walk-forward eval, leak detection, shadow-logging a change against prod before it affects anything — the discipline that caught my own leak and market-follow artifact); instrument what I own with a dashboard/alert; write the postmortem on my own first miss openly.
- **Days 60–90 (propose where I add leverage):** ship the 30–60 component behind a flag/gradual rollout with monitoring in place; bring one well-validated proposal (efficiency / accuracy / reliability / cost — I cut per-unit CV inference to ~$0.10/game, so I care about unit economics) with evidence, risk, and an honest statement of what would make me wrong; reduce bus factor by documenting/automating; calibrate against the team on where my judgment is trusted.
- **Explicitly not promising:** a headline metric by day 90 (anyone who promises that hasn't met your data); to be net-positive in week one (onboarding is a real cost). No CS degree — what I offer is demonstrated senior-level work in one git history and a track record of catching my own overclaims.

---

## 6. Target roles & where to apply

### 6.1 — Seniority call

- **Founding / early-stage IC:** apply at **senior / founding** level — breadth + judgment carry it.
- **Established-company ML/CV/Applied:** target **mid (L3–L4 / SWE II–III)** with a genuine shot at **senior** when the team prizes autonomy and validation rigor.
- **Avoid for now:** Staff/Principal, and any role whose bar is "led a team / owned org-wide infra." Claiming it would undercut the one thing that makes him stand out — that he tells the truth about his own work.

### 6.2 — Role tiers (where to spend application effort)

**Tier 1 — strongest fit (target first):**
1. **Founding / Early Engineer (seed–Series A)** — the single best match ("Founding Engineer," "Member of Technical Staff," "Engineer #2–10"). Independently shipped across the entire stack; founders hire on demonstrated output, so the no-degree concern is weakest here.
2. **Applied ML / ML Engineer** — sell methodology, not metrics: walk-forward CV with purge windows, shadow-logging, leak detection, hard ship gates, and the documented self-skepticism. Mid-level, credible senior case at the right team.
3. **Computer Vision Engineer** — production CV from messy broadcast video at ~$0.10/game is concrete and rare; he's debugged the unglamorous failure modes (homography drift, re-ID swaps, ball dropout). Gap: classical-CV + applied DL, not research-track novel-architecture CV.

**Tier 2 — viable, position carefully:**
4. **Data Engineer / ML Platform / MLOps** — real platform work (daemon fleet, scrapers, model registry, settlement loop) but grew organically for one operator. Frame as "I built and operated the pipelines," not "designed team-scale standards."
5. **Quant / sports-modeling** — only if he leads with the honest version. The strength is the rigor (leak-aware validation, CLV thinking, Kelly sizing, killing signals that don't replicate). **Do not lead with betting returns** — the headline numbers are known-soft; leading with them invites the scrutiny that turns the story negative.

### 6.3 — Target companies (anchor names to branch from)

The product is three transferable skills (production CV / system breadth / validation rigor + honesty), not "NBA betting." Lead with the skill that matters most to each buyer.

- **Tier 1 — direct CV transfer (lead with the vision pipeline):**
  - *Sports analytics / sports-tech:* Hawk-Eye (Sony), Genius Sports, Sportradar, Stats Perform / Opta, Second Spectrum, PFF, Sportlogiq, Track160, Pixellot, Veo, Hudl, KINEXON, SkillCorner, Swish Analytics, Statsbomb. **Why he wins:** most run multi-camera/fixed rigs; he did it from single broadcast feeds on a consumer GPU — "the same thing without your camera rigs."
  - *General CV startups (non-sports):* Standard AI, Trigo, Verkada, Ambient.ai, Covariant, Skydio, Anduril, Path Robotics, Landing AI, Roboflow, Voxel51, Encord, Scale AI, Tractable, Viz.ai, PathAI. Verticals: retail/store analytics, warehouse vision, robotics perception, drones, medical imaging, manufacturing QA, agtech, security, geospatial.
- **Tier 2 — applied ML + methodology (lead with rigor + honesty):**
  - *ML-infra / MLOps:* Weights & Biases, Comet, Arize, WhyLabs, Predibase, Modal, Baseten, Together AI, Fireworks, Hex, Hugging Face, Galileo.
  - *Time-series / forecasting / decision systems:* Nixtla, Faire, Flexport, Pricefx, Sift, Sardine, Unit21, o9. Verticals: demand forecasting, energy/grid, supply chain, pricing, fraud/risk.
- **Tier 3 — trading / quant (lead with honest signal-vs-noise judgment):** Jane Street, HRT, Two Sigma, Citadel / Citadel Securities, Jump, DRW, IMC, Optiver, SIG, Akuna, Cubist, Voleon, Tower; crypto: Jump Crypto, Wintermute, GSR. **The honesty lever:** most candidates show a backtest that "made money"; his strongest signal is the opposite — he found his own ROI was a market-follow artifact and wrote it down. Caveat: no formal stats/finance pedigree, so target research-engineer tracks / dev-heavy desks. *Betting operators (problem-space-native, use sparingly):* DraftKings, FanDuel, Underdog, PrizePicks, Kalshi, Polymarket, Pinnacle.
- **Tier 4 — dev-tools / agentic AI (lead with the discovery loop):** Anthropic, Cursor / Anysphere, Cognition, Factory, Sourcegraph, Replit, Warp, All Hands AI, Augment, Codeium/Windsurf, Braintrust.

### 6.4 — How to find the specific (currently-hiring) names

1. **Mine YC** — `ycombinator.com/companies`, filter tags: `computer-vision`, `machine-learning`, `sports`, `dev-tools`, `fintech`, `robotics`. Densest source of small, hungry, credential-agnostic teams.
2. **Follow the funding** — Crunchbase / PitchBook or "[vertical] startup Series A 2025/2026"; seed→Series B is the sweet spot for show-me-the-work hiring.
3. **Read the papers, find the labs** — CVPR / ICCV / MIT Sloan Sports Analytics papers on tracking, re-ID, sports video; author affiliations = a curated buyer list.
4. **Reverse the job boards** — Wellfound / Otta / LinkedIn for postings with "homography," "multi-object tracking," "re-identification," "YOLO," "Kalman," "walk-forward," "backtest." Those companies want his exact resume.
5. **GitHub & arXiv adjacency** — orgs/contributors around Ultralytics/YOLO, OSNet, BoT-SORT, ByteTrack are warm targets.
6. **Conference sponsor lists** — Sloan Sports, CVPR sponsors, quant-recruiting events are pre-filtered.
7. **Match by problem, not industry** — anyone whose core problem is "video → structured signal" or "noisy time-series → sized decisions under feedback."

### 6.5 — Application channels (route around the resume screen)

The no-degree filter lives in ATS resume screens — so route around them. Priority: **Referral > Founder/EM direct outreach > Take-home/trial offer > Open-source visibility > Cold application.**

- **Tier 1 (skip the ATS):** founder/hiring-manager DMs at seed–Series B (YC's Work at a Startup, Wellfound, the monthly HN "Who is Hiring?" thread — search the comments for `computer vision` / `ML` / `video`); warm referrals via people who've seen the work (a referral converts ~10× a cold apply); take-home / paid-trial-friendly companies (volunteer one).
- **Tier 2 (niche boards, better signal-to-noise than LinkedIn):** the HN Who's Hiring thread (best single source), Wellfound, CV/ML Discords & Slacks; sports-tech companies directly (their problem *is* your project); remote-first boards.
- **Avoid as primary channels:** LinkedIn Easy Apply and big-corp ATS portals — strongest no-degree filter, least artifact visibility. Use only with a warm contact inside.
- **Sequencing (one week):** Day 1–2 polish the README (diagram + demo clip + named CV stack + cost/game) and pin the methodology doc; Day 2–3 build the second-degree referral map, pick 10 targets, find one mutual at each; Day 3–5 send 5 tailored founder/EM emails + 5 referral-intro asks; Day 5–7 publish one honest technical post-mortem (the self-audit story is the strongest, most-differentiated post). Run Tier 1 weekly; treat Tier 2 boards as a background queue. **Track replies, not sends.**

---

## 7. The no-degree framing

> **Frame:** I don't have the credential, but I have ~3 months of dated, public, reviewable evidence of senior-level work. **The git history is my transcript — and unlike a transcript, you can read every commit.** Lead with the work, point to the proof, be honest about the gaps. **Never substitute an inflated betting metric for the methodology + honesty pitch.**

### 7.1 — The one-line answer (say it first, then stop)

> "I don't have a CS degree. What I have instead is a public ~3-month git history of a production computer-vision and ML system I built solo — broadcast NBA video to court coordinates to a live serving stack. I'd rather you judge me on the code than on a credential, and it's all on GitHub: github.com/neeljshah/court-vision."

Then let them ask. Don't over-explain — the repo does the arguing.

### 7.2 — The "transcript" reframe (strongest move)

> "A transcript tells you I sat in a room for four years. My git history tells you what I actually built, when, and how I thought about it. You can read the commit where I caught my own data leak. You can't do that with a GPA."

Concrete specifics you can name (all real, all in the repo): ~2,800 Python files in one coherent system; ~116 API routes across the FastAPI layer; a real CV tracking module (`src/tracking/` — `court_detector.py`, `osnet_reid.py`, `advanced_tracker.py`, `rectify_court.py`); one git history, no resets, no squashing away the messy parts.

### 7.3 — Translate self-teaching into evidence of the job

> "Self-directed learning isn't a substitute for the degree — it's the same skill the job needs every day. Nobody handed me a syllabus for 'turn broadcast video into court coordinates on a $0.10/game budget.' I had to scope it, find the right techniques, and know when my own results were lying to me. That's the loop I'd be running on your team."

Techniques he taught himself and shipped (signal real CS depth, not tutorial-following): homography / camera geometry (SIFT + per-clip 3×3 homography mapping pixels to 2D court space); multi-object tracking (Kalman filter for occlusion prediction + Hungarian assignment via `scipy.optimize.linear_sum_assignment`); re-identification (OSNet-x0.25 implemented directly in PyTorch, not a wrapped library).

### 7.4 — The honesty signal (what actually closes a senior hire)

> "The most important thing I built isn't a model — it's a validation discipline that catches my own overclaims. I run walk-forward CV, shadow-logging, and explicit leak detection with hard ship-gates. And it works: I caught a data leak inflating one of my model's metrics, and I caught that a betting return I'd been quoting was a market-follow artifact, not real edge. I documented both *against my own interest* before anyone asked. I'd rather kill my own result than ship a number I can't defend."

A degree certifies you *can* be rigorous; this *demonstrates* you choose to be, even when the result hurts. That's the senior trait teams can't easily interview for — and you have receipts.

### 7.5 — Anticipated follow-ups

- **"How do we know you can work on a team?"** — "Fair; solo work doesn't prove collaboration, and I'd want to learn your review culture. What it proves: I maintain a large multi-service codebase with CI, tests, and 9 services, and I treat my own code adversarially — default-off flags, byte-identical fallbacks, regression tests before changes ship. Those habits make code reviewable by *other* people, not just me."
- **"Won't you have foundational gaps?"** — "Almost certainly, in spots — probably formal CS theory I never needed to ship video tracking. I'd rather name a gap than bluff one. The gaps a degree fills are usually breadth; depth I have, and I close breadth fast — that's literally how I built the whole thing."
- **"Why take the risk over a CS grad?"** — "Because the risk is unusually low to verify. You can clone the repo this afternoon. With a new grad you're projecting from coursework; with me you're reading shipped, dated, instrumented work — including the parts where I corrected myself."
- **"What would you do differently with formal training?"** — "I'd have reinvented fewer wheels and known the standard names for things I rediscovered. The flip side is I understand those pieces from the inside because I had to build them."

### 7.6 — Delivery rules

- Lead with the work, not the apology. Never open with "I know I don't have a degree, but…".
- Offer the repo early and specifically. "It's all public" is a flex only a builder can make.
- Name one gap honestly per conversation — it buys credibility for everything else.
- **Do NOT cite betting returns as proof of skill.** The pitch is CV + ML rigor + systems + honesty. If betting comes up, it's the problem space, and the honest framing is: "the model itself doesn't reliably beat closing lines — I proved that to myself, which is the point."
- Stop talking after the answer. Confidence is brevity. Let them probe.

### 7.7 — The reusable one-liner (everywhere a degree would go)

> **Solo-built a ~3-month, ~6,000-file CV→ML→production platform: real-time broadcast-video tracking on a consumer GPU, FastAPI backend (~49 endpoints, 9 daemons), and a walk-forward validation harness that catches its own overclaims.**

---

*Two artifacts cite a different file count (~2,800 Python files vs. ~6,000 total git-tracked files) and endpoint counts (~49 vs. ~90/116/119) depending on what's being counted — Python source vs. all tracked files, and routed endpoints vs. routers. Both ranges are defensible; pick the conservative figure when in doubt and be ready to say which you're counting. The OSNet embedding dimension (256 vs. 512) is contested between the repo docstring and CLAUDE.md — leave it unstated unless verified.*
