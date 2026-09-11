# G398 A8 High Resolution DEV Shadow -- Preregistration

Status: PREPARE-ONLY. This protocol authorizes no inference, rating, scoring, deployment, restart, flag, register, ledger, or data write. A Claude finisher alone may measure after the remaining launch-time checks.

## Binding inputs observed before this seal

- G394 independent disposition and handoff were read from lane tip `87a497e94`: RESULTS_LEDGER records `NOT VALIDATED`; its checkpoint receipt identifies the archived A8 input digest `0f05a61618687bda2005ce4ac8343c5987f60ba0076245597de59f7380398762`.
- Current G389 full-table check: `frames_v3.csv` has 1,620 rows: 1,071 development and 549 held-out. `dev_boxes_v3.csv` has 530 unique keys across 27 games. Held-out keys cover 32 games and 35 sections. `reference_v3.csv` has 302 held-out VISIBLE, 188 ABSENT, and 59 UNKNOWN states.
- Archived raw A8 weights: `docs/evidence/tracking/g390_ball_a8_sealed_pass_2026-09-11/a8_final_epoch.pt`, 6,259,242 bytes, SHA-256 `0f05a61618687bda2005ce4ac8343c5987f60ba0076245597de59f7380398762`; the G390 weight receipt records a torch zip readback of 365 members.
- Inputs are frozen from G389: `frames_v3.csv` SHA-256 `11797e162dd303441a7bde18e66fae4b404341fa2bd611678226182258d58945`, `reference_v3.csv` SHA-256 `ad00670c3601706d5d817de734fc85d82e8fdc379ea03b21bbe1a46e272ad09e`, and `dev_boxes_v3.csv` SHA-256 `e151f932c3b4bffe84c89aa8fde18f08c346a1e3a6e65d27ed4b36f095b7b4fa`.

## Frozen method

1. Freeze all 1,071 DEV keys, labels, boxes, source game, section, PTS, and native 1920x1080 receipts. Refuse any held-out or context identity in either tensor arm, preserve every ABSENT and UNKNOWN state, and assert all 549 held-out keys and 32 held-out games are absent from DEV tensors.
2. Use the full DEV reference, including the 530 reused training-positive frames. Do not repair labels or replace unavailable source pixels.
3. Baseline uses archived A8 weights and G390 arguments at imgsz 960. Candidate differs only by imgsz 1920. Both use conf 0.05, IoU 0.70, rank-0 OBSERVED, max_det 300, original precision mode, and the native-to-720p transform. No tiles, crop stage, person veto, augmentation, temporal input, threshold, weight, seed, or production-setting change is permitted.
4. One prospective paired shadow launch processes the sorted game/section/numeric-frame/key order in 30 interleaved quantile bins and alternates arm order by bin. The allowance is one sequential GPU launch with a 60-minute GPU-stage deadline. Failed, partial, or out-of-memory execution spends it and closes this option without substitution.
5. Save raw predictions and timing before any score. Independently replay the saved predictions twice in fresh scorer processes only. One run is descriptive and establishes neither a causal nor repeatable-system conclusion.
6. Score every DEV key using the frozen G363 centre tolerance `max(3 px, diameter_720p/2)`. UNKNOWN predictions are false positives. Archive TP, FP, FN, C0=TP/N_dev, Wilson95 precision lower, ALL FP/N_absent_dev, ABSENT-only FP, and per-key paired records. Improvement convention: baseline loss minus candidate loss; positive means the candidate has lower loss.
7. The continuation condition is strict: candidate C0 > baseline C0, candidate Wilson lower >= baseline Wilson lower, and candidate ALL FP/N_absent <= baseline. Any tie fails continuation. Historical bars 0.25/0.90/0.01 remain unchanged and untested.
8. Prepare 30 evenly distributed paired native cards across all DEV keys, including silence and UNKNOWN states. No score, rating, or eye judgment is performed by this preparation lane.

## Required launch-time refusal conditions

Refuse measurement if a frozen input hash, source byte/resolution receipt, code identity, environment receipt, held-out isolation assertion, launch token, or raw prediction archive is missing. Refuse a second launch. Do not infer held-out or context frames.

## Planned artifacts and placeholder verdict

The finisher must create only the named G398 evidence artifacts under this directory, with raw predictions and timing preceding scores. This prepare-only lane records no measured result. Placeholder verdict: NOT VERIFIED -- no DEV inference, rating, or score has run.

## NOT VERIFIED

- No baseline or candidate inference has run.
- No DEV continuation condition, historical bar, latency, VRAM, eye check, or paired arithmetic has been measured.
- Runtime source-pixel availability, route hashes, environment identity, and launch eligibility require a fresh finisher check.
SEAL sha256 47d81b921baa4941e4db36601486bc88ddf6a6bf89dea77900364129bdaed700
