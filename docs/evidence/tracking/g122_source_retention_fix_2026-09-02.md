# G122 source-retention fix

**Verdict: ACCEPT.** The inline bridge now retains its remote source after a real cycle.

G116 established the policy history and frozen 199-table census used here; this row does not re-derive it.

The inline bridge documented `download -> scp -> track on pod -> delete local AND remote copies immediately`.

The concrete deletion was `footage_bridge.push_and_track`'s unconditional `rm -f <remote>` in `finally`.

## Premise remeasurement before change

A read-only pod stat check found all eight G116 jump-gate-eligible source keys in `data/footage_corpus/` (8/8).

The same check reported 334T free on `/workspace`.

## Change

`scripts/platformkit/footage_bridge.py` now moves the inline remote source from `data/footage_bridge/` to `data/footage_corpus/` in the existing cleanup position.

If a same-name corpus file exists, it is untouched and only the duplicate staged upload is removed.

The `.part` then atomic-rename contract in `push_staged`, plain-`.mp4` completion rule, harness thresholds, coordinate contract, rung ladder, and verdict logic are unchanged.

`track_daemon.py` is not touched.

## Loop avoidance

The daemon watches `data/footage_bridge/` for plain `.mp4` files.

A successful inline source moves into `data/footage_corpus/`, outside that watched stage, so it cannot be claimed again.

The duplicate-name branch leaves the existing corpus file intact and removes only the temporary staged duplicate.

## Real-cycle verification

Witness: `g122_mlb_retention_10893dca`.

Its complete 342,144,561-byte source reached `data/footage_bridge/` and the inline command `python adapter_run.py baseball ... g122_mlb_retention_10893dca` was observed running.

After the inline cycle, a read-only pod stat found `data/footage_corpus/g122_mlb_retention_10893dca.mp4`, exactly 342,144,561 bytes, and found no same-name file in `data/footage_bridge/`.

The newly written tracking CSV has one physical row (header only, zero emitted data rows). This is not a tracking-quality claim: the acceptance metric is source survival after the real tracking invocation.

The local bridge stage no longer contains the witness source.

The post-cycle read-only source check found every G116 jump-gate-eligible source key present again: 8/8.

## Scope boundary

Backfill is out of scope.

The 126 G116 census tables with absent sources remain permanently unverifiable by source re-check under this row.

G96 and G114 established that reacquisition can yield different content or no source.

## Focused test

Exactly one new per-file regression test was added and only it was run:

`python -m pytest tests/platformkit/test_footage_bridge_retention.py -q`

Result: `1 passed in 0.54s`.

## VERIFIER_CONTRACT self-check

- **A1:** The lane ran its sole new per-file test. The contract assigns a master-side rerun to the independent verifier; this worktree did not write to master.
- **A2:** The post-cycle headline was recomputed from direct pod `stat` and `find` results: the named witness exists in the corpus and is absent from the stage.
- **A3:** No render decision set applies.
- **A4:** The gate measurement names eight distinct source keys; the witness is one distinct game id.
- **A5:** Scoped readers found only the bridge control flow and its legacy unit assertions. The two assertions encoding deletion were updated; no schema field changed.
- **A6:** The explicit-path commit and independent verifier archive landing/ledger/register steps are pending the final worktree commit. No master tree is modified by this lane.
- **A7:** Before reporting, this memo, G116, its `table_source_census.csv`, the G122 spec, the verifier contract, and the focused test path will be existence-checked.

- **B1:** Clear. The 8/8 denominator is the complete named G116 gate set, and no item is excluded.
- **B2:** Clear. No schema field or status was renamed or removed.
- **B3-B4:** Clear. No gate, claim, retry, or queue behavior changed.
- **B5:** The spec expressly permits this pod deploy. It occurred only after the local focused test and used atomic replacement; no daemon, keeper, bridge lane, or other process was killed or restarted.
- **B6:** Clear. The existing deletion-behavior tests were updated; no module was retired.
- **B7:** Not applicable; no render or row sample is a headline metric.
- **B8:** Clear. No fitted residual is claimed.
- **B9:** Clear. The metric is one named source file after one named real cycle, not recycled track ids.
- **B10:** Clear. No harness threshold, coordinate contract, rung ladder, or verdict changed.

## NOT VERIFIED

- Historical source backfill or byte-identical recovery of the 126 absent G116 sources.
- Tracking quality for the witness: its CSV contains zero emitted data rows.
