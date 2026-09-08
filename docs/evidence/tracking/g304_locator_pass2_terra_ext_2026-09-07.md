# G304 Locator Pass 2 Extension Memo
Locator: gpt-5.6-terra (MODEL).
Scope: 40 blind-eligible extension rows only; no registration, projection, calibration, tracking, detector, or prediction was run.
Method: opened commit-pinned 1920x1080 JPEG renders and used cv2 headless native zoom crops for direct landmark marking.
Inputs: `C:/Users/neelj/nba-track-a4` commit `346b976a3`, manifest `docs/evidence/tracking/g304_e1_extension_manifest_2026-09-07.json` (49,765 bytes), and `g304_local_renders_ext/` (75 renders).
Eligibility input: `C:/Users/neelj/nba-track-a20` commit `a4d5ac8b8`, `docs/evidence/tracking/g304_eligibility_ext_sol_2026-09-07.csv` (15,332 bytes).
Byte check: all 40 used render blobs match sealed commit `346b976a3`; each decoded render is 1920x1080.
Arena counts: Gateway Center Arena / wnba_01 = 15 frames, 90 visible landmarks; Climate Pledge Arena / wnba_04 = 25 frames, 100 visible landmarks.
Landmarks per frame: wnba_01 all 15 frames = 6; wnba_04 all 25 frames = 4 plus an explicit visible=0 shortfall record.
Shortfall rows: wnba_04_e01, wnba_04_e02, wnba_04_e06, wnba_04_e07, wnba_04_e09, wnba_04_e11, wnba_04_e14, wnba_04_e16, wnba_04_e17, wnba_04_e18, wnba_04_e24, wnba_04_e25, wnba_04_e26, wnba_04_e27, wnba_04_e30, wnba_04_e33, wnba_04_e34, wnba_04_e37, wnba_04_e38, wnba_04_e39, wnba_04_e41, wnba_04_e42, wnba_04_e43, wnba_04_e44, wnba_04_e45.
Time: 00:48:00 local annotation and validation wall time.
NOT VERIFIED:
- This locator is a model (gpt-5.6-terra), not a human.
- The wnba_04 shortfall frames do not meet six visible vocabulary landmarks across three marking structures.
- No second-locator comparison, adjudication, registration, calibration, or tracking quality is verified here.
- Agreement alone never establishes correctness. Unresolved labels mean INSTRUMENT NOT VALIDATED; they are not omitted frames and not successful abstentions.
LF-normalized CSV SHA-256: c0465aa9afd24b9ad1b4aac683539603883deda6c7b2f91a588c036208e40cbe
