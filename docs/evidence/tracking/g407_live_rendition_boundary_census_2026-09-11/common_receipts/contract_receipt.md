# G407 inherited common-contract receipt

- Premise step 0 measured from the pod, not from the brief: activation boundaries read from `/workspace/feeder/relaunch.log`, digests of the feeder, discovery, ledger and queue stores sealed in `ops_snapshot.json` at census UTC.
- Whole-set population: every terminal attempt in the sealed epoch window, failures and thin sections included; repeat attempts suppressed to the earliest terminal ORIGINAL attempt.
- Retention: all 88 sources that still existed were copied off-pod before any derived table was published, then rehashed and decoded independently; 88 of 88 digests match and 88 of 88 probes agree. Sources the quota guard had already pruned stay UNKNOWN rows.
- Identity: 12 producer assets hashed read-only; all 12 mtimes precede both the daemon start and the window start, so the ORIGINAL producer identity holds across the whole window.
- Bounding: every derived table is bound either to the sealed centered two-second native-PTS interval or to the section's admitted span; overruns are retained separately in the traces.
- UNKNOWN is never scored as zero: 33 pruned sources, 10 sections without a reconstructed schedule and 0 empty-denominator held shares are all carried as explicit UNKNOWN rows.
- No daemon restart, no feeder change, no flag flip, no registry write, no force flag, no full-suite pytest, no deletion of a file this row did not create.
- Reproduction: two fresh processes regenerate every delivered table and card from delivered bytes; this is arithmetic and render reproduction only.
- Vocabulary: field-aware scan over every delivered record and every delivered text artifact returns zero non-opaque hits; patterns are built from character codes and only indices are emitted.
