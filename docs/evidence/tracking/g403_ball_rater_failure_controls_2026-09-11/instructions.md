# G403 sealed ball-rating instruction set (v2, for the next collection stage)

This replaces the free-text instruction G400 used. It does NOT weaken the sealed centre rule and it
does not change the scale contract. Sealed for the next stage; it may not be edited in place.

## What you are looking for

1. Locate the ONE basketball that is participating in on-court action on this card: the ball a
   player is holding, dribbling, passing, shooting, or the loose ball that is live on the floor.
2. In your answer, NAME the object you chose and the visible support for it (for example
   "ball in the shooter's raised hands", "loose ball on the floor inside the arc").

## Objects that can never supply a centre

3. Rim hardware -- the ring, the net, the backboard, the shot-clock housing, the stanchion padding.
   An orange object at the ring is hardware unless you can see the ball separately from it.
4. A spare ball at the bench, on a rack, in a ball-boy's hands, or anywhere off the live playing
   surface. A basketball that is present but not in play is NOT the answer.
5. A jersey patch, a kit logo, a shoulder or arm, a shoe, a court logo, an advertising board, a
   broadcast graphic, a clock or score overlay, a challenge or replay card, and anything in the
   crowd. If your candidate is one of these, you have not found the ball.

## When to answer UNKNOWN and when to answer ABSENT

6. UNKNOWN: two or more objects are plausibly the game ball and you cannot separate them, or the
   ball's identity is obscured by blur, occlusion or scale. UNKNOWN is a correct answer, not a
   failure, and it is preferred over a guessed centre.
7. ABSENT: the card clearly contains no game ball at all -- a bench or player close-up, a crowd
   shot, a full-screen graphic, a wipe.
8. Never answer VISIBLE without a centre, and never answer VISIBLE for an object you have named as
   one of the objects in section 3 to 5.

## Geometry (unchanged from G389 and G394)

9. Work in NATIVE pixels of the card you were given, at `sheet_scale` 1.0. Never rescale, never
   assume a 1920-wide frame for a 1280-wide card. A centre or box outside the card's own native
   width and height is an invalid answer.
10. The sealed centre rule is unchanged: a centre matches when it lies within
    `max(3 px, diameter_720p / 2)` of the reference centre. Report the box as
    `x, y, w, h` in native pixels; the centre is the box centre and the diameter is `(w + h) / 2`.
11. You see the full native view and no peer labels, no prediction markers, no other rater's answer.

## Card-to-answer binding (new; this is the round-8 failure mode)

12. Every answer line MUST repeat the card id you were given, and you MUST answer the cards in the
    delivered order, one answer per card, with no line reordered, merged or skipped.
13. Before you write a line, re-read the card id you are looking at. If the image you are viewing
    cannot be tied to the id on the line you are about to write -- the batch is short, a card fails
    to open, or you have lost your place -- write `BINDING_FAULT` for that id and stop the batch.
    Do not continue from the next card to catch up.
14. Naming the object and its support (rule 2) is what makes a slipped binding visible afterwards,
    so never leave the support field empty, including for ABSENT and UNKNOWN.

## Draw discipline

15. Cards are drawn before rating and cannot be dropped afterwards. No card may be rejected because
    of what turned out to be in it: an all-graphic card, a bench close-up or an unresolvable card is
    answered ABSENT or UNKNOWN and stays in the denominator.
SEAL sha256 9693c36fb2e928107e0cf99dd20501c953286072d174ac205bf11e951892f825