# G93 Findings

## Baseline

- G93 requires a LIMIT measurement only: no detector tuning, no calibration changes, and no fresh sample.
- The required sample is G84's 33 seeded frames (seed `84092026`).
- The metric is recall among paint lines visible to the eye, overall and separately for baseline, free-throw, and lane roles, with Wilson 95% intervals and a fixed-vocabulary miss histogram.
- The committed evidence must include one overlay render for every sampled frame and be committed before reporting (A7).
- Canonical contract is `docs/evidence/tracking/VERIFIER_CONTRACT.md` (the root-level path is absent). Section A requires independent metric recomputation, non-head-slice render sampling, reader checks for touched fields, explicit-path archive landing, and evidence-path existence checks. Section B's automatic rejects will be self-checked before reporting.
- G84 measured 198/1,764 candidate-group precision (11.22%) and 0/33 all-four co-occurrence using exactly the required fixed detector call chain. G87 found 11/12 true manual paint-line inputs passed the unchanged perspective gate; G93 must not reopen or modify it.
- The worktree was already dirty in `docs/evidence/tracking/specs/G93_spec.md` before G93 work began; it is user-owned and will be preserved.
- Before candidate-overlay review, wrote the committed G93 protocol: roles, visibility denominator, 12-degree angle / 12-pixel perpendicular / 20-pixel endpoint-extension correspondence rule, and seven-value miss taxonomy. The protocol uses G84's detector chain verbatim.
- Candidate-overlay review began only after the protocol was written. The first six fixed G84 frames confirm that broadcast overlays are too cluttered for reliable endpoint marking alone, so raw 640x384 tiles will be cropped from the same read-only G68 contact sheets for the eye-marking pass; final committed renders will still include candidates and marks.
- Correction: the G68 contact-sheet tree is absent in this worktree, so raw crops cannot be regenerated. The fixed, already committed G84 overlays and their candidate endpoint CSV remain available; they will be the transparent image basis for all manual marks. No external footage/data action is authorized or needed.
- G87 supplies independent, pre-existing manual endpoints for nine overlapping G93 frame identities (five NCAA and four WNBA), including all four paint roles. These are source-image annotations, not candidate-derived truth, and can anchor the corresponding G93 visibility marks. The remaining G93 identities will be marked from G84's fixed overlays.
- G76 defines every selected `PAINT_SOLVABLE` frame as having all four physical paint lines individually discernible with continuous fittable extent. That establishes the sample premise, but G93 will retain a separate four-role visibility mark for every frame. The first eight raw-board crops exposed a layout-mapping mistake (some blank/wrong cells); those temporary outputs are discarded pending a full-board inspection.
