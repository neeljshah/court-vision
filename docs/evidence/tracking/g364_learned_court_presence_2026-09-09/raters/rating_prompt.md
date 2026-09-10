# G364 blind development rating prompt

The rater sees only JPEG sheets. No score, probability, margin, prediction, model
name, threshold, candidate, competition, or game identity is supplied. Each sheet
shows one centre frame plus the causal three-frame strip around it.

Assign exactly one of these four labels to every sheet:

- `USABLE_COURT` -- a wide broadcast view of the live playing floor in which the
  court and its markings are visible across the frame and play can be located on
  the floor.
- `CLOSEUP` -- a tight shot of one or a few people (player, coach, bench, referee,
  interview, huddle) in which the floor as a whole is not visible.
- `CROWD_GRAPHICS` -- crowd, arena architecture, scoreboard, score bug filling the
  frame, studio desk, advertising, replay wipe, title card, or any other content
  that is not the live floor view.
- `UNKNOWN` -- the sheet cannot be assigned: transition, motion blur, black frame,
  or genuinely ambiguous content.

Rules:

- Judge the CENTRE frame. The strip is context for motion only.
- Never guess a label to avoid `UNKNOWN`; `UNKNOWN` is a real answer and its share
  is reported.
- Rate every sheet in the batch exactly once.
- Output only CSV, no prose, with the header `sheet,label` and one row per sheet,
  where `sheet` is the file basename without the `.jpg` extension.
