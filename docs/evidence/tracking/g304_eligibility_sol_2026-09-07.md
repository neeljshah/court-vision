# G304 Eligibility Annotation - gpt-5.6-sol

- Annotator: gpt-5.6-sol (declared MODEL annotator).
- Method: inspected all 60 native 1920x1080 renders individually and in row order; used no candidate output, projection, homography, detector result, or classified locator label.
- Rule: ELIGIBLE requires an identifiable court view with at least three distinct, well-spread marking structures; explicit out-of-scope views are NEGATIVE; an in-scope-looking view with fewer than three reliable structures is UNRESOLVABLE.
- Arena eye check: the sources are visually distinct. wnba_01 has gray hardwood, black paint, and a bright blue apron; wnba_04 has striped tan hardwood and a forest-green apron.

| source | eligible | negative | unresolvable | close-up | graphics/transition | replay/alternate-camera | 20+10 met |
|---|---:|---:|---:|---:|---:|---:|---|
| wnba_01 | 14 | 16 | 0 | 10 | 1 | 5 | NO |
| wnba_04 | 9 | 19 | 2 | 7 | 0 | 12 | NO |

- Quota shortfall: wnba_01 needs 6 additional eligible rows; wnba_04 needs 11; eligible-only deficit is 17 rows total.
- Exact 30-row and 4/3/3 composition cannot be repaired by appending while retaining all 60 rows. A replacement inventory needs at least 8 new candidate rows for wnba_01 (6 eligible, 2 graphics/transition) and 14 for wnba_04 (11 eligible, 3 graphics/transition), 22 replacements total.
- UNRESOLVABLE: wnba_04_02 and wnba_04_08 show a sideline and center-circle fragments but fewer than three reliably identifiable marking structures.
- Time spent: 15 minutes for visual annotation and artifact preparation; about 15 seconds per row including recording and review.
- LF-normalized CSV SHA-256: `a3a456d7a6ebc810bbddea06ef61ede88aaf60fc9a8873c557c818bd0596b6f3`.

## NOT VERIFIED

- The transcribed arena names Gateway Center Arena and Climate Pledge Arena were not independently verified; only visual distinctness was confirmed.
- Eligibility annotations do not verify six-landmark availability, two-locator agreement, >4 px adjudication, or >=4 eligible camera shots per arena.
- The required exact negative split of 4 close-up / 3 graphics-transition / 3 replay-alternate per arena is not met.
- Two rows remain UNRESOLVABLE; the packet is therefore INSTRUMENT NOT VALIDATED and G306-G308 remain blocked.
- No registration, calibration, homography, prediction, detector, or tracking quality was measured or verified.
