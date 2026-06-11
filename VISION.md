# CourtVision — Where This Is Going

> A longer-form narrative on the product, the platform, and the honest intellectual
> trajectory. Technical architecture: [ARCHITECTURE.md](ARCHITECTURE.md).
> Start with the honest numbers: [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md).

---

## What this is — and what it isn't

CourtVision is an AI-native sports intelligence system. The current form is an NBA
prediction engine: broadcast video → court-coordinate CV tracking → 80-artifact
intelligence layer → calibrated player-game projections → a self-improving research loop
that discovers, validates, ships, and retires signals.

The honest accounting is in the repo itself, because the most important thing about this
project is what it *refused* to claim.

Against real sportsbook closing lines, the prop models are roughly break-even-minus-vig.
The market is efficient; the system confirms that, rather than hiding it behind inflated
numbers. What survived adversarial self-audit: leak-free prop MAE of PTS ~4.58 / REB ~1.90
/ AST ~1.34 / FG3M ~0.88, win-probability accuracy 70.9% / Brier 0.193, one durable
~+4–5% signal on assists (regime-dependent, breaks in playoffs), and a broadcast-video
CV pipeline that runs at ~$0.10–0.13 per game on a consumer GPU.

What this is **not**: a profitable betting operation, a P&L track record, or a system
with a demonstrated edge on closing lines. The first real forward Pinnacle closing-line
CLV measurement happens in October 2026. Zero real money has been placed, by design.

The value proposition to a serious evaluator is not the headline metrics — it's the
methodology: a system sophisticated enough to catch its own measurement artifacts, document
them openly, and retract them.

---

## The engineering thesis — why broadcast CV changes the economics

Sports analytics has a cost structure problem. The data that *actually* explains basketball
outcomes — defender location at the moment of a shot, spacing as a convex hull at release,
fatigue accumulated through movement — comes from player-tracking systems that cost
six to seven figures per season to license (Sportradar, Second Spectrum). Those systems run
on dedicated in-arena cameras with proprietary computer vision, sold to teams and
broadcasters at prices that structurally exclude researchers and small operators.

The broadcast feed changes that equation. Every NBA game is filmed with broadcast cameras,
distributed freely (via streaming) or cheaply (via cable), and contains all the spatial
information those licensed systems derive — it's just not yet extracted. A CV pipeline that
converts the broadcast feed to court coordinates produces the same *class* of spatial data
at ~$0.10–0.13 per game on a consumer GPU. That's a cost-per-game reduction of four to
five orders of magnitude.

The thesis: if broadcast-derived CV features carry predictive information that book pricing
doesn't currently account for, that gap is a structural advantage. The current honest answer
is that CV features show SHAP importance ≈ 0 in production prop models — the plumbing is
complete but the signal isn't demonstrated yet. That's a roadmap item, not a hidden failure.
It's stated plainly because it's the discipline.

Whether or not broadcast CV produces a betting edge, the engineering value is independent:
a team, broadcast partner, or data vendor that wants behavioral spatial data from any game
in the archive — not just games with dedicated tracking — can extract it from the broadcast.
The pipeline runs on anything.

---

## The intelligence layer — the part that understands the game

Most prediction systems stop at a number. CourtVision also produces an *explanation*:
1,249 player dossiers (up to 28 statistical categories, archetype-labeled, scheme-tagged),
30 team scheme cards, a 690-node knowledge graph, and a grounded AI chat surface that
answers basketball questions against pre-extracted facts rather than hallucinating.

The intelligence layer isn't decorative. It's the substrate for the self-improving research
loop: the loop's ARM B writes new atlas sections back into the player profiles, so the
system's understanding of each player deepens automatically as more games are processed.
It's also what makes predictions *interrogable* — when the engine projects a number, the
player's dossier explains why: form, matchup, scheme context, historical role under similar
defensive coverage.

The 291,625-pair player-vs-player matchup matrix (built from 2,214 raw tracking files
across three seasons) and the archetype×scheme interaction tables represent a different kind
of value than MAE metrics. They encode how *this* type of player performs against *that*
type of defense — the kind of structured basketball knowledge that is useful to front offices
and broadcast analysts independent of any betting application.

---

## The self-improving loop — the research machine

The piece that makes CourtVision more than a static ML stack is the two-arm autonomous
discovery loop (`src/loop/`).

ARM A mines residuals from existing models into candidate signals, instantiates a leaf
`signals/<name>.py`, and passes it through a hard statistical gate: expanding walk-forward
(all folds must improve), null-shuffle permutation control (z ≥ 3), ablation-vs-full
marginal lift, and Benjamini-Hochberg FDR across the hypothesis family. Most candidates
are correctly rejected. The gate is built to *refute*, not confirm.

ARM B writes new atlas sections into the player intelligence layer — not hallucinated
summaries, but derived statistical findings with explicit REAL-vs-unknown marking, point-in-
time-correct computation, and confound flagging.

The loop is what caught and retracted the system's own inflated headline numbers. It's also
what found the one durable edge (assists) and documented exactly why it survives and where
it breaks. An agent loop that only ever ships is just automated overfit. The value is in
the honest REJECTs.

The loop architecture is domain-agnostic by design. The gate, the ledger, the hypothesis
contract, the atlas section protocol — none of them know what sport they're running on.
That's intentional.

---

## The platform direction — kernel + adapter architecture

The long-term vision is a **domain-agnostic, multi-sport forecasting and decision engine**.

A June 2026 audit of the 430-module codebase showed that approximately **38% of the code
is already sport-agnostic**: the honest validation gate, the walk-forward CV harness,
calibration machinery, Kelly/CLV/devig math, the Monte Carlo simulation framework (minus
basketball rules), the self-improving loop orchestration, the brain/flags registry, the
fusion/reconciliation layer, and the serving scaffolds. That code runs on any sport. The
remaining ~53% is NBA-specific (possession rules, prop models, PBP parsers, the basketball
CV pipeline, ratings, team-system builders, NBA API connectors) and moves cleanly to
`domains/nba/`.

The target architecture:

```
kernel/                     ← sport-agnostic engine (~38% of current code)
  loop/                     honest gate, discovery daemon, ledger
  calibration/              isotonic calibration, conformal prediction
  validation/               CLV tracker, walk-forward harness
  sim/                      Monte Carlo framework (pluggable outcome model)
  brain/                    flag registry, control brain, discovery gate
  prediction/               Kelly, devig, decision engine, shadow logger

domains/
  nba/                      ← the current system, reorganized as an adapter
    sim/                    possession model, basketball rules, PBP parsers
    cv/                     broadcast CV pipeline (basketball court geometry)
    prediction/             prop models, win-prob stack, in-play heads
    intel/                  NBA intelligence builders, rating systems
    api/                    trading desk templates, NBA-specific endpoints
  tennis/                   ← planned second-domain proof-of-concept
    ...
```

**The contract:** adding a new sport = writing a `domains/<sport>/` adapter that implements
seven config/protocol objects. The kernel never changes. The honest-edge discipline — that
accuracy ≠ edge, CLV > ROI, and nothing ships un-gated — is baked into the kernel as
invariants. No domain adapter can weaken the gate.

The kernel's value is that it embeds the methodology itself: a new sport inherits a
calibrated, leak-free, self-improving research infrastructure from day one, rather than
being built on the same ad-hoc foundations that most sports-prediction projects start with
and never fix.

The NBA system is the reference implementation and the proof that the methodology works
end-to-end. Every future domain adapter builds on that proof.

More detail: [docs/PLATFORM.md](docs/PLATFORM.md)

---

## What needs to be true for this to matter

The honest answer is that the platform is at an early proving stage. Several things need
to land before the vision is validated:

**1. A demonstrated forward-captured edge.** The first real Pinnacle closing-line CLV
reading happens in October 2026, when preseason lines are available for fresh data. Until
then, the strongest evidence is the methodology — the harnesses, the gate, the documented
self-corrections — not a P&L number. That's the honest position and worth defending.

**2. CV features that actually move the model.** Today, CV-derived features show SHAP ≈ 0
in production. The plumbing is complete; the signal isn't there yet. The roadmap path is
more clean-games tracking to build the corpus, then a rigorous feature-selection campaign
with the same gate that rejects everything else.

**3. A second-domain proof.** The tennis adapter is the first test of the kernel/adapter
architecture. If adding tennis requires minimal kernel changes — just the adapter — the
architecture claim is validated. If it requires kernel surgery, the audit was wrong.

**4. Team or broadcast commercial validation.** The spatial features CourtVision extracts
(defender pressure, spacing, play type, shot quality by context) are what NBA front offices
buy from Second Spectrum for six-figure annual contracts. The first external customer that
pays for broadcast-derived spatial data validates the cost-structure thesis independently
of any betting application.

None of these are guaranteed. They are the next testable milestones.

---

## The honest framing for evaluators

The strongest thing this project demonstrates is not any individual metric. It's a way of
working:

- Build ambitious systems with real engineering depth.
- Build the instruments to disprove your own claims.
- Document the negative results in writing.
- Ship only what the gate approves.

That methodology is rare and it's more durable than any single model's MAE. The prop MAE
numbers are competitive with published benchmarks — that's the baseline. The self-caught
leaks, the retracted headlines, the honest limitations file — those are the differentiator.

A system that publishes a fake +18.38% ROI is easy to build. A system that catches the
artifact, root-causes it to specific lines of code, documents it publicly, and retires the
inflated claim is harder. That's what CourtVision is.

---

*For technical architecture: [ARCHITECTURE.md](ARCHITECTURE.md)*
*For the honest numbers and do-not-claim list: [docs/JOB_EVIDENCE_PACKET.md](docs/JOB_EVIDENCE_PACKET.md)*
*For the platform roadmap: [docs/PLATFORM.md](docs/PLATFORM.md)*
*For open gaps and limitations: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md)*
