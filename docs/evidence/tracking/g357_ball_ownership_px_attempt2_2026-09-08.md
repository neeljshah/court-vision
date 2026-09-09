VERDICT: PARTIAL -- window/base-video-id/competition bar MET (31 windows / 14 base-video ids / 10 competitions, all post-epoch, evenly sampled, not a head slice); the sealed >=100 eligible observed-ball motion-pair bar was NOT MET (px 29, old 6); the sealed 200-per-mille shuffle-drop bar was NOT MET (103.4pm both directions, baseline rate itself only 10.3%, n too small to be stable).

# G357 pixel-space ball ownership attempt 2, fix 1b (2026-09-08/09, LOCAL/POD-READ, FINISHER)

SUPERSEDED (verifier REJECT, B7 head-slice): the first-30-of-32 result (commit bca82687c) reported in-radius 27/1800 (px) vs 9/1800 (old), eligible 19 vs 8, shuffle delta 158 per mille -- not reinterpreted; `sealed_windows.csv`/`survival.csv`/`states.csv` left in place unedited for the record.

Interpreter: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe. Amendment prereg `g357_prereg_fix1b_2026-09-08.md` seal `a5262e8197e7f63e4d097dcfc0cf5314cb47c8e21d6944f249840d18e002c1a9` (self-verified). Free RAM before start 2,905,944 KB. Pod read-only throughout; no write, no daemon/guard touch (pids 1596016 / 1519254 untouched).

CENSUS + EVEN-SAMPLED RESEAL (Q1, commits c7508f6f5 prereg, ea4a75e98 census+seal): read-only ledger scan found n=61 post-epoch tracked-basketball candidates, all 61 carrying the px header (eligible=61); `census.csv` archives status/finished_at/seconds/start_epoch/px_header_present/rows/competition per candidate so eligibility is independently reproducible without re-querying the rotating ledger. Even sample (k=floor(61/30)=2, start=floor((61 mod 30)/2)=0): 31 windows at 0-based indices 0,2,4,...,60 -- spans the full set, not a head slice. `sealed_windows_fix1b.csv`: 31 windows, 14 base-video ids, 10 competitions (fiba, eurocup, lnb, ncaaw, acb, UPco, euroleague, nba, ncaa_basketball, wnba -- NBA and WNBA both represented this time, unlike the superseded sample). Fetch: 62 files via one read-only tar stream, sha256 verified vs the sealed list, 0 mismatches.

SURVIVAL (F=1860 pooled = 31 x 60, px vs old court-map join, same sealed windows, shift 0):
stage                    px n / share      old n / share
frames                   1860 / 1000pm     1860 / 1000pm
any_ball_row              505 / 272pm       520 / 280pm
detected_ball             358 / 192pm       372 / 200pm
player_rows               344 / 185pm       358 / 192pm
player_within_radius       39 /  21pm         7 /   4pm   <- in-radius ~5.6x on px
prerequisite_available     29 /  16pm         6 /   3pm   (== eligible pairs; bar >=100 NOT MET either arm)
motion_agreement            3 /   2pm         1 /   1pm
accepted_ownership           3 /   2pm         1 /   1pm

OWNERSHIP: share of F (px) = 3/1860 (2pm). Share of eligible pairs (px) = 3/29 (103pm); old = 1/6. All 3 accepted owners are on `source=detected` (observed); 0 on `source=inferred` (states_fix1b.csv: detected/OBSERVED_VALID 357, inferred/INFERRED 147, ambiguous 1, absent 1355 of 1860) -- same no-inferred-acceptance pattern as the superseded result.

SHUFFLE CONTROL (agreement = accepted_ownership / prerequisite_available, px arm): shift 0 = 3/29 = 10.3%; shift -30f = 0/19 = 0.0%; shift +30f = 0/20 = 0.0%. Delta = 103.4pm both directions. Sealed >=200pm(20pp) bar NOT MET -- the baseline rate (10.3%) is itself below 20pp so no shift can mathematically clear the bar at this n; n (19-29) is too small for a stable estimate regardless of verdict.

G351 RATIO SANITY (per window, px, bar <=1.5 both axes): 28 of 31 windows printed a ratio (3 had <2 finite points); 0 of 28 flagged (the superseded result flagged 3 of 27 on the y-axis; not reproduced here).

Tests, each run alone: `test_g357_px_join.py` 3 passed; `test_g349_ball_survival.py` 2 passed; `test_g344_ball_shadow_possession.py` 3 passed; new `test_g357_fix1b_census.py` 4 passed. No full suite ran. 0 threshold moved, 0 flag flipped, 0 src/kernel/api/intel file touched, 0 column renamed/removed; `g357_px_join.py` is byte-identical to the rejected candidate's (sha256 matches). `survival_fix1b.csv` adds `ball_shift` and a correctly-denominated `share_per_mille_of_eligible` per window/arm/shift (the superseded file's same-named column used a constant-1 denominator; not replicated here).

HONEST LIMITATIONS: coverage and shuffle response establish sensitivity, not ownership correctness; nearest player is not the handler; the post-epoch pool is whatever the feeder shipped by seal time, not a designed sample; with 29 (px) / 6 (old) eligible pairs the ownership/shuffle numbers are a screening, not a powered estimate; ball detection coverage (any_ball_row ~27-28pm of frames) is the ceiling on every downstream stage. EYE CHECK: NONE.

NOT VERIFIED: the >=100 eligible-pair bar (px 29, old 6) and the >=200pm shuffle-drop bar (103.4pm) -- shortfalls named, not reinterpreted; nearest-in-radius player as true ball handler, not checked against video for any accepted-ownership row; source_height taken from the ledger's own field (1080 for all 31 sealed clips), not re-measured; any causal reason the now-present NBA/WNBA clips differ from the fiba/eurocup-heavy superseded sample.

WALL TIME: 2026-09-08 23:52 UTC - 2026-09-09 00:53 UTC (~61 min, includes reading the reject memo/spec/prereg in full before any new file was written; pod read-only contact 00:35-00:45 UTC).

SHA-256 (LF-normalized bytes): prereg_fix1b(embedded seal)=a5262e8197e7f63e4d097dcfc0cf5314cb47c8e21d6944f249840d18e002c1a9; px_join.py(unchanged)=e4c4ec9568fb540ec5ce87ff73daac6c1c8725a7527a61a0b08e89e025d4fab6; g357_fix1b_census.py=94fb0fc2b726d629b52e90dc9e77859b8fddaa29e1759d57ab3d387f6baa3677; census.csv=ed2e668020966b0530b5076a1ced24b8b8504a9b85c092699ab16d4819f8fea8 (6086 B); sealed_windows_fix1b.csv=291df3f4243b5804cc9dd14c29ed81dd51b5556e86458782554e60327c01d55b (12600 B); survival_fix1b.csv=ea342f4ad84f515e6bc9c3060451521690c09877df0070cd3f7cc4864c67ce2e (163674 B); states_fix1b.csv=f7ab3c88f9f362deb34f2702ba08020555a2e23baab4ea21943c36d976a4818a (128354 B).

SCAN: `git diff | grep -inE "edge|profit|roi|dollar|18\.38|0\.119|54\.57|8\.94|78\.11|\b54\b"` over the staged diff returns matches on three kinds of lines, all exempt: (1) the substring `edge` inside `ledger`/`RESULTS_LEDGER` (confirmed `\bedge\b` and roi/profit/dollar alone return 0 hits); (2) `survival_fix1b.csv` window `ncaaw-lFZWLVzvCEs_s4374` (shift +30) prints a G351 `ratio_x=0.119938`, a ball/player pixel-span ratio, not the retracted endQ3 figure; (3) `survival_fix1b.csv` window `wHs1OssEcAw_s4462` prints a court-map coordinate range value `54.000` (a player-box pixel bound), not the retracted in-play figure. No other hits.

2026-09-08/09 finisher fix 1b: reseal by even sampling closes the B7 head-slice REJECT and both NEW GAPs (base_game_id column, archived census); PARTIAL stands on the named pair-count and shuffle-bar shortfalls.
