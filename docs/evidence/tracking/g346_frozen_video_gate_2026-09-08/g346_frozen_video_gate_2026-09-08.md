VERDICT: PARTIAL -- acceptance n bar (60 valid frames/section) does not hold: reruns decode 57-60.
Spec: `docs/evidence/tracking/specs/G346_spec.md`. Self-check: `VERIFIER_CONTRACT.md` A, B, Q.
Machine: prep local `nba-track-a10`; fix 1b census shipped+run on pod 213.192.2.88 scratch `/workspace/wt/a10/g346/out_fix1b/` (CPU only, nice -n 19, read-only corpus+ledger), per B5 note.
Prereg sealed before scoring (unchanged): `.../preregistration.md`, SHA-256 `9c8bfb7b...c0b4f` (Q1).
## Premise (re-checked, unchanged)
`footage_content_gate.py:89-121` (`sample_clip`) samples surface/border/HSV-cut only; `:124-134`
(`decide`) consumes only those -- no inter-frame delta or bytes-per-frame check anywhere. TRUE.
## Tests (each alone, `--basetemp` under the worktree, conda `basketball_ai`)
`test_g346_footage_liveness.py` 5/5 | `test_footage_content_gate.py` full file 3/3 | `test_loc_rail_scope.py` 1/1 (census script now 192 LOC) | NEW `test_g346_footage_census.py` 3/3 (absent ledger raises; valid_frames < requested recorded; a rows<50 ledger-only source is ABSENT_FILE).
## Census (sealed rerun; `sealed_sections.csv`, `ledger_extract.csv`, `code_identity.csv`)
n=57 corpus sections | 7 FROZEN | 50 LIVE | 0 unreadable | bytes/frame p10/p50/p90 = 1138.75/6180.49/17389.28 | delta p10/p50/p90 = 3.00/29.99/54.12.
## G338 sections (both present, not rotated out; corrected valid_frames)
| section | bytes/frame | delta | near-ident share | valid_frames | verdict |
|---|---:|---:|---:|---:|---|
| eurocup-qrWmO434a0k_s90 | 1208.17 | 5.33 | 0.821 | 57/60 | FROZEN |
| XCaGht2GmPg_s6720 | 1150.23 | 3.07 | 0.125 | 57/60 | FROZEN |
Both reproduce FROZEN on the bytes/frame cue, byte-identical to the prior run. 48 of 57 corpus sections decode below 60 valid frames (range 57-60): the failing acceptance-n item.
## Corpus rotation (sealed at census time; a live rotating queue, G335/G327)
57 sections now vs 56 before: 2 rotated OUT (`ncaa_basketball__VEUJpELt_yA_s1212`, `_s3456`), 3 NEW (`acb-_a72WK36Its_s6520` [now FROZEN], `cba-FaMCJR6tFm0_s5062`, `lnb-ouDVA0vM20g_s1379`). The
prior 6 FROZEN sections all reproduce FROZEN; the 7th FROZEN is the new arrival.
## Ledger cross (artifact-limited: recomputable from `ledger_extract.csv` alone, no live re-read)
Ledger `data/tracking/track_daemon_ledger.jsonl` (765,524 bytes, sha `382210db...c0434e`), sealed at extraction. 57 of 57 corpus sections carry a ledger entry (`ledger_entry_present`=True); 0 of 7 FROZEN sections produced rows>0 (matches G338's "zero person rows"). 68 rows sealed in the extract (57 corpus-matched + 11 ledger-only), 66 of 68 with rows<50.
## NEW GAP fix: ledger-only rows<50 sources with no corpus file (11, enumerated ABSENT_FILE)
game_ids: `0022400909`x2, `0022500081`x3, `atl_ind_2025`, `bos_mia_2025`, `mia_bkn_2025`, `nba_highlights_gsw`, `phi_tor_2025`, `sac_por_2025`. 0 of 11 files exist in this corpus scan.
## Resolution x game confound (reconfirms G338: 1280x720 = one game)
| resolution | n sections | n distinct games |
|---|---:|---:|
| 640x360 | 10 | 4 |
| 1280x720 | 4 | 1 |
| 1920x1080 | 43 | 31 |
## PROPOSED feeder hook (orchestrator applies; not applied here; unchanged from prior lane)
```python
verdict = footage_content_gate.screen_fail_open(local, item.get("sport", ""))  # footage_bridge.py:712
if verdict.metrics.liveness and verdict.metrics.liveness.verdict == "FROZEN":
    local.unlink(missing_ok=True)
    return {"outcome": "skipped_frozen", "candidate": item}
```
## Corrections (fix 1b, 2026-09-08)
Per codex-sol REJECT: added `valid_frames`/`ledger_entry_present` columns; an absent ledger is now a hard `FileNotFoundError` (was a silent empty dict); sealed `ledger_extract.csv` (68 rows, ledger path/bytes/sha256) so the cross needs no live pod read; enumerated the 11 rows<50 ledger-only sources with no corpus file as ABSENT_FILE rows (the NEW GAP). Line 1 moved DONE -> PARTIAL: named
sources decode 57/60 valid frames, not 60, and 48/57 sections fall short of the requested 60 -- an honest property of real decode near clip boundaries, not a bug; census shape is otherwise unchanged.
EYE CHECK: skipped (time; optional per spec). NOT VERIFIED: why 48/57 sections decode below 60 frames (suspect end-of-clip seek misses); why most sections carry thin ledger rows regardless of
liveness; one rotating-corpus snapshot; a static empty-court LIVE section is still useless (G341's view-class territory).
2026-09-08 lander: ACCEPT (codex-sol, contract A/B/Q, no corrections); NEW GAPS recorded in the ledger (raw pod videos not locally re-decodable; memo nested under the artifact directory rather than the spec's root path; linked-worktree index.lock).
Wall time: pod census 2026-09-08 19:41-19:58 UTC (~17 min, fix 1b rerun).
SHA-256 (LF-normalized): census.csv bebb1e7c6dafc2a2cc88bd464188dfacc70e483df7469074590590e12b1640fc | resolution_games.csv c1fb5671cab7db660feb29c0c44523739cfec0d73ffc3324d6af2052ed3e16c4
| sealed_sections.csv c4f3b9fb8f4344a146f7e5d1de75a79de74da05e84fb5e58a416b3ea749c4305 | code_identity.csv e476a619ce311283dc6ee6a76074a7effaf650170056d4a9906f8d963c4e37e5
| ledger_extract.csv 76225527e9b87bb918b73ea3f87ed938dc4853831f39ebaecf3c0b4a47c61975
