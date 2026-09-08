# G304 adjudication batch 1 -- two-locator agreement and adjudication

Scope: the 23 ELIGIBLE rows of the original 60-row sealed inventory (14 Gateway Center Arena, 9 Climate
Pledge Arena). Prereg `docs/evidence/tracking/g304_adjudication_batch1_prereg_2026-09-07.md`, seal
`6c091d189c2721807a97b600d99087a3572277d2c52d72a50d0ac605eeff9892`, committed alone at `1f916f68b`
before any adjudication decision. Inventory identity: manifest payload SHA-256
`5806527e2d50c9830a12774e690e440dcda6a4e56fe04b933c676fd48aed14c1`. This batch measures NO
registration, NO calibration and NO tracking quality. Raters: pass 1 `gpt-5.6-sol` (MODEL), pass 2
`gpt-5.6-terra` (MODEL), adjudicator `claude-opus-5` (MODEL) -- no human annotated or adjudicated any
point. G280b/G291 measured crop judgements to be rater-sensitive, so a model adjudicator does not turn
two model annotations into truth. **Agreement alone never establishes correctness.**

## Agreement (denominators named)

| arena | eligible frames | items | in both passes | within 4 px | share | median px | p90 px | max px | pass1-only | pass2-only |
|---|---|---|---|---|---|---|---|---|---|---|
| Gateway Center Arena | 14 | 100 | 65 | 0 | 0.0 % | 207.9 | 583.3 | 694.4 | 16 | 19 |
| Climate Pledge Arena | 9 | 36 | 13 | 0 | 0.0 % | 437.3 | 761.3 | 829.7 | 0 | 23 |
| both | 23 | 136 | 78 | **0** | **0.0 %** | -- | -- | -- | 16 | 42 |

**0 of 78 co-located pairs fall within the 4 px threshold**, so all 136 items were adjudicated. An
item is one (row_id, landmark_name) pair present in either pass.

## Adjudication outcomes (136 items)

`agreed` 0 (no pair within 4 px) | `pass1` 12 | `pass2` 0 | `both_wrong` 65 (landmark visible, neither
point on it) | `unidentifiable` 59 (named point not locatable in that frame). The 12 resolved items are 9 free-throw-line / lane corners in Gateway and 3 midcourt-line x
far-sideline points in Climate Pledge, all from pass 1, with an adjudicator offset of 4-22 px from
the painted marking. Pass 2's coordinates are near constant across frames that pan (`LANE_BASE_R`
x = 816-827 on seven different Gateway frames), which is why it resolves nothing. Per-item outcomes,
coordinates, distances and reasons: `docs/evidence/tracking/g304_e1_landmarks_batch1_2026-09-07.csv`.

## E1-ready frames (>= 6 resolved landmarks across >= 3 structures)

| arena | E1-ready | short | needed by the packet | best frame |
|---|---|---|---|---|
| Gateway Center Arena | **0 / 14** | 14 | 20 | 2 resolved, 2 structures (`wnba_01_17`) |
| Climate Pledge Arena | **0 / 9** | 9 | 20 | 1 resolved, 1 structure |

Every Climate Pledge frame carries only 4 annotated vocabulary names, so it cannot reach 6 regardless of
adjudication. Frame table: `docs/evidence/tracking/g304_e1_frames_batch1_2026-09-07.csv`. No frame was
dropped: all 23 stay in the output with their resolved and structure counts.

## NOT VERIFIED

- All three raters are models, not humans; rater sensitivity is measured (G291), not assumed.
- 124 of 136 items are unresolved. **Unresolved labels mean INSTRUMENT NOT VALIDATED -- they are NOT
  omitted frames and NOT successful abstentions.**
- The 12 resolved coordinates carry an adjudicator offset of about 4-22 px against the painted
  marking, the same order as the packet's own `p90 <= 12 px AND max <= 24 px` bar; they are not
  established ground truth.
- "Sits on the named landmark" was read as within the spec's 24 px max tolerance. No bar was moved: the
  4 px threshold, the 6-landmark / 3-structure rule and the frame-good rule are quoted byte-identically
  from the spec and the sealed manifest.
- Arena identities are transcribed. The two courts look plainly different by eye (dark court with blue
  apron vs light hardwood with green apron) but venue identity is not established.
- The pairwise distance table was computed before the seal (disclosed in prereg section 11); no
  adjudication decision predates it.
- Batch 1 covers 23 of the 40 eligible frames the packet requires. The extension batch is not
  adjudicated here and no packet-level verdict is claimed.
- This batch measures no registration, no calibration and no tracking quality, and does not translate
  into any ledger `passed` field. G306-G308 stay blocked.
