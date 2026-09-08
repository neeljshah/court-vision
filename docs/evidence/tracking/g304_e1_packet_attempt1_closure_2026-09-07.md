INSTRUMENT NOT VALIDATED -- attempt 1 (model locators)

Spec: [G304_spec.md](specs/G304_spec.md). This closes attempt 1 of the E1 sealed held-out packet. It measures NO registration, NO
calibration, NO tracking quality and NO prediction, and sets no ledger `passed` field. G306, G307 and G308 stay BLOCKED.

## The chain that ran

1. Sealed inventory (`b8f7ab394`, verifier fixes `a6fa18878`): 60 time-stratified rows, 30 per source, from two hash-confirmed
   native 1920x1080 broadcasts -- `wnba_01.f137.mp4` (Gateway Center Arena) and `wnba_04.f137.mp4` (Climate Pledge Arena), courts
   confirmed visually distinct. Payload seal `5806527e2d50c9830a12774e690e440dcda6a4e56fe04b933c676fd48aed14c1`.
2. Sealed extension (`346b976a3`): 75 further rows (30 wnba_01 + 45 wnba_04) drawn at a 1/3 within-bin offset, proven disjoint
   from the sealed 60. Seal `d4e7ba31...977280f3`.
3. Blind eligibility by one MODEL annotator (`gpt-5.6-sol`) over all 135 rows: Gateway Center 29 eligible (the 20-eligible
   requirement MET), Climate Pledge 34 eligible but its negative pool is 2 graphics/transition negatives short of the declared 4 /
   3 / 3 split.
4. Two blind MODEL locators over a shared 15-name landmark vocabulary -- pass 1 `gpt-5.6-sol`, pass 2 `gpt-5.6-terra`; neither is
   a human -- then batch-1 adjudication by a third MODEL, `claude-opus-5` (prereg sealed alone at `1f916f68b`, result
   `bf52f9ac2`), over the 23 eligible rows of the sealed 60.

## What batch 1 measured

Q1 NOT VALIDATED: the first pairwise distance table predates preregistration
(g304_adjudication_batch1_prereg_2026-09-07.md:112-127); no locator or adjudication headline is verified. The distance figures
previously printed here are withdrawn as unpreregistered. Packet remains 0/240 completed correspondences; G306-G308 stay blocked.
Attempt 2 (proposal-verify instrument, spec VERSION 2026-09-07b) is the live path.

### Measured burden

Spec requirement: G304_spec.md:111-115 (wall-clock annotation burden per frame). Wall time = each lane's log DISPATCHED-to-EXIT
span; per-frame burden = wall time / frames handled.

- Eligibility, sealed 60 (a3, `cx_g304e_eligibility.log` tag `g304e`, 2026-09-07T16:33:05 to 16:51:09 -05:00, matches the
  standing memo's mtime): 1084 s / 60 rows = 18.1 s/row.
- Eligibility, extension 75 (a20, no named log for this lane; self-reported in
  `g304_eligibility_ext_sol_2026-09-07.md:8`): ~2100 s / 75 rows = ~28 s/row.
- Locator pass 1, 23 eligible (a7, `cx_g304p1_locator_pass1.log` tag `g304p1b`, 2026-09-07T17:23:01 to 17:50:12 -05:00, matches
  the standing memo's mtime): 1631 s / 23 frames = 70.9 s/frame.
- Locator pass 2, 23 eligible (a3, `cx_g304p2_locator_pass2.log` tag `g304p2b`, 2026-09-07T17:23:11 to 17:31:41 -05:00, matches
  the standing memo's mtime): 510 s / 23 frames = 22.2 s/frame.

## Next

Attempt 2 is the PROPOSAL-VERIFY instrument recorded as `G304_spec.md` VERSION 2026-09-07b: landmark proposals generated
algorithmically from the in-repo line providers at native resolution, then a binary ACCEPT / REJECT by two independent model
raters with Cohen's kappa reported. Two attempts is the limit. **Human annotation of the eligible frames is the alternative and it
is a USER DECISION, not an agent one** -- it is the only path that does not rest on model raters.

## NOT VERIFIED

- All three raters are models; no human annotated or adjudicated any point.
- Arena identities are transcribed; only visual distinctness was confirmed.
- 124 of 136 batch-1 items are unresolved; the 40 eligible extension frames were never adjudicated.
- The eligibility census is one model annotator's, unreplicated.
- Whether proposal-verify does better: attempt 2 is proposed, not measured.