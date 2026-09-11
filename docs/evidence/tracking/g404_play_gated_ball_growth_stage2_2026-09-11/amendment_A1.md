# G404 amendment A1 -- one native card per transport request

## Authority and scope

This amendment is sealed ALONE, in its own commit, BEFORE any rating card is
dispatched. It amends nothing in the sealed preregistration
`docs/evidence/tracking/g404_play_gated_ball_growth_stage2_2026-09-11/prereg.md`
(sealed alone at 5112012e9, SEAL
`36ffa3620e776f6bb3a7e8e335fe1cb4dbd90791ac6d3994743e1cf48eeb4de4`), which is
never edited. It clarifies HOW a sealed card reaches a rater. Every bar, count,
order, label vocabulary, centre rule and verdict rule in the preregistration and
in `docs/evidence/tracking/specs/G404_spec.md` is unchanged. Source: the astra
round 10 transport clarification, `docs/research/astra_round10_2026-09-12.md`
section A BALL (local-only).

## The original clause this clarifies

The preregistration states, verbatim:

> Each rater receives G403's 30 controls once without feedback and must achieve 30
> of 30 state decisions plus all 20 known visible centre matches. Any failure is
> `NOT VALIDATED` and stops real rating.

and, for the gate audit:

> Two raters independently label native full frames `PLAY`, `NONPLAY`, or `UNKNOWN`
> without gate output or ball coordinates.

Neither clause says how many cards travel in one transport request. G400's round 8
failure was diagnosed by G403 as a one-card ANSWER-TO-CARD BINDING SLIP inside a
multi-card batch (`g403_ball_rater_failure_controls_2026-09-11/instructions.md`,
SEAL `9693c36fb2e928107e0cf99dd20501c953286072d174ac205bf11e951892f825`), so the
transport, not the judgement, is what this amendment pins.

## The clarified transport (binding for this row)

1. Logical rounds stay at 30 cards. Round membership, round order, card order
   within a round, the 300 planned keys and every sealed bar are unchanged.
2. ONE native card is delivered per transport request. The rater echoes that
   card's id and its image SHA-256 in its answer, and the echo is validated
   before the next card is sent.
3. Order is preserved. A card is never renumbered, realigned, replaced or
   silently re-sent beyond the sealed retry count.
4. A failed or absent echo is a `BINDING_FAULT` for that card: it is recorded with
   the raw answer, the card counts as unvisited, and its state is `UNKNOWN`. An
   unvisited card is recorded distinctly from a card reviewed and judged `UNKNOWN`.
5. Each rater runs from an authenticated, writable home with no prior answers or
   context for this row. The terra home is created fresh by copying ONLY the
   authentication material of the existing terra home; its exact path and the
   model/version string observed in a smoke run are recorded in the evidence.
6. A home change alone is NOT a binding remedy. The per-card echo is the remedy.
   One smoke card with a validated echo is proven for each rater BEFORE the
   controls, and the controls before any real card.
7. Everything else -- native pixels, `sheet_scale` 1.0, the centre rule, the
   three-label vocabulary, the kappa rail, the usability rail, the control pass
   condition and every verdict rule -- is exactly as sealed.

SEAL sha256 93857d40a18f09d740e29618546e75398259d759447fb02beadab93a9eaee5d8
