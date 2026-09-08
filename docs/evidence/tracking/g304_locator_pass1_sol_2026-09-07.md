# G304 Locator Pass 1 - gpt-5.6-sol

Locator: gpt-5.6-sol, MODEL locator, pass 1, blind to all other locator-pass artifacts.
Method: reviewed every supplied ELIGIBLE render before any projection, homography, detector, or prediction output.
Sealed inventory: `C:/Users/neelj/nba-track-a4/docs/evidence/tracking/g304_e1_sealed_heldout_packet_manifest_2026-09-07.json` at `a6fa18878a3cc7409ef78fe495af37b1d5b52f0c`.
Inventory identity: canonical manifest payload SHA-256 `5806527e2d50c9830a12774e690e440dcda6a4e56fe04b933c676fd48aed14c1`.
Renders: `C:/Users/neelj/nba-track-a4/g304_local_renders/`, 1920x1080 JPEG inputs, read-only.
Eligibility: `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g304_eligibility_sol_2026-09-07.csv` at a3 HEAD `bbfb14b80ace3426c1f8402df145419d3cc647cf`.
Crop scale: 1.0 native pixels, no resampling; three overlapping 1280x900 crops per eligible frame, y=120:1020 and x=0/320/640.
Coordinates in the CSV are in original 1920x1080 pixels; `_L` is the far/top endpoint and `_R` is the near/bottom endpoint for paired lane and free-throw-line names.
Elapsed annotation wall time: approximately 38 minutes of model session time.

## Counts

Supplied classification: 60 unique rows = 23 ELIGIBLE, 35 NEGATIVE, 2 UNRESOLVABLE.
CSV: 142 records = 94 visible LANDMARK, 37 FRAME, 11 explicit SHORTFALL records.
Gateway Center Arena: 14/14 eligible rows labeled, 81 landmarks; per-frame distribution 6x12, 5x1, 4x1; 16 negatives, 0 unresolved.
Climate Pledge Arena: 9/9 eligible rows labeled, 13 landmarks; per-frame counts 3,0,2,1,2,1,2,0,2; 19 negatives, 2 unresolved.
Unresolved rows: `wnba_04_02` and `wnba_04_08`; each lacks three reliably identifiable marking structures in its moving midcourt crop.
Negative categories: Gateway 10 close-up, 1 graphics/transition, 5 replay/alternate-camera; Climate 7 close-up, 0 graphics/transition, 12 replay/alternate-camera.

## NOT VERIFIED

- NOT VERIFIED: the supplied 23/35/2 classification does not meet the sealed target of 40 eligible, 20 negative, 0 unresolved.
- NOT VERIFIED: 11/23 eligible rows contain fewer than six visible named landmarks; only 12/23 meet six across at least three structures.
- NOT VERIFIED: the required per-arena 4/3/3 negative split is absent from the supplied classification.
- NOT VERIFIED: arena names are transcribed; the renders show visually distinct courts but do not independently establish venue identity.
- NOT VERIFIED: this is one model locator only; inter-locator agreement and every difference over 4 px remain unmeasured and unadjudicated.
- NOT VERIFIED: this pass measures no registration, no calibration, and no tracking quality whatsoever.
- NOT VERIFIED: G306-G308 remain blocked; an incomplete packet means INSTRUMENT NOT VALIDATED.

Unresolved labels mean INSTRUMENT NOT VALIDATED -- they are NOT omitted frames and NOT successful abstentions.
Agreement alone never establishes correctness.
LF-normalized CSV SHA-256: `5540545aaf575bb1dbc3d08c525a78561f67e9a3fe82e7b374114960edeb3251`.
