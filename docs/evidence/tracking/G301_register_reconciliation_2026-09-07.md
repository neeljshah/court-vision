# G301 -- tracking register reconciliation (2026-09-07)

STATUS: DONE. `docs/evidence/tracking/TRACKING_GAPS_2026-09-01.md` diff is 129 insertions / 6 deletions.

## What was wrong

Two separate drifts, both from the same cause -- the register row is written by hand at landing time and
nothing ever checked it:

1. **Stale OPEN allocation rows.** G193-G197 all landed on 2026-09-03 but their allocation rows still read
   `OPEN -- allocated 2026-09-03`. G193, G194 and G196 additionally had a SECOND, correct result row a few
   lines below, so the register contradicted itself; G195 and G197 had only the stale row.
2. **No register block at all for G198-G299.** 111 ids in that range have a landing commit and/or a memo on
   disk and had no row here. This is the whole G24x-G29x era.

## Changes (every row changed, exhaustive)

### A. Status cell rewritten in place (5 rows; only the last cell touched, line endings preserved)

| Gap | line | new status |
|---|---|---|
| G193 | 90 | DONE -- LANDED ae9ecf7f0; `g193_route_determinism_with_tuner_off_2026-09-03.md`; superseded by the G193 result row below |
| G194 | 94 | DONE -- LANDED 1537a23d2; `g194_which_M1_2026-09-03.md`; superseded by the G194 result row below |
| G195 | 100 | DONE -- LANDED 141bd294f; `g195_cv2_rng_route_determinism_2026-09-03.md`; no separate result row exists |
| G196 | 104 | DONE -- LANDED 218502d10; `g196_homography_from_labelled_corners_2026-09-03.md`; superseded by the G196 result row below |
| G197 | 108 | DONE -- LANDED 93baf7587 (gating field moved to `coverage_attempted_frames_pct`); `g197_harness_coverage_denominator_2026-09-03.md` |

### B. Rows ADDED in a new block `## G198-G299 reconciliation register` at the end of the file (111 rows, id order)

    G198 G199 G200 G201 G202 G203 G204 G205 G206 G207 G208 G209
    G210 G210B G211 G211B G212 G213 G214 G215 G216 G218 G219 G219B
    G220 G220B G220C G221 G222 G223 G225 G226 G226B G226C G228 G231
    G232 G233 G233B G233C G233D G234 G235 G236B G238 G239 G242 G243
    G243B G243C G244 G245 G246 G247 G248 G249 G250 G251 G252 G253
    G254 G255 G256 G256B G257 G258 G259 G260 G261 G262 G263 G264
    G265 G266 G267 G268 G269 G270 G271 G272 G272B G273 G274 G275
    G276B G277 G278 G279 G280 G280B G281 G282 G282B G283 G284 G285
    G285B G286 G287 G288 G289 G290 G291 G292 G293 G294 G295 G296B
    G297 G298 G299

### C. Header

`NEXT_GAP_ID: G300` -> `NEXT_GAP_ID: G304`. G300 (ledger repair), G301 (this row), G302 (amateur-vs-resolution
attribution, a5) and G303 (production-resolution recall, a12) are allocated by this session; G304 is the next
free id. One counter, one holder: this session is the holder.

## Method and its limits

An id counts as landed when a git-log subject starts with it (`^G[0-9]+[a-z]?`) or a memo matching
`docs/evidence/tracking/<id>_*.md` exists. The landing sha is the last commit touching that memo, falling
back to the subject-leading commit. Sport is taken from the id's `RESULTS_LEDGER.md` row where one exists,
else `see memo`. The Finding cell is the landing commit subject with its leading id stripped.

NOT VERIFIED:
- **No memo body was read and no finding was re-verified.** Every added Status cell says so in the cell
  itself. These rows record that the id landed and where its evidence is; they are not adjudications.
- Ids in G193-G299 with neither a landing commit nor a memo were left exactly as they were (untouched, and
  none is silently promoted to DONE).
- The landing-sha heuristic can name a follow-up commit that only edited the memo, rather than the original
  landing, when a memo was corrected after landing.
- The 111 rows were generated mechanically; the Finding cells are commit subjects written by the landing
  verifier, so they inherit whatever that subject claimed.
