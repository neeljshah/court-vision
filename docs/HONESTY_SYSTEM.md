# The Honesty System -- how this system is prevented from lying to itself

> **Funnel position:** cuts across every stage. The discipline described here is what makes the
> DATA -> SIGNALS -> MODELS -> ENGINES -> PREDICTIONS -> EXECUTION -> SELF-IMPROVE funnel
> (see [INDEX.md](INDEX.md)) trustworthy end to end. Honesty rail: this doc claims no edge -- it
> documents the machinery that stops an edge claim from surviving unproven. Truth-source for any
> number: [JOB_EVIDENCE_PACKET.md](JOB_EVIDENCE_PACKET.md).

## Why this exists

A solo-built, agent-driven prediction system has one structural risk that matters more than any
bug: a number that looks like a win but is actually a measurement artifact, shipped because
nobody adversarially checked it before it hit a README. This system was built the hard way once
already -- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) documents five headline numbers that were
published, then refuted by the system's own validation harnesses, then retracted:

| Retracted | Root cause (one line) |
|---|---|
| +18.38% ROI vs real closes | Market-follow grading artifact -- the grader bet the market's own devigged direction, never read the model |
| endQ3 Brier 0.1191 "Pinnacle-class" | Two features computed from Q4 data leaked the quarter being predicted |
| +54%/78% in-play ROI | Retracted: settled against an L5 rolling-average proxy line, not a real sharp close |
| Full-season spread/total edge | Truncation-invariant walk-forward backtest showed CLV approx 0 |
| In-series playoff win-prob edge | PBP Finals replay showed pooled Brier 0.34-0.40 -- worse than a coin flip |

The full table, proof artifacts, and root-cause detail live in
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md#retracted-numbers--the-discipline-headline); this doc
does not repeat the numbers outside that retraction context (see the lint layer below for why that
distinction is enforced mechanically, not just by convention).

The lesson that came out of that: retraction cannot be a one-time cleanup pass. It has to be a
standing property of the system -- every new claim gets adversarially checked *before* it can be
repeated, not after a reader catches it. What follows is the stack of layers that does that
checking, cheapest and most mechanical first, most expensive and most judgment-heavy last.

---

## The layers, in the order a claim passes through them

```
  LINT  ->  GATES  ->  INDEPENDENT VALIDATORS  ->  PREREGISTRATION  ->  RETRACTION LIST
    |                                                                          ^
    +---------------------------- OPS DETECTORS -----------------------------+
                                        |
                                   GIT GUARDS (wrap the whole loop)
```

A claim that survives every layer is VERIFIED and can appear in a public doc. A claim that dies
at any layer is a REJECT, DEFER, or STUCK -- and the graveyard remembers it so nobody re-derives
the same false positive next week.

### 1. Lint -- catch a banned word or number before it is even a claim

Two lints run at two different times, because a bad string can enter the system two different
ways: written by hand into a doc, or fabricated at runtime into an API response.

**Static repo lint** (`scripts/platformkit/hygiene_lint.py`) scans every `git ls-files`-tracked
file for two violation classes: a short list of retracted numeric artifacts (the same five figures
tabled above) appearing *outside* an explicit retraction-context line (the line must contain a
keyword like `retracted`, `artifact`, `do-not-claim`, `superseded`, `quarantine`), and a short list
of edge-claim phrases -- unqualified assertions of profitability or of beating the market -- which
are always flagged, no exemption, since there is no honest context in which this codebase should
say one of those out loud. Exit code 1 on any hit -- this is what keeps this very document honest:
any of the five retracted figures above would trip the lint if it appeared without the
retraction-keyword sentence around it.

**Runtime response lint** (`predict_service/honesty_mw.py`, `HonestyLinterMiddleware`) closes a
gap the static lint cannot reach: a fabricated `$`/`roi`/`pnl` key produced at *serving* time,
after the static scan already passed. Every JSON response body gets scanned before it leaves the
API; a banned key or retracted number in a live payload replaces the response with a 500
honesty-violation sentinel (`edge_claimed: false`, the violation list, never the poisoned body)
rather than serving it. The linter is fail-closed by design -- an exception while scanning is
treated as a violation, not a pass, and an unlintable body is never served.

The subtlety worth naming: the product tracks *units*, never dollars, so a bare `stake` token
would over-match the legitimate `stake_units` / `stake_a` / `stake_b` fields. The middleware
carries a narrow, documented exemption -- a key is forgiven only when it carries the literal
`units` token or is one of the two explicit unit-stake legs (`stake_a`, `stake_b`); the real
dollar keys (`stake_dollars`, `stake_usd`) are listed as explicitly NOT exempt, so a genuine `$`
field still trips the guard even if someone tries to smuggle it in as `stake_dollars_units`. The
exemption is documented inline in the module with the exact reasoning, because a silent exemption
list is itself a way to lie to yourself.

### 2. Gates -- a claim must clear a fail-closed checklist before it can be greenlit

`scripts/platformkit/econ/greenlight_criteria.py` is the sharpest example: seven lettered
criteria (a-g), each a pure function over a channel's paper rows, each independently fail-closed
(an exception or a missing input is a failure detail, never a silent pass):

- **(a) sample size** -- n >= 300 total, and >= 150 in *each* of two independent halves. The
  split is date-parity (even/odd day-of-month), a cheap, deterministic, leak-free fold with no
  hand-chosen boundary (`halves()`).
- **(b) both-halves-positive** -- net units positive in half A *and* half B independently; a
  channel that only wins on one half is not greenlit on the pooled number.
- **(c) CLV beats the fee hurdle** -- mean CLV exceeds `breakeven_edge_prob`'s cost hurdle with a
  95% CI that excludes zero, in both halves.
- **(d) after-cost units positive** -- same both-halves requirement, after transaction costs.
- **(e) segment + channel trust** -- both a segment-trust file (m26) marks the channel TRUSTED
  *and* a real per-channel computation (`greenlight_trust_honesty.channel_trust_status`) returns
  GREEN across five independently-fail-closed sub-checks (settled-N/coverage, CLV-CI sign, a
  same-venue reconciler verdict, adverse-segment scan, and -- for in-game channels -- an in-game
  CLV verdict).
- **(f) eval-gate + honesty-gate** -- the offline golden-set eval gate must be GREEN *and* a
  five-check honesty scan (`cv_honesty_status`, see below) must return `NOT_REFUTED`.
- **(g) win-rate excess** -- a statistically significant excess over the implied win rate.

Every criterion returns `passed` plus a `detail` string explaining exactly why it failed --
nothing is greenlit by a bare boolean nobody can audit later.

`cv_honesty_status` (also in `greenlight_trust_honesty.py`) is the honesty-gate itself: five
checks, all must pass, zero `NOT_APPLICABLE` allowed for a clean `NOT_REFUTED` verdict --
retracted-number/edge-phrase scan over the report *and* every cited ops artifact, `edge_claimed`
literally `False` on the segment-trust files, a proposal-only integrity check (measurement-only
flags never silently flipped, no flag marked `wired`), a monotonic reject-ledger check (the
ledger's line count and a sha256 prefix hash can only grow, never shrink or get rewritten --
catches a ledger that was silently truncated to hide a past REJECT), and a preregistration
integrity check (the pinned prereg fields must match a snapshot taken the first time the gate
ran, sha-verified).

### 3. Independent validators -- a producer's claim is never its own proof

`scripts/platformkit/intel_validation/` runs two structurally different validator kinds, and both
share one rule: **the validator never re-derives what the producer already computed by importing
the producer's code.** It only re-reads what the producer wrote to disk and checks it independently.

- `claims_validator.py` recomputes *ranking* claims straight from the raw parquets -- an
  independent re-derivation from source data, not a re-run of the claim-generation code.
- `verdict_claims_validator.py` validates *verdict* claims (`"gate X produced verdict Y with
  number Z"`) by provenance + consistency: the cited `verdict_file` must exist, parse, and every
  field the claim asserts must be re-extracted from that file at the claim's declared JSON path
  and match exactly. It explicitly **never imports a gate module and never re-runs a gate** --
  only re-reads the artifact the gate already wrote. Any missing file, missing field, or shape
  surprise is `UNVERIFIABLE`, never silently treated as `VERIFIED`; a value that resolves but
  disagrees is `MISMATCH`.

This is the same discipline `predict_matchup`'s kernel/adapter seam uses for train==inference
parity (see [PLATFORM.md](PLATFORM.md)): a producer claiming its own output is correct is not
evidence; a second, independently-computed read of the same artifact is.

### 4. Planted-null validation -- proving the gate can actually detect nothing

A gate that never rejects anything is not rigorous, it is broken. The fit-validity gate
(`scripts/platformkit/intel_validation/fit_validity_gate_nulls.py`) runs two real, seeded,
deterministic permutation nulls before trusting any real-arm result:

- **null_1** (`shuffle_move_team_assignment`) permutes destination team *within each season fold*
  while holding each player's true realized outcome fixed -- a real permutation of an existing
  column, never a redraw from an assumed distribution.
- **null_2** (`shuffle_outcome_deltas`) permutes the outcome column itself within each fold, the
  fit-relevant columns held fixed.

`null_dies()` then asks the harder question honestly: a null only "clears the bar" if it manages
the *same* positive-delta win the real arm would need, not merely a smaller loss than the real
arm's own negative score. If the real arm never beats its baseline in the first place, a null that
also fails to beat it is not evidence of anything -- the check is written to avoid manufacturing a
false pass out of two losing numbers. The same `planted_null` field is threaded through every
autoloop standing-prereg template (`scripts/platformkit/autoloop/templates/*.json`) and the
greenlight prereg-integrity check pins it as one of four fields that can never silently drift
between a template's registration and its later use.

### 5. Preregistration -- the bar is fixed before the result is seen

`scripts/platformkit/autoloop/standing_prereg.py` is the sha-pinned template registry for the
autonomous discovery loop: each template (`universe`, `corpus`, `bars`, `k_ledger`,
`planted_null`, `max_candidates_per_cycle`, ...) carries its own `prereg_sha`, a sha256 over the
canonical JSON (sorted keys, minus the sha field itself). The daemon **only ever reads and
verifies** this pin -- it never writes one. A mismatch is fail-closed: `PREREG_TAMPER`, and the
family is refused outright. Registering a *new* template class is a human/Fable action, not
something the loop can do to itself mid-run. This closes the most tempting failure mode in any
self-improving system: quietly loosening the bar after seeing that the original bar wasn't
clearing.

The same pattern surfaces again in `greenlight_trust_honesty._check_prereg_integrity`: the first
time a gate runs, it snapshots its own pinned fields; every subsequent run must match that
snapshot exactly (and match a sha256 once one is stamped), or the check fails closed rather than
silently accepting a moved goalpost.

### 6. Leak-free gates -- walk-forward, truncation-invariance, multi-corpus

Underneath all of the above sits the base discipline every claim in this system must clear before
it is even eligible for a greenlight: walk-forward cross-validation with assertion-level leak
guards, truncation-invariance testing (a result must hold whether the corpus is cut early or run
to completion -- this is exactly what caught the retracted full-season spread/total edge above),
and a requirement for >=2 independent corpora before a single-fold lift is trusted at all. This
machinery is sport-blind (`kernel/validation/proof_metrics.py`, the conformance and parity-matrix
mechanisms) and is described in architectural depth in [PLATFORM.md](PLATFORM.md)'s kernel/adapter
section -- every new sport adapter inherits these gates for free, on day one, without rebuilding
them.

### 7. The reject ledger -- the signal graveyard

`scripts/platformkit/reject_ledger.py` is append-only institutional memory: every verdict a
leak-free gate returns for a signal gets recorded (`data/frontend/reject_ledger.jsonl`, gitignored)
so the discovery loop never re-tests a known-dead signal, and a human (or a future agent) can see
what was killed and why. The module's own `CALIBRATION_NOTE`, carried on every record, states the
governing philosophy in one sentence: *"A REJECT is honest market-efficiency evidence, not a
failure; calibration != edge (no $ claim)."* A reject can go stale and become revisitable once a
corpus grows (`stale_after_days`) -- the graveyard remembers without forbidding forever, because a
thin corpus and a permanently-dead signal are different things and the ledger should not conflate
them.

### 8. Ops-level honesty -- STUCK detectors and partial-baseline markers

A daemon that silently stops doing its job is a slower, quieter version of the same lie a bad
number tells: it looks fine from the outside (no crash, no error) while producing nothing. The
2026-07-07 incident that motivated this layer: an in-game settler ran 63+ consecutive ticks with
open bets and zero settles, and nothing surfaced it. The fix
(`scripts/platformkit/ingame/ingame_paper_settle.py::write_status`) folds a STUCK detector into
every status write: a tick that ends with open bets but zero settles increments a persisted
`consecutive_zero_ticks` counter; past a threshold (24 ticks, ~6h, `INGAME_SETTLE_STUCK_TICKS`)
the status flips from `OK` to `STUCK` so `ops_sentinel`/`feed_health` can alert on it. A quiet
daemon is now a visible one. The same principle -- surface partial state rather than let it read
as complete -- shows up across the platform as `VALIDATION_PENDING`, `NOT_TESTABLE`, and
`INSUFFICIENT_DATA` markers rather than a bare pass/fail: an in-game result waiting on more
real-corpus data is labeled as pending, not silently rounded up to done.

### 9. `edge_claimed: false` -- the stamp that travels with the artifact

Every ops artifact this system produces that could be mistaken for a betting result carries an
explicit `edge_claimed: false` field on the artifact itself -- not a caveat in a doc someone might
not read, but a machine-checkable field on the JSON. The honesty-gate's
`_check_edge_claimed_false` check enforces this directly: it reads the segment-trust and
in-game-verdict artifacts and fails closed if any of them is missing or if `edge_claimed` is
anything other than the literal boolean `False`. This is deliberately redundant with the lint
layer above -- a positive units figure should never be able to appear without its gate status and
its `edge_claimed: false` stamp sitting next to it, because a reader who only sees the number
should still see the honesty rail.

### 10. Git guards -- the layer that wraps the whole loop

`scripts/hooks/pretooluse_guard.py` runs as a live `PreToolUse:Bash` hook and blocks three classes
of command outright (exit code 2, the reason on stderr) regardless of what any agent believes it
should do: a bare `git push` or `git push origin` (origin is the public repo -- local commits
only, pushed only after explicit human review on a private remote), any command containing
`--force`, and a full `pytest tests/` (a bare directory target or no target at all -- this box
freezes on the full suite; a single test file is always allowed). It also emits non-blocking
guidance when a bash command is missing the required cwd prefix, because a flaky working directory
is a silent-failure risk of its own kind. This is a structural guard, not a request the agent can
talk itself out of -- it runs on every Bash tool call, independent of what the calling agent's
context window currently believes about the task.

---

## A claim dying honestly: CQR prop intervals (2026-06-26)

A concrete worked example, picked because it shipped a REJECT cleanly and is a good illustration
of "the rigor IS the product." Commit `a642eac5` (`domains/basketball_nba: CQR prop intervals ->
HONEST REJECT 7/7 stats`) built a Conformalized Quantile Regression gate (Romano et al. 2019) for
NBA prop intervals: leak-free walk-forward, a chronological 50/25/25 train/calibration/test split,
LightGBM quantile heads at `alpha/2` and `1-alpha/2`, conformity scores computed on the held-out
calibration slice, and an adaptive-width band applied on the untouched test slice -- compared
against the incumbent constant-width split-conformal band already in production.

The ship gate required three things simultaneously: interval coverage closer to the 90% nominal
target than the incumbent, pinball loss no worse than the incumbent, and a planted-null check
(shuffled features) showing real-signal collapse. On 356k real out-of-fold rows across all 7 prop
stats (`ast pts reb fg3m stl blk tov`, n_test=11,896 each), CQR won on pinball loss and interval
width -- genuinely sharper bands, on every single stat. But it over-covered the 90% nominal target
(91-96% actual coverage) while the incumbent constant-width band sat closer to nominal (88-91%),
failing the gate's strict proximity check; the planted-null inflation ratio also came in below the
1.5x bar the gate required. Honest verdict: `SHIP=0 REJECT=7`. The existing constant-width band
ships unchanged; the module lands as a default-off measurement script with a reusable template for
the next conformal-interval attempt, not wired into pricing.

What makes this the right worked example: a genuinely sharper model, measured honestly, still
failed the calibration bar it was held to -- and the system reported that plainly instead of
quietly relaxing the proximity check to let a "better" number through.

---

## What it costs

Being this honest is not free, and pretending otherwise would itself be a small dishonesty. The
concrete costs:

- **Most signals tried die.** The reject ledger exists because REJECT is the modal outcome of a
  leak-free gate, not the exception -- most hypothesized edges are, correctly, market-efficiency
  noise once you check them properly.
- **A sharper model can still lose the gate.** The CQR example above is the general case, not an
  edge case: "better on the metric I optimized for" and "clears every independently-checked bar"
  are different claims, and only the second one ships.
- **Real numbers are reported even when they are unflattering.** [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)
  documents an unpatched, measurable, publicly-surfaced bug (`sim_win_prob` polarity inversion)
  precisely because the alternative -- staying quiet about a known issue until it is convenient to
  fix -- is the same failure mode this whole stack exists to prevent.
- **A STUCK daemon is surfaced, not hidden.** The honest behavior for a settler that stops
  settling is to say so loudly (STUCK status, an ops alert), not to keep reporting a clean `OK`
  because nothing crashed.
- **Preregistration means a bar can be missed on the first real try.** A sha-pinned template that
  turns out to be too strict cannot be quietly loosened after seeing the result; it has to be
  re-registered as a new, honestly-labeled template, with the old one's history intact.

That IS the feature. A prediction system whose validation harness only ever confirms what it
already believed is not rigorous, it is decorative. The discipline stack above is what makes a
REJECT, a STUCK, or a retraction a normal, expected, load-bearing part of how this system works --
not an embarrassment to be edited out of the record.


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
