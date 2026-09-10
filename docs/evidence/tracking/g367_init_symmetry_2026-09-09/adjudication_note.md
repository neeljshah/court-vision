# G367 orientation set -- blind adjudication note (2026-09-09)
Scope. 54 sheets in `sheets/manifest.csv`; terra and sol each rated all 54, every label in
{left,right,unknown}, none missing or invalid. 48 agree and keep the agreed label unchanged (never
re-rated); 6 disagree and were adjudicated from the sheet alone.
What I saw. Of the 6 opened: 4 carry a usable court view (a ball handler advancing with the lone
defender ahead of him; a drive toward an endline lined with photographers; two trailing attackers
entering an empty half with the lane opening off the frame edge; a transition running from the
centre-circle logo toward a visible backboard). 2 are tight low rim angles with no floor and no
court lines, so neither side is determinable and both took `unknown`. All 6 rendered; none failed
to open. No cue value, no detector output and no numeric column of `orientation.csv` was read.
Class counts vs the rails. Reference after adjudication: left 12, right 16, unknown 26;
N_labelled (left or right) = 28. The n >= 30 per class rail is NOT met on either class, and the set
holds 54 rated frames against the bar-5 floor of 60, so the orientation part is PARTIAL on both
counts (Q7 and bar 5). `unadjudicated_frames` is empty.
Blindness deviation, disclosed. Disagreeing sheets were found by comparing the two rating files, so
the adjudicator saw the disputed label pair (and its rater) before opening those 6 images. Each
label was read off the image; 2 of the 6 match neither primary rater.
Files. `ratings.csv` is the prereg long form (frame_key,rater,label,reason) with terra, sol and 6
ADJUDICATOR rows; `ratings_wide.csv` carries the requested per-sheet resolved view. Reference
labels are NOT VERIFIED against any cue; nothing here is wired to `src/`.
