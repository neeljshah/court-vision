# G67 -- soccer penalty-box solvability census

Date: 2026-09-02. Gap: G67. This is the pre-registered, pure human census in
`specs/G67_spec.md`; the calibration rationale is
`CALIBRATION_STRATEGY_2026-09-02.md`. No detector was run, no solver was
written, and no pod file was changed.

## Method

All five pod-only soccer clips were decoded read-only on `config.pod`.
For every clip, `stride = total_frames // 300` and the sampled indices are
`0, stride, 2*stride, ..., 299*stride`: exactly 300 decoded frames per clip,
1,500 frames in total. Each 5-by-5 sheet has the source frame index burned
into every tile and is retained in `g67_box_census/contact_sheets/`.

Each tile received exactly one human label in
`g67_box_census/per_tile_labels.csv`:

- `BOX_SOLVABLE`: the goal line, 16.5 m line, and both box side lines of one
  penalty box are all discernible with fittable extent.
- `WIDE_NO_BOX`: a live wide pitch view, but not all four required lines.
- `NON_WIDE`: all other views.

The denominator is every sampled decoded frame, including `NON_WIDE`; it is
never conditioned on a wide-view judgment or an accepted detector output.

## Result

| clip | total frames | stride | BOX_SOLVABLE / 300 | share, Wilson 95% | wide / 300 | wide share, Wilson 95% |
|---|---:|---:|---:|---:|---:|---:|
| `soccer__soccer_AgspyOj5BPk` | 28,805 | 96 | 21 | 0.0700 [0.0462, 0.1046] | 196 | 0.6533 [0.5978, 0.7049] |
| `soccer__soccer_DdnvC6-PGYY` | 28,951 | 96 | 16 | 0.0533 [0.0331, 0.0849] | 200 | 0.6667 [0.6115, 0.7176] |
| `soccer__soccer_EKhrdU9bVZA` | 28,821 | 96 | 12 | 0.0400 [0.0230, 0.0686] | 190 | 0.6333 [0.5774, 0.6859] |
| `soccer__soccer_cKXZysISV4w` | 28,951 | 96 | 15 | 0.0500 [0.0305, 0.0808] | 195 | 0.6500 [0.5944, 0.7018] |
| `soccer__soccer_kSgNjoaqCpI_1080p` | 18,150 | 60 | 8 | 0.0267 [0.0136, 0.0517] | 190 | 0.6333 [0.5774, 0.6859] |
| **pooled** | **135,678** | -- | **72 / 1,500** | **0.0480 [0.0383, 0.0600]** | **971 / 1,500** | **0.6473 [0.6228, 0.6711]** |

The pooled box-solvability share is below the pre-registered approximately
0.10 decision point. **CLOSED AT LIMIT:** a penalty-box-corner provider would
calibrate too little of this broadcast corpus to change the harness picture;
no solver is written from this lane.

The 0.6473 pooled wide share agrees with G34's one-clip 0.6500 estimate
(Wilson 95% [0.594, 0.702]); G34's wide number was not used as this row's
denominator or as a proxy for box solvability.

## Full-resolution re-read

Seed `6702` deterministically selected 20 initially `BOX_SOLVABLE` tiles;
their full-resolution frames and result table are retained in
`g67_box_census/full_resolution_reread/` and
`g67_box_census/full_resolution_reread_results.csv`. Two of 20 tile calls
were downgraded to `WIDE_NO_BOX` after re-read (Agspy frame 864 and Ddnv frame
15,648); the per-tile table and headline counts above include those
corrections. Re-read disagreement: **2/20 = 10.0%**. This is a limitation of
the 320-pixel sheet judgment, not smoothed away.

## Environment and durability

- Pod: `config.pod`, read-only; Python 3.12.3, OpenCV 4.14.0.
- Local source revision before this evidence commit: `20791e0d7`.
- Contact sheets, label table, label summary, seed, full-resolution re-read
  frames, and re-read table all reside under `docs/evidence/tracking/g67_box_census/`.
- No artifact was written under `/tmp`; no `scp`, deploy, daemon operation,
  detector, or solver occurred.

## Verifier-contract self-check

- B1/B9: every one of the 1,500 arithmetic-stride decoded frames is present
  once in the label table; excluded sets are named labels, not removed rows.
- B2-B6: no production field, schema, caller, deployment, or module changed.
- B7: samples cover each whole clip by fixed arithmetic stride, not a head slice.
- B8: no fit or residual exists in this census.
- B10: the pre-registered approximately 0.10 decision point and all existing
  thresholds/contracts were left untouched.
- A7: every evidence path named above exists at memo time.

## NOT VERIFIED

- This is a five-clip, one-observer census, not a claim about every broadcaster
  or all soccer camera styles.
- A `BOX_SOLVABLE` label establishes visible line extent only; it does not
  establish correct role assignment, a valid homography, independent metric
  scale validation, or temporal stability.
- The 10% full-resolution disagreement rate means any later use of a
  thumbnail-based triage rule needs its own validation; this lane supplies no
  detector or solver implementation.
