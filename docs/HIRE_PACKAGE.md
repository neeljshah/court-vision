# Hire Package -- Neel Shah

> **A systems engineer (B.S. Data Science, University of Iowa, expected May 2027) who builds end-to-end CV -> ML -> full-stack -> agentic
> systems, and builds the validation harnesses that prove what is real and reject what is not --
> including catching his own inflated numbers.** Solo human architect / director of an agentic
> build pipeline. B.S. Data Science, University of Iowa, expected May 2027; the work and the self-audit trail are the credential.
>
> One-line: *I built a 4-sport calibrated forecasting platform AND the leak-free harnesses that
> prove it matches efficient closing lines, measure a real in-game-conditioning calibration gain,
> and REJECT every false edge -- catching my own overclaims before any recruiter could.*

Honesty truth-source (every number here reconciles to it; the retracted-figure list lives there,
never here): [docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md). Open gaps:
[docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

---

## 1. What I built (lead with the engineering)

A single solo-built git history spanning computer vision, ML, a serving platform, and an
agentic build/validation loop -- ~3 intensive months, 8,200+ tracked files, architected and
directed by one person.

### Computer vision in production
Broadcast NBA video -> court coordinates -> behavioral features, on a single consumer RTX 4060
at ~$0.10/game (vs six-/seven-figure optical-tracking licensing). Implemented from primitives,
not black-box wrappers:
- **YOLOv8n** custom ball detector, exported PyTorch -> ONNX -> TensorRT.
- **SIFT + RANSAC homography** for broadcast-frame-to-court rectification, hardened with an
  inlier gate, EMA smoothing, and drift re-anchoring for moving cameras / replays / scene cuts.
- **Kalman filter + Hungarian assignment** multi-object tracker (6D constant-velocity motion
  model, blended IoU + appearance cost) written from scratch.
- **OSNet omni-scale re-ID** reimplemented in PyTorch with a layered inference backend
  (TensorRT -> torchreid -> standalone -> MobileNetV2 -> HSV-histogram fallback chain).
- Resolved anonymous tracker slots to real NBA player identities across 240+ games.

*(Honest scope: per-player CV attribution is ~4% in production and CV-feature SHAP ~0 today --
documented, not hidden. CV is the engineering lineage, not a claimed predictive moat.)*

### ML modeling + a converged 4-sport predictor
- Leak-free walk-forward prop models (PTS MAE ~4.83, REB ~1.92, AST ~1.39, FG3M ~0.89,
  re-measured 2026-07-20 on the grown corpus; earlier smaller-corpus figures were
  4.58/1.90/1.34/0.88), competitive with published benchmarks.
- A possession-level **Monte Carlo simulator** where teammate scoring competes for a shared pie
  -- the correct negative teammate correlation EMERGES from the mechanics instead of a
  hand-tuned matrix.
- Converged this into a **4-sport (NBA / MLB / Soccer / Tennis) calibrated forecaster**: one
  win-probability anchor per sport drives a coherent pregame surface plus an in-game repricer,
  behind a sport-blind kernel + per-sport adapters (adding a sport is an adapter, not a rewrite).

### Full-stack + data platform
- **FastAPI** serving layer (~99 endpoints across 11 active routers; REST + WebSocket + SSE).
- A fleet of long-running daemons with a watchdog/registry supervisor; production alerting with
  rate limiting, dead-letter queue, and per-channel circuit breakers.
- Dual-backend persistence (PostgreSQL-first, transparent SQLite fallback) with idempotent
  migrations; real CI/CD (GitHub Actions) and multi-target Docker packaging.

### Agentic orchestration (current-era signal)
- Authored a **multi-agent build/validation loop**: a planner model orchestrates cheaper
  executor models under hard ship gates, parallel branch-isolated, crash-safe, unattended --
  without corrupting the repo.
- An LLM-free signal proposer enumerates thousands of candidate transforms; an adversarial ship
  gate (walk-forward + permutation null + ablation-vs-full-model + Benjamini-Hochberg FDR)
  decides. Most candidates are correctly REJECTED, by design.

---

## 2. The differentiator: validation rigor that proves what is real and rejects what is not

This is the part a hiring manager actually wants. I do not just build models -- I build the
instruments that try to refute them, and I report the negative result as the deliverable.

### A. The 4-sport market-efficiency proof (leak-free, real data)
I ran a real-data edge hunt across **4 sports and 6 independent price corpora**. The honest,
just-proven result: my own calibrated model **MATCHES the SHIN-devigged closing line within
noise** on team-strength markets -- the realistic best case for an efficient market.

| Sport | Market | Metric | N | Our model | Close | Verdict |
|---|---|---|---|---|---|---|
| NBA | moneyline | Brier | 372 | 0.1735 | 0.1672 | MATCH |
| MLB | moneyline | Brier | 13,992 | 0.2429 | 0.2390 | MATCH |
| Soccer | O/U-2.5 | Brier | 7,558 | 0.2465 | 0.2390 | MATCH |
| NBA | total O/U | RMSE | 372 | 19.17 | 18.11 | BEHIND (freshness) |
| MLB | total O/U | RMSE | 1,679 | 4.72 | 4.44 | BEHIND (freshness) |
| Tennis (ATP) | match-win | Brier | 7,374 | 0.2177 | 0.2028 | BEHIND (freshness) |

Totals / ATP trail ONLY by the freshness data the market prices (injuries, lineups, weather,
park, starting pitcher) that a box model structurally cannot see -- a data/speed gap, not a
model defect. Nothing beats the close pregame, and that is the correct outcome. Writeup:
[docs/MARKET_EFFICIENCY_PROOF.md](MARKET_EFFICIENCY_PROOF.md).

### B. Every candidate edge REJECTED -- and I caught my own overfits
Every schedule / fatigue / form / h2h / totals / CLV candidate scored through the REAL leak-free
gate across >=2 independent corpora REJECTED. The load-bearing self-audit: signals that looked
positive on the full sample **SIGN-FLIPPED** across the held-out calendar half -- the overfit
signature the gate is built to catch.

| Candidate (sample) | Corpora | Verdict | Overfit signature |
|---|---|---|---|
| NBA b2b / rest / 3-in-4 / travel diff | 2026 H1/H2 | REJECT | sign flips H1<->H2 |
| NBA altitude / home-court probe | 2026 H1/H2 | REJECT | HCA fully in the devig |
| MLB rest / streak / h2h x3 | NL + AL | REJECT | reject on BOTH leagues |
| MLB totals slice | NL + AL | REJECT | the close beats us |
| open->close CLV capture | MLB NL + AL | REJECT | NL/AL sign disagree |

CLV exists as a market phenomenon (the close is sharper than the open; MLB DM on log-loss
p=0.0010, N=27,975) but a leak-free open-time model has ~0 correlation with the open->close move
(corr +0.0038, CI [-0.046, +0.055]) -- it is the market's own sharpening, not ours to harvest.
Reproduce: `python -m scripts.platformkit.edge_hunt_scoreboard` (`--live` re-runs the real
harness verbatim).

### C. The one measured WIN: in-game conditioning (calibration, scoped honestly)
The genuine, measured, calibrated advantage is **IN-GAME conditioning** -- fusing the pregame
intelligence prior with the realized mid-game state sharpens the win-prob forecaster:

- NBA win-prob Brier **0.209 -> 0.159** (real private corpus, leak-free OOS).
- MLB win-prob Brier **0.241 -> 0.126**.

This is FORECASTER QUALITY / calibration, **not a dollar edge** -- a live book also sees the
score, so no DM-vs-close test applies and `edge_claimed = False`. Scoped honestly: the
real-corpus OOS result is the win; on the committed synthetic fixture the NBA row prints
no-improvement (a SYNTHETIC ANCHOR ARTIFACT, not a refutation), so MLB/Soccer/Tennis reproduce
in <60s on a fresh clone while NBA is VALIDATION_PENDING without the private corpus.

### D. I caught and retracted my own inflated numbers (the strongest signal)
The same harnesses that grade the market were pointed inward and fired on me:
- A headline pregame "ROI" was a **market-follow artifact** (the grader bet the book's own
  devigged favorite, the model was never read, at a flat -110 fiction with in-sample-tuned
  filters). I root-caused it to specific lines of code and retired the claim.
- An in-play win-prob "win" was inflated by a **fourth-quarter look-ahead leak**; an in-play ROI
  was an **L5-proxy ceiling**, not realized edge.
- A grid-search showed 0.79 CV R^2 vs 0.06 leak-free holdout -- I hard-coded the corrective
  regularization so it cannot silently reappear.

Every one of those retracted figures lives, in full retraction context, in
[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md) -- and nowhere as a current result.
Building the instrument that disproves your own hype is the senior-engineering signal here.

---

## 3. Reproduce it in under 60 seconds (fresh clone, offline)

```
pip install -r requirements-predictor.txt      # or: pip install -e .  -> cv-matchup CLI

# the market-efficiency / self-audit REJECT scoreboard
python -m scripts.platformkit.edge_hunt_scoreboard

# pregame quality vs the devigged close (committed fixture)
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof

# in-game conditioning, conditional vs static (committed fixture)
python -m scripts.platformkit.ingame_scoreboard --corpus tests/fixtures/proof

# one calibrated matchup, pregame + in-game, with edge_claimed:false baked in
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0
```

The fixture paths run the SAME code on a small committed sample so the methodology verifies
end-to-end with no private data; the canonical full-corpus numbers live in `vault/_Edge_Maps/`
and reproduce on the private corpora. Proof-module index: [docs/PROOFS.md](PROOFS.md).

---

## 4. What I am and where I fit

- **Strongest fit:** ML-infra / applied-ML / CV / data-platform / founding-or-early generalist
  roles where validation rigor and ownership matter. I own the full stack from frame decode to
  served endpoint, and I treat every result as guilty until proven leak-free OOS.
- **Engineering, not betting.** The sports-betting domain was the forcing function -- a live,
  adversarial, ground-truth-rich grader that punishes self-deception immediately. The
  transferable product is the CV pipeline, the calibrated multi-sport forecaster, the systems
  breadth, and the validation methodology. I make **no dollar-edge / ROI / +EV / picks claim**;
  "the market is efficient; I match the close; the self-audit is the result" is the honest pitch.
- **Honest gaps (volunteered):** real-corpus OOS-vs-close on a fresh clone is human-gated
  (VALIDATION_PENDING); cross-team-process maturity is the thing solo work cannot demonstrate,
  and is exactly why I want a team.

Contact: [neeljshah22@gmail.com](mailto:neeljshah22@gmail.com)

---

*All prediction numbers here are calibration / sharpness (Brier, RMSE, BSS), never a dollar
edge; `edge_claimed = False`. The single honesty truth-source is
[docs/JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md); the retracted measurement artifacts
listed there appear on this page only in explicit retraction context (section 2D).*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
