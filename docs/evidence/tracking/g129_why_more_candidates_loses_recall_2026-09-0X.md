# G129: why candidate-count growth can coincide with lower paint-line recall

## Baseline reproducibility first

Before either intervention was traced, the unchanged frozen G115 `measure()`
routine was executed twice in fresh `basketball_ai` Python processes after its
documented read-only rebuild of the 30 fixed tiles. Both executions returned
**25 detected / 68 visible** paint-line roles, with 120 all-role records. The
baseline is therefore reproducible on the current reconstructed inputs.

## Result

The proposed monotonicity paradox is **falsified as stated**. Neither
intervention supplies the baseline candidate set plus extra candidates:

| variant | detected / visible | LSD segments | candidate groups | change from baseline |
|---|---:|---:|---:|---|
| baseline | 25 / 68 | 2,577 | 1,581 | reference |
| G120 fragment merge | 24 / 68 | 2,577 | 1,311 | 270 fewer groups |
| G123 CLAHE | 23 / 68 | 2,993 | 1,654 | 416 more segments; 73 more groups |

G120 merges/replaces fragment spans before the frozen grouping call; it
removes candidates rather than adding them. G123 does add groups in aggregate,
but it changes the image and reruns LSD, so the post-CLAHE groups are a new
set, not a superset. A baseline true-line group can disappear while unrelated
texture groups are added. There is no need to invoke a downstream eviction to
explain either recall decrease.

The current G120 aggregate remains 24/68, but it consists of three
baseline-found roles lost and two old misses recovered. G123 consists of seven
baseline-found roles lost and five old misses recovered, yielding 23/68. The
per-line records, rather than either net count, establish the mechanism.

## Per-line traces and mechanism distribution

There are 10 `(variant, clip, frame, role)` loss records representing every
baseline-found role lost by either intervention: 9 distinct physical line
identities because the G120 and G123 variants both lose the `IB-_u4gW3ds`,
frame 20160, `lane_left` role. Full matching indices, counts, endpoint pairs,
source-fragment overlap, and each render path are in
[lost_line_traces.csv](g129_mechanism/lost_line_traces.csv).

| variant | clip, frame, role | first lost stage | per-case evidence |
|---|---|---|---|
| G120 | `IB-_u4gW3ds`, 20160, lane_left | pre-group fragment merge | groups 51 to 40; the matched span moved from `[[4,187],[4,224]]` to nearest `[[2,156],[4,224]]` |
| G120 | `IB-_u4gW3ds_1080p`, 1560, lane_right | pre-group fragment merge | groups 43 to 38; matched span `[[2,293],[341,271]]` is absent after merge |
| G120 | `wnba_01_1080p`, 12720, free_throw | pre-group fragment merge | groups 50 to 43; matched span `[[179,165],[638,198]]` becomes nearest `[[357,185],[638,197]]` |
| G123 | `IB-_u4gW3ds`, 19200, free_throw | LSD proposal generation | segments 81 to 116; groups 41 to 48; original matching group no longer matches |
| G123 | `IB-_u4gW3ds`, 19200, lane_right | LSD proposal generation | segments 81 to 116; groups 41 to 48; both baseline matching groups vanish |
| G123 | `IB-_u4gW3ds`, 20160, lane_left | LSD proposal generation | segments 84 to 97; groups 51 to 55; original matching group no longer matches |
| G123 | `IB-_u4gW3ds_1080p`, 11760, lane_right | LSD proposal generation | segments 76 to 89; groups 38 to 37; original matching groups vanish |
| G123 | `tiUvyvWOCxo`, 192, lane_left | LSD proposal generation | segments 80 to 101; groups 43 to 51; original matching group no longer matches |
| G123 | `zqBCKovJCQU`, 19200, lane_right | LSD proposal generation | segments 72 to 95; groups 53 to 56; original matching group no longer matches |
| G123 | `wnba_05`, 6912, lane_right | LSD proposal generation | segments 77 to 82; groups 58 to 57; original matching group no longer matches |

| mechanism | loss records | share |
|---|---:|---:|
| G120 replacement/fragment-group geometry change | 3 | 30% |
| G123 CLAHE changes the upstream LSD proposal set | 7 | 70% |
| greedy correspondence claim, top-N eviction, or baseline non-determinism | 0 | 0% |

The machine-readable per-role outcomes and aggregates are in
[variant_role_measurements.csv](g129_mechanism/variant_role_measurements.csv),
[mechanism_summary.csv](g129_mechanism/mechanism_summary.csv), and
[variant_summary.csv](g129_mechanism/variant_summary.csv).

## Ruled-out candidate mechanisms

- **Correspondence claiming:** ruled out. G93's `_matches` is evaluated
  independently for every `(candidate, hand-line)` pair; a role is found when
  any candidate matches. It has no one-to-one assignment, reservation, or
  greedy ordering. A shifted intervention group can fail the fixed 12-degree,
  12-pixel, 20-pixel test, but no spurious group can claim the hand line away
  from another group.
- **Cap:** ruled out for this measurement. `candidate_line_group_details`
  processes its complete sorted segment list and has no top-N or score cut.
  The only `[:16]` in `line_calibration.py` is inside downstream
  `assign_paint_roles`; the G115/G120/G123 recall runners never call it.
- **Non-determinism:** not supported by the required baseline gate: both fresh
  baseline executions were 25/68. This does not establish long-term source
  durability; G103 previously documented that reconstructed pod tiles do not
  checksum-match the historical contact-sheet tiles.

## Side-by-side render check

All 10 lost-case side-by-side renders were reviewed, exceeding the required
five. Each has baseline on the left and the intervention on the right; the
thick role-colour line is the fixed hand mark and a green baseline candidate is
a G93 correspondence match. The G120 panels visibly reduce/re-span grouped
segments, while the G123 panels show a denser but materially different LSD
proposal field around the lost marked line. The rendered decision set is
[g129_mechanism/renders/](g129_mechanism/renders/).

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g115_paint_line_recall --rebuild
conda run --no-capture-output -n basketball_ai python -c "from scripts.platformkit.g115_paint_line_recall import measure; rows,_=measure(); print(sum(r['detected']=='true' for r in rows), sum(r['visible']=='true' for r in rows), len(rows))"
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g129_more_candidates_mechanism
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g129_more_candidates_mechanism.py -q
```

The baseline-count command was run twice, as reported above. The rebuild reads
only the fixed pod frames and writes local tiles; no pod file, process, or
configuration was changed. The sole new focused test passed: `1 passed`.

## Verifier-contract self-check

- A2: independently recomputed `variant_role_measurements.csv` gives 25/68,
  24/68, and 23/68 from unique visible roles; `lost_line_traces.csv`
  recomputes 3 G120 and 7 G123 loss records, with 9 unique `(clip, frame,
  role)` identities.
- A3: reviewed all 10 paired renders, not a head slice.
- A4: 10 trace rows are 10 unique `(variant, clip, frame, role)` units; their
  9 physical-line identities are explicitly stated, including the one overlap.
- A5: the new trace CSV field names have no existing readers; the only readers
  are this new isolated writer and its focused test import. No existing field
  changed.
- A7: every named evidence path exists at self-check: this memo; the four
  CSVs; the 10-render directory contents; the isolated module; and its one
  focused test.
- B1: the denominator is every frozen visible G115 role (68); no role was
  excluded after scoring.
- B2-B6: additions only; no existing schema, reader, gate, lifecycle, pod
  deployment, module move, caller, or feature flag changed.
- B7: the entire loss decision set was reviewed.
- B8: the G93 correspondence and G120/G123 preregistered transformations were
  reused unchanged; no threshold or rule was selected from these losses.
- B9: the recall denominator is 68 unique visible `(clip, frame, role)` units,
  and the trace denominator is unique variant-line units, not reused IDs.
- B10: G93/G115 detector and correspondence values, G84 sample/seed, labels,
  `line_calibration.py`, coordinate contract, and every harness threshold are
  untouched.

## Not verified

- Historic byte identity of the current reconstructed tiles to G68 contact
  sheets; G103's checksum finding remains open, even though the current
  baseline aggregate is reproducible.
- Generalization beyond the 30 frozen frames and 68 visible roles.
- A new detector, a different contrast method, a fragment-merge change, or a
  calibration fix. This row explains the observed losses only.
- Any court-coordinate recovery, solver behavior, deployment, or feature flag.
