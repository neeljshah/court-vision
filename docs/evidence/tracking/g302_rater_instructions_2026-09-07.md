# G302 attempt 2 -- blind rater instructions

You are the SINGLE rater for tracking row G302 attempt 2. You are a MODEL, not a human, and no human
will check your work; that limit is already recorded in the row and is not your problem to solve.
This is a MEASUREMENT. There is NO pass bar, no target number, and no outcome that counts as success
or failure. Report what you see.

## What you are rating

216 image crops, each 512x640 pixels, listed in
`docs/evidence/tracking/g302_amateur_resolution_attribution_artifact/blind_packet/blind_rating_manifest.csv`
(columns `blind_index`, `crop_path`). Each crop is a neighbourhood of ONE object-detector box's
claimed footpoint, drawn from basketball video. A RED CROSS AND CIRCLE mark the exact footpoint being
judged, at the centre of the crop.

The crops come from three different video sources, deliberately shuffled and renamed so you CANNOT
tell which crop came from which source. Do not try to work it out, do not group the crops, and do not
let a guess about the source change a rating. Rate each crop on its own.

## The four categories -- fixed, unchanged, exhaustive

Judge the subject AT THE RED MARKER (within roughly 48 px of it). Use the whole crop for context.
Every crop gets exactly ONE of these four, spelled EXACTLY as written here:

- `PLAYER` -- a person at the marker who is a uniformed player of one of the two competing teams AND
  is on the marked playing court, apart from any bench, chair, huddle, timeout or scorer's-table
  cluster.
- `PERSON NOT PLAYER IN PLAY` -- a person at the marker who is not that: referee, coach, staff,
  broadcast or camera crew, cheerleader, spectator, scorer's-table crew, a seated or huddled bench
  player, or a uniformed player who is off the court of play.
- `NOT A PERSON` -- no person at the marker: floor, seat, wall, equipment, or a broadcast graphic.
- `CANNOT JUDGE` -- a person IS at the marker but the crop does not let you decide their
  on-court-of-play status (a close-up whose surroundings are not visible, or unresolvable blur).

`CANNOT JUDGE` is a real answer and is expected on some crops. Use it when it is true. Never use it
to avoid a call you can actually make, and never redistribute it into another category.

## What to produce

Fill in the verdict column of
`docs/evidence/tracking/g302_amateur_resolution_attribution_artifact/blind_packet/blind_verdicts.csv`,
in place, keeping its exact two-column header `blind_index,verdict` and all 216 rows in ascending
`blind_index` order 1..216. Write ONE of the four strings above in every `verdict` cell. Leave no
cell blank; add no column; add no row; change no `blind_index`.

Also write `docs/evidence/tracking/g302_rater_note_2026-09-07.md`, at most 25 lines: your rater name
and model, the number of crops rated, the count in each of the four categories, the wall-clock time
you spent, and the SHA-256 of the LF-normalized `blind_verdicts.csv`.

## Rules

- Rate ALL 216 in ascending `blind_index` order. NEVER PARK: rate every row before you stop. If you
  genuinely cannot finish, say exactly how many you completed -- do not leave rows blank silently and
  do not rate some crops more thinly than others.
- Do NOT open, read, search for, or reason about any unblind map, arm name, source-frame number,
  presentation order file, detection CSV, summary JSON, prereg, memo, or any other G302, G273 or
  G280b artifact. The crop images and this file are your only inputs.
- Do not push. Never use `--force`. ASCII only. Calibration language only: no monetary, return-on-stake or
  wagering language anywhere in what you write.
- Try to commit by explicit pathspec. If `git commit` is DENIED by the sandbox, leave the files on
  disk and finish with the line `SHA: NOT CREATED (sandbox); files ready for lane_commit` followed by
  every path you created or modified.
