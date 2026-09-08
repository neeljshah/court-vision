# G304 locator pass 2: gpt-5.6-terra model annotation

- Method: model-only visual annotation from the sealed renders and the blind eligibility sheet; no fitting, projection, detector, homography, or prediction was opened or run.
- Inputs: `C:/Users/neelj/nba-track-a4/docs/evidence/tracking/g304_e1_sealed_heldout_packet_manifest_2026-09-07.json` (49,256 bytes) and its native 1920x1080 JPEG renders under `C:/Users/neelj/nba-track-a4/g304_local_renders/`; eligibility input `docs/evidence/tracking/g304_eligibility_sol_2026-09-07.csv` (11,779 bytes).
- Crop scale: cv2 headless 2x bicubic crops of each 960x540 quadrant; CSV coordinates remain original 1920x1080 pixels.
- Gateway Center Arena: 14 eligible frames labelled; 6 visible landmarks per frame; 84 visible landmarks.
- Climate Pledge Arena: 9 eligible frames labelled; 4 visible vocabulary landmarks per frame; 36 visible landmarks and 9 explicit shortfall rows.
- Negative rows: 35 recorded with the blind category and no landmark names. Unresolvable rows: `wnba_04_02`, `wnba_04_08`; reason recorded in CSV.
- Shortfall rows: `wnba_04_03`, `wnba_04_04`, `wnba_04_06`, `wnba_04_09`, `wnba_04_12`, `wnba_04_16`, `wnba_04_17`, `wnba_04_20`, `wnba_04_22`; only four vocabulary landmarks were visibly locatable.
- Time spent: approximately 34 minutes, including crop generation and per-frame review.
- NOT VERIFIED: gpt-5.6-terra is a model, not a human; no independent second locator comparison or adjudication was performed.
- NOT VERIFIED: all shortfall and UNRESOLVABLE rows leave the instrument not validated; they are counted, not omitted.
- NOT VERIFIED: this pass measures no registration, no calibration, and no tracking quality.
- Contract self-check: no selected row was removed; no result is reported beyond this model locator annotation.
- CSV SHA-256 (LF-normalized): 9ceaea77100e7c39ad9476d15172bc7de6929bcb59f506a0c07ad579dcf96f92
