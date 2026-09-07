**CLOSED AT LIMIT -- source availability (attempt 2 of 2)**

ATTEMPTED (worktree a7, soccer-only by design after the attempt-1 preflight removed the tennis arm): sample 48 unconditioned retained detections from one eligible soccer run on the pod, render G273-geometry crops at two sizes, classify blind in G287's seven categories, compare the soccer (a)+(b) "on a player at all" rate against G287's committed WNBA baseline (32/72 = 0.444; graphic share 13/72 = 0.181). The lane PASSED the operational CPU/disk gate on the pod (`dd conv=fsync` 1 MiB written and removed; load15 4.27 against `nproc` 256) and then stopped at source selection. No crops, no labels, no soccer counts, no G287 comparison were created.

LANE CLOSING STATEMENT, quoted from `cx_g293_footpoint_content.log`:
> "The original soccer source is absent after pod reallocation. Per the required run-selection rule I checked the next three already-eligible soccer sources as well; all four expected footage paths are absent."
> "All four allowed soccer sources are absent, while the CPU/disk operational gate passed. With no eligible video remaining to decode, there is no honest way to create or label the required blind packet; I've recorded this as a source-availability closeout rather than inventing a measurement."
> "CLOSED AT LIMIT / NOT VALIDATED: all four eligible soccer sources are absent on the reallocated pod. No crops, labels, soccer counts, or G287 comparison were created."

It probed `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_<id>.mp4` for `Z6NTDyxcODs`, `c1mzmBGHQr4`, `dnR5C6WLJI4`, `kSgNjoaqCpI`, plus an exact-name search under `/workspace`. `G293_spec.md`'s attempt-2 rule is explicit -- stopping before the soccer numbers exist is a failed second attempt and the row is CLOSED AT LIMIT. That rule is applied here.

LOCAL SOURCE CHECK (orchestrator, this repo, `ls -l`): THREE of the four ARE present locally under `data/videos/bridge/` -- `soccer_Z6NTDyxcODs.mp4` 2,341,768,743 bytes (byte-identical to the size the spec records for the pod copy at attempt 1), `soccer_dnR5C6WLJI4.mp4` 3,373,680,742, `soccer_kSgNjoaqCpI.mp4` 2,647,890,892 (plus its bridge partial `soccer_kSgNjoaqCpI.f136.mp4`, 463,326,113 -- do not touch). `soccer_c1mzmBGHQr4` has NO local video, only `data/tracking_reports/soccer/soccer_c1mzmBGHQr4.json`. UNBLOCK PATH for a future row: local -> scp -> pod, no re-download. This attempt still closes as the spec requires; a local file on disk is not a substitute for the attempt-2 result.

A FUTURE ROW WOULD NEED: a new gap id that ships one of the three local sources to the reallocated pod, then runs the unchanged G293 method soccer-only, dispatched on `gpt-5.6-terra` so the G287 rater stays constant.

NOT VERIFIED: the seven soccer footpoint-content counts at either crop size; the (a)+(b) on-player rate and its two-proportion test against G287; the (d) graphic share; the replication answer; per-run native resolution, crop fraction, route and sampling coverage; the blind order sha; whether the local files decode or match the pod copies beyond byte size; whether the pod corpus was remounted under a different path.
