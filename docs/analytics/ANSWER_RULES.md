# NBA Answer Engine -- binding rules

Read [README.md](README.md) and [nba.md](nba.md) first. This file governs any
Claude (or human) consuming `domains/basketball_nba/concepts/concept_registry.py`
and `scripts/platformkit/answers/contracts.py` to answer a scouting-style
question. It is public-safe -- no numbers here are edge/$ claims.

## The core rule

A scouting question about a CONCEPT ("best gravity", "who protects the rim
best", "does X fit team Y's need for spacing") is **never** answered by
sorting one raw attribute column. Concept questions route through the concept
registry's derived-weight composite (`concept_registry.derive_weights` +
`contracts.answer_superlative/comparison/explanation/fit`). A single-attribute
lookup is fine for a plain fact question ("what is X's clutch eFG?") -- that
still goes through `scripts/platformkit/profiles/ask.py`, unchanged.

Why: raw single-attribute rankings are dominated by small-sample noise near
that attribute's own floor. Verified on this repo's real data -- the bare
`gravity` column's top-ranked players at n~330-400 (near its 300-minute floor)
are role players, not the stars a scout would name; the concept composite
(gravity + spacing_contribution, status-rank x n-shrinkage weighted, floor
raised to 1000) surfaces LaMelo Ball / Luka Doncic / Victor Wembanyama instead.

## Every answer object carries, always

- `window` -- which season/period the numbers are from.
- `n` (or per-ingredient `n`) -- the sample size backing the number.
- `status` (or `status_mix`) -- VALIDATED_MECHANISM / VALIDATED_CLAIM /
  DESCRIPTIVE / PROVISIONAL, per `attribute_registry.py`'s ladder.
- `ingredients` / `decomposition` / `ingredient_table` -- what the number is
  made of, never a bare composite score with no breakdown.
- provenance back to the concept registry's `weight_basis` for WHY each
  signal is included (read the registry entry, not just the output number).

**Never print a bare number for a concept question.** If code you are writing
or reviewing does that, it violates this rule -- fix the caller to route
through `contracts.py`, not to hand-roll a shortcut.

## Status ties and low-n

- VALIDATED_MECHANISM beats VALIDATED_CLAIM beats DESCRIPTIVE beats
  PROVISIONAL in any tie or borderline call -- this is the same status ladder
  the profile builder already declares, re-used, not re-invented.
- If an entity's primary signal sits below the concept's declared `min_n`, it
  is EXCLUDED from a superlative ranking, not shown with a caveat. If asked
  directly about a below-floor entity (explanation/comparison/fit), SAY the
  n is thin and the confidence tier is LOW -- never present a low-n number
  with the same confidence as a well-sampled one.
- Confidence tiers (`contracts._confidence_tier`) are deterministic: LOW if
  any signal is PROVISIONAL or the primary signal is below its own floor;
  HIGH only if status is VALIDATED_CLAIM-or-better on average AND the primary
  signal's n is at least 2x the concept floor; MEDIUM otherwise. Do not
  invent a different confidence heuristic ad hoc.

## Question routing

| Question shape | Route to | Never |
|---|---|---|
| "best X" / "who has the most X" | `contracts.answer_superlative` | ranking one raw column |
| "A vs B on X" | `contracts.answer_comparison` | reporting only the winner, no ingredient table |
| "why is A good at X" | `contracts.answer_explanation` | a one-line answer with no decomposition |
| "does A fit team T's need for X" | `contracts.answer_fit` | inventing a "team need" score -- there is no on-disk team-need dataset; the only honest proxy is the given roster's own composite average, and the answer object says so explicitly |
| "will A win", "what is the win probability", any forecast/odds/spread question | `predict-matchup` (the calibrated forecasters) | routing to profile attributes or concept composites at all |

Concept vs. calibrated forecast are DIFFERENT systems for a reason: concept
composites are DESCRIPTIVE scouting reads (mostly unvalidated against actual
game outcomes -- see `attribute_gate.py`'s NULL/SKIPPED verdicts for most NBA
profile attributes tested pregame so far). A concept score is not a
prediction and must never be presented as one.

## No edge / no dollar claims

This file, and everything it governs, is public-safe. Nothing here computes
or implies betting edge, ROI, or a dollar figure. See
`.claude/rules/no-edge-claims.md` for the binding list of numbers that may
never be reprinted as current. If a consuming agent is tempted to turn a
concept ranking into a betting angle, stop -- that is out of scope for this
engine entirely.

## Extending the registry

Adding an 9th+ concept: every `signals[].attribute` MUST already exist in
`domains/basketball_nba/profiles/attribute_registry.py`'s `ATTRIBUTES` dict
(verified by `test_concept_registry.py`) -- never invent a new raw metric
inside the concept registry itself; that belongs in the attribute registry
and its builder first. Document `weight_basis` (why included), at least one
`context_qualifier`, and at least one `failure_mode` for every new concept --
an undocumented concept is not mergeable.
