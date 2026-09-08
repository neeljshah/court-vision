# G304 Extension Eligibility Annotation - gpt-5.6-sol

- Annotator: gpt-5.6-sol (declared MODEL annotator), pass A2.
- Inputs: `C:/Users/neelj/nba-track-a4/docs/evidence/tracking/g304_e1_extension_manifest_2026-09-07.json` and `C:/Users/neelj/nba-track-a4/g304_local_renders_ext/`.
- Source worktree was read at commit `346b976a3a25f8b256617090ca2334a58e03712c`.
- Method: blind visual classification of all 75 native renders; no locator labels, projections, homographies, detector outputs, or candidate results were inspected.
- Rule: ELIGIBLE requires an identifiable court view and at least three named, distinct, well-spread marking structures; explicit out-of-scope views use the specified NEGATIVE category; otherwise UNRESOLVABLE states the reason.
- Time spent: about 35 minutes (about 28 seconds per row, including review and artifact preparation).

## Counts and quota status

| Source / arena | Extension E/N/U | Extension C/G/R | First pass E/N/U | Combined E/N/U | Combined C/G/R | 20 E + 10 N (4/3/3) | More rows needed |
|---|---:|---:|---:|---:|---:|---|---:|
| wnba_01 / Gateway Center Arena | 15/15/0 | 10/2/3 | 14/16/0 | 29/31/0 | 20/3/8 | MET | 0 |
| wnba_04 / Climate Pledge Arena | 25/18/2 | 4/1/13 | 9/19/2 | 34/37/4 | 11/1/25 | NOT MET | 2 graphics/transition negatives |

C/G/R means close-up / graphics-transition / replay-alternate. Counts establish candidate-pool availability; no final ten-negative subset was selected.

## NOT VERIFIED

- Arena identities are manifest labels and were not independently geolocated; only visual distinctness was assessed.
- Eligibility does not verify six-landmark availability, two-locator agreement, greater-than-4-pixel adjudication, or four eligible camera shots per arena.
- Climate Pledge Arena still lacks two graphics/transition negatives for the exact 4/3/3 negative composition.
- Four combined rows remain UNRESOLVABLE; the packet is therefore INSTRUMENT NOT VALIDATED and G306-G308 remain blocked.
- No registration, calibration, homography, prediction, detector, or tracking quality was measured or verified.

LF-normalized CSV SHA-256: `649331de7a5669e1b21dd0e4987a3369a8013769d97e7b48e463e1d8fcfed48c`.
