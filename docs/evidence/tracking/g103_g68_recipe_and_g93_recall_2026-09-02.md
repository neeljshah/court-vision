# G103 G68 tile recipe and G93 recall stop

## Result

**CLOSED AT LIMIT: source-tile checksum mismatch (0/33).** G103 implemented
the narrow, deterministic 33-tile reconstruction recipe requested for G93.
It then compared every regenerated tile from the read-only pod source clips to
the corresponding surviving G68 source-sheet tile. None matched. This is the
specification's explicit stopping condition, so G93 was not run: there is no
recall value, role table, miss-reason histogram, or judged-overlay set to
report.

The failure is material. G97 showed that an unchanged G84 render could be
byte-identical across OpenCV versions, so a tile-level checksum is a fair
durability test rather than a cosmetic requirement. The recovered source clip
does not presently reproduce the exact G68 detector input.

## Recipe and verification

The tracked [manifest](g103_recall/tile_manifest.csv) declares all 33 fixed
G84 identities across 11 clips. For each it records the source clip ID, exact
frame index, former sheet row, tile dimensions, banner construction, JPEG
quality, and SHA-256 of the decoded BGR source-sheet tile.

[`g103_g68_tile_recipe.py`](../../scripts/platformkit/g103_g68_tile_recipe.py)
pulls only those source frames from
`/workspace/nba-ai-system/data/footage_corpus/` through read-only SSH. It
resizes the decoded frame to 640x360, places it below a 24-pixel black banner
in a 640x384 BGR tile, draws the recorded `f<frame_index>` banner at `(8, 13)`
with `FONT_HERSHEY_SIMPLEX`, scale `0.3`, BGR `0,255,255`, thickness `1`, and
JPEG-encodes at quality 92. These parameters are recorded per row, rather than
being inferred at a future rerun.

The complete [checksum verification](g103_recall/tile_checksum_verification.csv)
has 33 unique `(clip, frame_index)` rows: **0/33 matches**. It is a full fixed
selection result, not a head-slice sample. Only 2,636,014 bytes of rebuilt
tiles were pulled locally for the check; neither the 66 source contact sheets
nor a full source video was committed.

Reproduce the verification after the manifest is present with:

```text
python -m scripts.platformkit.g103_g68_tile_recipe --verify
```

It exits nonzero on any mismatch and writes the complete comparison CSV. The
single focused parser test is
`python -m pytest tests/evidence/tracking/test_g103_g68_tile_recipe.py -q`.

## Consequence for G93

The protocol committed at `98b7d6974` is unchanged. In particular, G103 did
not re-choose the 12-degree angle, 12-pixel perpendicular distance, 20-pixel
endpoint extension, or fixed miss-reason vocabulary. It did not touch the G84
seed/sample manifest, candidate labels, detector values 28.0/5.0/10.0,
`line_calibration.py`, G87's 11/12 result, or any harness threshold.

Running G93 against non-identical source tiles would make its detector input
non-commensurable with G84's 11.22 percent candidate precision measurement.
The appropriate result is the checksum stop, not an unlabelled substitute
recall estimate.

## Verifier contract self-check

- A7: this memo, the recipe manifest, the complete checksum verification, the
  entry point, and its focused test all exist in this landing. No absent
  overlay or recall artifact is presented as evidence.
- B1: all 33 fixed G84 identities are named in the manifest and verification;
  none was excluded after seeing a mismatch.
- B2: additions only. No existing schema, status, reader, or field changed;
  the new CSVs have no existing readers.
- B3: no gate changed and no missing item was treated as bad evidence.
- B4: no claim, queue, or retry lifecycle changed.
- B5: no file was copied to the pod. The entry point only reads source clips
  and pulls 33 encoded tile results to the worktree.
- B6: no module was moved or retired.
- B7: verification covers all 33 frames across all 11 clip IDs, not a head
  slice.
- B8: no fit, residual, or post-hoc detection rule is claimed. The frozen G93
  correspondence protocol was not executed after its input failed to match.
- B9: the unit is one unique fixed `(clip, frame_index)` tile; 33/33 are unique.
- B10: no detector parameter, protocol value, gate, or harness threshold moved.

## Not verified

- The root cause of the source-sheet versus pod-clip mismatch is not known.
  It may be source-video provenance, frame decoding, or a historical sheet
  construction detail; this row does not select among those explanations.
- The recipe is not accepted as a durable replacement for the source sheets.
  A future row must first make all 33 checksums match.
- G93 detection recall, its visible-line denominator, per-role intervals,
  miss reasons, and eye-check overlays remain unmeasured. No detector was
  rerun for a substitute result.
