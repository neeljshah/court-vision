# Evals, Quality Loops, and Forecasting Rigor

_Researched 2026-06-16. Scope: LLM-as-judge, eval frameworks (Inspect/promptfoo/Braintrust/Bloom), proper scoring rules, leak-free backtesting, and how to wire an eval-driven improvement loop for a calibrated sports predictor._

---

## TL;DR (highest-leverage takeaways)

- **LLM-as-judge is now standard** for automated evaluation of free-form outputs; ~85-90% agreement with human reviewers when rubrics are tight. Use it to score narrative outputs (scouting summaries, LLM scheme priors) not numeric predictions -- numeric predictions get proper scoring rules.
- **Brier score + log-loss + CRPS are the right scorers for probabilistic forecasts.** They are strictly proper: a forecaster maximizes expected score only by reporting true beliefs. Walk-forward (expanding-window) with vintage alignment is the only leak-free backtest for time-series sports data.
- **Anthropic's power-analysis paper is directly applicable:** report SEM + 95% CI on every eval, use paired-difference analysis across model versions (frontier models share right/wrong patterns, correlation 0.3-0.7), require a pre-specified effect size before calling a model "better."
- **Inspect AI (UK AISI, open source)** gives you a principled Task/Solver/Scorer scaffold with model-graded scoring, Docker sandboxing, and 200+ pre-built evals. It is the most rigorous open framework for reproducible evals.
- **promptfoo** is the fastest path to CI regression gating: YAML-defined eval cases, runs in GitHub Actions, fails the build if scores drop. Zero infrastructure cost.
- **Braintrust** adds dataset versioning + PR-level experiment diffs (which exact cases regressed) if you want observability across many model versions; heavier setup than promptfoo.
- **Anthropic Bloom** shows the pattern for auto-generating eval cases from a behavioral description -- directly applicable to auto-generating new backtesting scenarios (game states, edge cases) without manual curation.
- **Calibration is the bar, not accuracy alone.** A Brier skill score vs. devigged market odds is the correct north-star metric: positive score = better than the market reference, negative = worse. Report it every eval run.

---

## Key capabilities / techniques

### Proper scoring rules (the foundation for forecasting evals)

| Metric | Formula | Use case |
|---|---|---|
| Brier score | mean((p - y)^2) | Binary win-prob, prop O/U; lower = better; perfect = 0 |
| Log-loss | -mean(y*log(p) + (1-y)*log(1-p)) | Same binary case; heavier penalty for confident errors |
| CRPS | Integral of (F(x) - 1(x>=y))^2 dx | Continuous distributions (point totals with uncertainty) |
| Brier Skill Score | 1 - (Brier_model / Brier_reference) | Calibration vs. a reference (e.g., devigged close) |

All three are **strictly proper**: only honest probabilities maximize expected score. Use multiple simultaneously; never optimize a single metric in isolation.

**Calibration check:** bucket predictions into 10 probability bins; plot predicted vs. observed frequency. A well-calibrated model's reliability diagram hugs the diagonal. Report Expected Calibration Error (ECE) = weighted mean bin deviation.

### Walk-forward backtesting (leak-free)

- **Expanding window:** train on games 1..t, predict t+1, then add t+1 to training, predict t+2, etc. Never look ahead.
- **Vintage alignment:** any feature derived from external data (injury reports, line moves) must use the value available at prediction time, not post-game values.
- **Minimum 2 independent corpora:** different seasons, different sports, or held-out franchises. Single-corpus lift is an artifact.
- **Temporal gap:** add a buffer (1-3 days) between train end and val start to avoid near-future leakage via shared covariate shifts.

### LLM-as-judge methodology

**When to use it:** evaluating the quality of free-form text outputs -- scouting summaries, scheme prior narratives, LLM-generated intel nodes. Not for numeric predictions (use proper scoring rules there).

**Rubric design matters most:**
- Rate-then-explain or explain-then-rate both beat raw scoring; explain-rate slightly higher agreement.
- Apply Item Response Theory (IRT) to judge responses: treat each rubric criterion as a "test item" and flag criteria with near-zero discrimination (judges always agree) or near-1 difficulty (judges always disagree) -- prune or refine those.
- Calibrate the judge against a 50-100 human-labeled "golden set" before deploying at scale. Target >80% agreement on the golden set.

**Bias guards:**
- Position bias: randomize option order when comparing two outputs.
- Self-preference bias: do not use the same model to judge its own outputs.
- Verbosity bias: longer outputs score higher spuriously; add a length-normalized criterion.
- Use multi-judge ensembles (2-3 models) and report inter-judge agreement (Cohen's kappa > 0.6 is acceptable).

**Meta-judge pattern (2025):** a second LLM evaluates the judge's own reasoning before it emits a score. Reduces single-judge failure modes for ambiguous cases.

### Anthropic statistical eval methodology

Source: "A statistical approach to model evaluations" (anthropic.com/research).

- **Always report SEM:** eval score +/- (1.96 * SEM). A 2-point improvement with a 3-point CI is noise.
- **Clustered SEs:** when questions cluster (e.g., multiple game-state variants from one game), naive SE underestimates uncertainty by 3x or more. Use cluster-robust SE.
- **Variance reduction inside a question:**
  - Chain-of-thought model: resample N times per question, average, then compute overall stats.
  - Deterministic model: use next-token log-probs as continuous scores instead of binary pass/fail.
- **Paired-difference analysis:** compare model v1 vs. v2 on the same eval set, analyze differences directly. Frontier models share right/wrong patterns (corr 0.3-0.7), so paired analysis has 40-60% lower variance than independent comparison.
- **Pre-specify effect size:** before running an eval, decide the minimum meaningful improvement (e.g., Brier drops by 0.005). Calculate required N to achieve 80% power. Avoid HARKing (Hypothesizing After Results are Known).

### Inspect AI (UK AISI open source framework)

Repo: github.com/UKGovernmentBEIS/inspect_ai | Docs: inspect.aisi.org.uk

Core primitives:
- `Dataset`: loads labeled samples (input + target). Supports HuggingFace, CSV, JSON, in-memory.
- `Solver`: generates answers -- from simple `generate()` to multi-turn ReAct agents with tools.
- `Scorer`: evaluates outputs -- `model_graded_qa()` for free-form, `includes()` for exact match, custom callables for numeric metrics.
- `Task`: composes Dataset + Solver + Scorer into a reproducible eval unit.

Key features:
- `model_graded_qa()`: LLM-graded scoring with bootstrap CIs built in.
- Sandboxed execution: `sandbox="docker"` runs tool calls in isolated containers, preventing side effects.
- 200+ pre-built evals (GAIA, SWEBench, GDM CTF, cybersecurity, math, reasoning).
- VS Code log viewer + web-based Inspect View for result inspection.
- Install: `pip install inspect-ai[dev]`.

Inspect does NOT have sports-specific or forecasting-specific primitives out of the box -- you write custom Scorers.

### promptfoo (CI regression gating)

Repo: github.com/promptfoo/promptfoo | CLI-first, open source, zero infrastructure.

Workflow:
1. Define eval cases in YAML (prompts + expected outputs or rubric criteria).
2. Run `promptfoo eval` locally or in CI.
3. Scores drop below threshold -> build fails.
4. Integrates with GitHub Actions, GitLab CI, Jenkins, CircleCI.

Best for: catching prompt or model regressions on every commit. Fast (seconds per run). No managed infra needed.

Limitation: no built-in dataset versioning or cross-run experiment diffs.

### Braintrust (full lifecycle platform)

Site: braintrust.dev | Managed SaaS, GitHub Action: `braintrustdata/eval-action`.

Key features:
- Dataset management: version-controlled eval datasets with lineage.
- Experiment diffs on every PR: which exact cases improved/regressed, with score breakdowns.
- AutoEvals library: built-in scorers (factuality, relevance, security, custom).
- Automatic rate limiting + concurrency controls (`maxConcurrency`).
- Connects eval -> scoring -> production monitoring -> release gating in one system.

Best for: teams running many model variants or prompt iterations and needing traceable experiment history.

Limitation: SaaS cost; heavier setup than promptfoo; requires sending data to Braintrust servers.

### Anthropic Bloom (auto-generated evals)

Site: anthropic.com/research/bloom | Open source.

Four-stage agentic pipeline:
1. Understand: parse behavioral description into measurable criteria.
2. Ideate: generate diverse eval scenarios (covering edge cases, adversarial inputs).
3. Rollout: execute scenarios in parallel with simulated user/tool interactions.
4. Judge: score transcripts + produce suite-level analysis.

Validates against "model organisms" (intentionally misaligned models): 9/10 correctly distinguished. Claude Opus 4.1 had highest human-judge correlation (Spearman 0.86).

Application pattern: describe a behavior you want to measure ("predict win probability without using post-game statistics"), feed it to Bloom-style pipeline -> auto-generate hundreds of diverse test cases.

---

## How THIS project should use it

### 1. Lock in a Brier Skill Score eval as the primary CI gate

Every model change (feature, architecture, calibration tweak) must run the walk-forward backtest and report:
- Brier score vs. devigged market close (reference)
- Brier Skill Score = 1 - (Brier_model / Brier_market)
- ECE (Expected Calibration Error) from reliability diagram
- Log-loss alongside Brier (catches overconfidence that Brier misses)

If BSS drops below 0 on either corpus -> reject the change. Positive BSS = measurably better than the market reference on calibration.

Wire this into promptfoo or a simple Python script that fails with exit code 1 if BSS < threshold. Run on every commit that touches model/feature code.

### 2. Apply Anthropic's SEM discipline to every eval result

Stop reporting bare Brier scores. Always report: Brier = 0.208 +/- 0.003 (95% CI, N=847 games). Use paired-difference analysis when comparing model v_n+1 vs. v_n: analyze the per-game Brier deltas directly rather than comparing aggregate scores. Pre-specify the minimum meaningful BSS improvement (suggest 0.005 absolute) before running the experiment.

### 3. Use Inspect AI for structured component evals (LLM scheme prior, intel summaries)

The LLM scheme-prior layer and intel-synthesis outputs are free-form text -- proper scoring rules do not apply. Wire Inspect's `model_graded_qa()` to score these against a golden set of 50-100 human-curated scheme annotations. Track the judge score across model updates. Fail the build if judge score drops below baseline.

Use Docker sandboxing (`sandbox="docker"`) when evals involve tool calls (e.g., the intel proposer calling data-fetch tools) to prevent side effects on production data.

### 4. Build a lean golden dataset (100 labeled game states)

Curate 100 game states with:
- Known true win probability (computed from PBP replay with outcome known)
- Known post-game stats (for prop evals)
- Human-annotated scheme description (for LLM scheme-prior evals)

Version-control this dataset (git-tracked CSV, NOT data/ which is gitignored -- put in tests/fixtures/). Run the full eval stack against it on every relevant change. This is cheap to build (one afternoon) and provides a stable regression anchor.

### 5. Auto-generate eval cases for edge states (Bloom pattern)

Use a Bloom-style prompt to auto-generate diverse game-state scenarios:
- "Generate 20 game states where in-game conditioning should matter most (blowouts, foul trouble, garbage time, 4th quarter within 5 points)"
- Score each scenario through the in-game projector and flag cases where the projector output is implausible
- Add confirmed-plausible cases to the golden dataset

This expands coverage without manual curation.

### 6. Walk-forward harness: two-corpus rule

Currently the system has a walk-forward harness for NBA. Extend the rule: any model change must show positive BSS on BOTH the NBA corpus AND at least one other sport (MLB, soccer, tennis). A lift on one corpus with a drop on another is a red flag for overfitting. Report this in the eval output.

Vintage alignment check: assert that every feature used in the walk-forward was available at prediction time. Add a `feature_availability_date` column to the signal registry and assert `availability_date < game_date` for all features in the eval window.

### 7. promptfoo for nightly regression

Add a `promptfoo.yaml` to the repo root defining the core eval suite (model outputs on golden dataset). Run it in a nightly cron (Claude Code CronCreate or GitHub Actions). If any scorer drops by more than 1 sigma from the 30-day rolling mean, send a notification (PushNotification). This catches silent regressions from data drift, not just code changes.

### 8. LLM-as-judge for intel quality (not for predictions)

For the 660-player / 30-team intel nodes: define a rubric (accuracy, completeness, absence of hallucination, recency). Run `model_graded_qa()` against a golden set of 50 human-verified intel snippets quarterly. Track judge score over time. This ensures the intel layer does not silently degrade as the vault grows.

---

## Gotchas / limits

- **LLM-as-judge is not a substitute for proper scoring rules on numeric predictions.** Judge agreement with humans is ~85-90% on open-ended text; on numeric calibration tasks the judge has no ground truth. Never use LLM judge to evaluate Brier scores.
- **Single-corpus lifts are artifacts.** The system's own history confirms this. The two-corpus rule is non-negotiable; do not relax it even for quick experiments.
- **Clustered SE matters more than it looks.** If your eval set groups multiple game states from the same game/season, naive SEs are 3x too narrow, making improvements look more significant than they are. Always cluster by game_id or season.
- **Walk-forward is necessary but not sufficient.** Even a leak-free walk-forward can be optimistic if the feature set was selected on the full historical dataset before the backtest ran. Feature selection and hyperparameter tuning must also be done inside the expanding window.
- **Bloom/auto-generated evals can introduce distribution shift.** Synthetically generated game states may not match the real game-state distribution. Always validate a sample (10%) of auto-generated cases manually before adding to the golden dataset.
- **Braintrust SaaS sends your eval data to external servers.** This project's binding invariant is no secrets / no data external push. Use Braintrust only for non-sensitive eval outputs, or self-host. promptfoo is fully local.
- **Inspect CI integration is not documented out of the box** -- you must write the GitHub Actions YAML yourself to run `inspect eval` and parse exit codes. The framework is rigorous but not plug-and-play for CI.
- **Brier Skill Score vs. devigged close is the bar, not vs. a coin flip.** BSS > 0 vs. a 50/50 reference is trivially achievable and meaningless. Always use the devigged market probability as the reference forecaster.
- **ECE can be gamed by predicting all 0.5.** Use sharpness (variance of predictions) alongside ECE. A model with ECE=0.01 and sharpness=0.001 is useless; a model with ECE=0.02 and sharpness=0.05 is genuinely informative.

---

## Sources

- [A statistical approach to model evaluations -- Anthropic](https://www.anthropic.com/research/statistical-approach-to-model-evals)
- [Bloom: open source tool for automated behavioral evaluations -- Anthropic](https://www.anthropic.com/research/bloom)
- [Inspect AI GitHub repo -- UK AISI](https://github.com/UKGovernmentBEIS/inspect_ai)
- [Inspect AI documentation](https://inspect.aisi.org.uk/)
- [Inspect Evals -- UK AISI blog](https://www.aisi.gov.uk/blog/inspect-evals)
- [Best AI Eval Tools for CI/CD Pipelines 2026 -- Braintrust](https://www.braintrust.dev/articles/best-ai-evals-tools-cicd-2025)
- [Proper Scoring Rules for Estimation and Forecast Evaluation -- arXiv 2504.01781](https://arxiv.org/pdf/2504.01781)
- [Proper scoring rules for multivariate probabilistic forecasts -- ASCMO 2025](https://ascmo.copernicus.org/articles/11/23/2025/ascmo-11-23-2025.pdf)
- [LLMs-as-Judges: A Comprehensive Survey -- arXiv 2412.05579](https://arxiv.org/pdf/2412.05579)
- [LLM-as-a-Judge: Tutorial and Best Practices -- Patronus AI](https://www.patronus.ai/llm-testing/llm-as-a-judge)
- [LLM-as-a-Judge -- Langfuse docs](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge)
- [Rubric-Based Evals and LLM-as-a-Judge -- Medium / Adnan Masood, Apr 2026](https://medium.com/@adnanmasood/rubric-based-evals-llm-as-a-judge-methodologies-and-empirical-validation-in-domain-context-71936b989e80)
