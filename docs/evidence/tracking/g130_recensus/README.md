# G130 source-first basketball recensus artifacts

This directory records a fresh source-decoded reachability census. Its source
inventory is the live basketball corpus at execution time, not the obsolete
G111 label set. `review_protocol.md` was completed before either decision pass.

On completion, this directory contains:

- `sample_manifest.json`: the global sample seed, current source metadata, and
  one random frame in every temporal stratum for every clip;
- `source_decodes/`: the exact source-decoded JPEG for every reviewed manifest
  frame;
- `contact_sheets/`: source-derived visual review sheets, grouped by clip;
- `first_pass_source_judgements.csv`: complete first-pass corner decisions;
- `rejudge_selection_manifest.json` and `second_pass_source_judgements.csv`:
  the separately seeded, shuffled 20 percent blind second pass;
- `summary.json`: direct recomputation inputs and Wilson intervals.

The rows are additive evidence only. They do not alter any threshold,
coordinate contract, rung, clip declaration, or REACH verdict.
