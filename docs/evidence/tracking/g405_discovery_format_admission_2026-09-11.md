VERDICT: DONE -- 30/30 sources admitted by the LIVE discovery gate probed at discovery time; 11 YES / 19 NO / 0 UNKNOWN; 30-only admission NOT supported; the 30 fps preference with 60 fps fallback is retained.

# G405 discovery format admission
Sealed protocol `g405_discovery_format_admission_2026-09-11/prereg.md` (SEAL 4bceb8457a4cf4a43bb08969610f69c446122c391e9071ba61524fad5a073097, sealed alone at cf437c7f9).
## Fix 1c (2026-09-11, after codex-sol REJECT x2 of 3a9258a69 and ed876f9b3)
ACCEPTANCE-1/B10/Q3: the gate now IS the archived live recipe -- `seen()` = ledger ids | sources.txt ids (discover.log recorded, never gated) and MAX=30 applied RUN-WIDE in the
live order of operations, so no id is excluded that the live run would admit. The exact pre-run gate membership is archived (`seen_set.jsonl`, the NEW GAP). Q6: every scan
receipt now emits opaque `pattern_<i>` indices instead of the token text. Discovery was rerun, 30 redrawn and all 30 reprobed; the two superseded attempts are retained
unmodified under `att1_ungated/` (ungated draw) and `fix1b_strict_gate/` (stricter-than-live draw). Only this live-recipe gate counts; neither archive is a current number.
## PREMISE step 0 -- NOT FALSIFIED (before-condition rerun 2026-09-11T18:09:45Z, BEFORE discovery and probing)
`/workspace/feeder/discover_sources.py` (sha256 00504c02ae66c2.., unchanged since attempt 1) writes a literal fmt at line 54, gates at line 53 `if not vid or vid in S or vid in
DENY or dur<2400: continue`, builds `S` at lines 29-41 from the ledger and `sources.txt` only, and breaks on `added>=MAX` at lines 51 and 56; `discover_loop.sh:3` passes MAX=30.
Rerun output: `discover_sources_probe_calls 0`, `queue_fmt_values_other_than_270 0`, no `*format*` / `*rendition*` store in `/workspace/feeder/`; no discovery-time rendition
evidence exists for ANY source, so not for >= 30. Queue paths/fields: `sources.txt` = `sport tag ytid fmt dur`; ledger `game_id` = `<tag->?<ytid>_s<offset>`; `discover.log` =
`NEW <sport> <tag> <ytid> <dur> <title>`; deny list `deny.txt` (1 id). Ordering: premise 18:09:45Z -> discovery 18:09:53Z-18:11:47Z -> draw frozen -> first probe 18:13:07Z ->
last probe 18:21:52Z (`premise_snapshot.json` d251fa2b5ec7ff.., `discovery_config_hashes.json` 90c6ebb48ea18b.., `runtime_receipts/premise_raw.txt` 3ef41236584eb8..).
## Method as executed
Bounded discovery-only pass on the pod 18:09:53Z-18:11:47Z, 27 frozen queries x ytsearch15, no download, no enqueue: 405 rows returned, every one archived with its gate verdict
(`discovery_population_all_returned.jsonl` 6e2c33143f40bf..). Replaying the live gate in the live order removed 148 seen ids and 31 rows under 2400 s; the RUN-WIDE cap was
reached at admitted=30 inside query 14 of 27, and the 196 rows returned after it are marked `after_run_wide_cap_not_reached_by_live_run` -- the live recipe would never have
seen them. Queries after the cap were still searched, for the archive only; they cannot change the admitted set. Admitted population = 30 rows / 30 unique ids
(`discovery_population.jsonl` 93071d6c9e3d63..). Seen set archived id-by-id: 304 ledger + 32 `sources.txt` = 311 live-seen union, 1 deny, plus 11 discover.log-only ids that
fix 1b wrongly excluded and this attempt leaves ELIGIBLE (`seen_set.jsonl` 64d1f582eac86a..). Because the live cap admits exactly MAX=30, N=30 and the sealed formula
floor(j*(N-1)/29+0.5) maps j -> j: the draw IS the whole admitted population, so every source the live run would have enqueued is probed (`draw.csv` 1014b2e225b8fd..,
0 duplicates, 0 replacements, shortest drawn source 4079 s). Per source: one `yt-dlp -F` listing (120 s, one attempt) and one `yt-dlp -J --skip-download` metadata request
(60 s, one attempt), 7 s apart; 60/60 runs returncode 0, 0 timeouts, 0 retries, 111.2 s tool time. Tool identity: /usr/local/bin/yt-dlp 2026.08.19 sha256 9f52a4db6862cf..,
python3 3.12.3, pod 213.192.2.120, helper `g405_pod_probe.py` sha256 34c954ac5c6c48... Metadata was redacted of `url`/`fragments`/`http_headers`/`manifest_url`; pre/post-
redaction digests are in `runtime_receipts/probe_receipts.json` (b6918229c0ff17..) and, counts-only and URL-free, in `probe_receipts.csv` (81c605b7295a87.., 60 rows). All 60
raw listing/metadata files were verified byte-identical between pod and PC by sha256 after transfer.
## Result over the full planned denominator of 30
| compatible_30fps | n | share of 30 |
|---|---|---|
| YES (HLS + h264 + height 720-1080 + fps 29-31 bound by BOTH inventories) | 11 | 0.3667 |
| NO (both inventories complete and excluding one) | 19 | 0.6333 |
| UNKNOWN | 0 | 0.0000 |

Probed denominator 30, known denominator 30. Buckets: 720p30 11, 1080p30 11, 720p60 1, 1080p60 0; per-query breakdown in `summary.json` (9b06b66b52fe70..).
Source fps of the HLS h264 720-1080 renditions: 25 fps x17, 30 fps x11, 60 fps x1, none x1 (`availability.csv` 8acf4b0f19eea2..).
The cohort is what the live cap admits, not a balanced sample of the query list: 14 of 30 came from one competition query and 12 from a second, because the run-wide cap stopped the live recipe at query 14. That is the live admission behaviour, and it is a limit on generalising these shares to the whole searchable supply.
## Decision rule as sealed
30/30 known YES is the only branch that supports proposing 30-only admission. Measured 11/30 YES with 0 UNKNOWN, so the recommendation is UNCHANGED: keep the 30 fps preference
with the 60 fps fallback. Projected loss under 30-only: 19 of 30 proven NO, 0 UNKNOWN. This is a user policy input, not an automatic admission change; nothing was applied.
## Measured correction to the itag assumption
`common_receipts/measured_itag_table.txt` (e3f0523f256501..): over the listing inventories itag 270 was 1920x1080 HLS at 25 OR 30 fps on the 22 sources that listed it, and
itag 232 was 1280x720 HLS at 25 OR 30 fps on 28 -- a numeric id fixes neither fps nor the verdict, as the seal requires; each source carries ONE source fps shared by all its
renditions. `feeder_pod.sh` is unchanged since fix 1b (sha256 96f897fed3fe04..); the fmt gate line 127 and probe bar line 179 are untouched and this row applied nothing.
## Checks
Eye review: all 30 paired listing/metadata/sidecar cards opened in even draw order, incl. every empty-qualifying-set source (`eye_index.csv` f953c4852170e2.., `cards/`); an
independent regex recomputation over the raw `-F` bytes, not the shipped parser, agrees 30/30 (`common_receipts/eye_recompute.txt` 418543815ca41a..). Repeats: two fresh-process
rebuilds of all 8 tables and 30 cards from saved bytes, identical=true, returncode 0 (`repeats.json` 255b1db952a62d..); no network probe was repeated, so this proves parsing
repeatability only, never stable future availability. Q6 scan over 355 text artifacts incl. every raw probe output, both retained archives and `RESULTS_LEDGER.md`: 0 owned/current-row hits;
shared ledger has 26 opaque pattern_2 hits (pre-existing rows), counts and opaque `pattern_<i>` indices only (`common_receipts/q6_scan.json`); the two archives' own scan receipts were regenerated in the same opaque
form. `SHA256SUMS` covers every file except itself with its byte domain on line 1.
Test: `python -m pytest tests/platformkit/test_g405_discovery_formats.py -q` -> 21 passed. Live queue and selector untouched: `sources.txt` was read and never written, feeder
pid 3780738 ran throughout; no restart, flag, registry write, download, decode or enqueue. `discovery_queue.jsonl` (530cb77be1c50a..) is an additive UNUSED export; every row
keeps its inherited `ytid`, `dur`, `sport`, `tag`, `fmt`, `title` beside the new fields and carries its `raw_inventory_digest`; no consumer reads it. `PROPOSED_g405_discovery_probe.diff` is reviewable, applied nowhere, not a validated fix.
## NOT VERIFIED
Actual downloadability of any listed rendition; that a probed fmt survives to fetch time; any future discovery population; tracking quality of any source; any effect on the
G401 cap loss (16/34) -- G401's 29/30 mechanics failure and single-probe basis problem stand unchanged and this census does not validate its diff. Nothing is claimed about the
196 rows the run-wide cap put out of the live recipe's reach, and the 11 YES / 19 NO shares are this admission cohort's, not the searchable supply's.
