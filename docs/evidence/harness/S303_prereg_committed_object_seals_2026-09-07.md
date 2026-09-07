# S303 preregistration: committed-object seal verification

## Construct

This is a local, unscored harness construct. It reads no data files, does not
read or write a ledger, and does not change any feature flag.

The S303 verifier test will obtain committed artifact bytes with `git show
HEAD:<path>` when the artifact exists at HEAD. Only after `git cat-file -e
HEAD:<path>` proves that it is absent will it fall back to LF-normalized
working-file bytes.

The six explicit committed-artifact anchors are:

1. `docs/evidence/harness/S261_ingame_headline_rederive_v2_attempt2_prereg_2026-09-04.md`
2. `docs/evidence/harness/S265_preregistration_incumbent_conformal_band_sample_2026-09-04.md`
3. `docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04_attempt2.md`
4. `docs/evidence/harness/S270_attempt_1c_S82_prereg_2026-09-04_v2.md`
5. `docs/evidence/harness/S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md`
6. `docs/evidence/harness/S274_mlb_distribution_evaluator_route_prereg_2026-09-04.md`

The temporary-repository construct must commit a sealed preregistration, dirty
the corresponding working file, and prove that the committed bytes are still
selected. The fallback construct must use an uncommitted preregistration and
record that the normalized working-file fallback was selected.

## Frozen rule

For every declared artifact, the digest is SHA-256 of the exact bytes above its
seal marker. Committed bytes are never normalized. Fallback bytes are normalized
from CRLF to LF before the bytes above the marker are hashed. A mismatch is a
finding; neither the test nor this construct rewrites an existing seal.

SHA256_SEAL: 9d15650f1491bfcdebd9dee88c0b847483aa9e26745fecb697f6c894114770dc
