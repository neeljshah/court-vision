# G220 amateur footage acquisition - 2026-09-04

This memo follows [the tracking verifier contract](VERIFIER_CONTRACT.md), including its section-B self-check. G220 is acquisition and classification only. No `src/` file or `footage_bridge.py` file changed; no tracking route, queue, daemon, adapter job, keeper, watchdog, or bridge supervisor was started, stopped, restarted, or otherwise changed. No footage was uploaded to the pod: copying a file there before acceptance would violate B5.

## Premise and pod observation

G216 is landed at `docs/evidence/tracking/g216_local_staging_concurrency_2026-09-03.md`. Its conclusion is that local staging did not remove the route's concurrency collapse, so the former G220 hold is lifted. This row did not treat the permanent `track_daemon` and `adapter_run` residents as a blocker and did not wait for them.

The G220 acquisition began at `2026-09-04T04:37:37Z`. Its lightweight load observation was: load averages `20.92, 24.75, 31.06`; GPU `0 percent, 354 MiB / 24576 MiB`. The only pod writes were the required, temporary 4 MiB `dd ... conv=fsync` probes. `df` was not consulted. The authoritative `du -sm /workspace/nba-ai-system/data` snapshots appear in the per-candidate table.

## Construct and guarded outcome

The construct is exhaustive: exactly the six reviewed YouTube IDs named in G220, with no substitution. For every ID the runner reused the bridge's `plan_section`, cookie path, first reviewed high-resolution format rung, section syntax, height probe, SSH configuration, and the existing content gate module. It requested one 16-minute, cookie-backed `b[height<=1080][height>=720]` section and set a 30-second command and 20-second socket bound so a resolver failure is recorded rather than parked. All six requests returned `Requested format is not available`; no file was produced. The actual height and resolution are therefore `not acquired`, not silently accepted as 360p.

| ID | Planned 16-minute section | Rung / actual height | Outcome and bytes | Pre / post dd probe; `du -sm` MB | Content gate and rubric |
|---|---|---|---|---|---|
| `jh3fnwMi7dM` | `00:10:00-00:26:00` | `b[height<=1080][height>=720]`; not acquired | unavailable: requested format unavailable; 0 B | 4,194,304 / 4,194,304 B; 31,012 / 31,013 | not run: no clip; no five-frame classification |
| `qpZfGp_fScU` | `00:10:00-00:26:00` | `b[height<=1080][height>=720]`; not acquired | unavailable: requested format unavailable; 0 B | 4,194,304 / 4,194,304 B; 31,013 / 31,014 | not run: no clip; no five-frame classification |
| `1MwO3CDkeeM` | `00:04:38-00:20:38` | `b[height<=1080][height>=720]`; not acquired | unavailable: requested format unavailable; 0 B | 4,194,304 / 4,194,304 B; 31,014 / 31,014 | not run: no clip; no five-frame classification |
| `3asBuhRd_LI` | `00:04:25-00:20:25` | `b[height<=1080][height>=720]`; not acquired | unavailable: requested format unavailable; 0 B | 4,194,304 / 4,194,304 B; 31,014 / 31,014 | not run: no clip; no five-frame classification |
| `lAs8JaoWNwg` | `00:10:00-00:26:00` | `b[height<=1080][height>=720]`; not acquired | unavailable: requested format unavailable; 0 B | 4,194,304 / 4,194,304 B; 31,015 / 31,016 | not run: no clip; no five-frame classification |
| `XwpLBtt1G2g` | `00:09:40-00:25:40` | `b[height<=1080][height>=720]`; not acquired | unavailable: requested format unavailable; 0 B | 4,194,304 / 4,194,304 B; 31,016 / 31,017 | not run: no clip; no five-frame classification |

The running transfer total is **0 B / 4,000,000,000 B**. All twelve probes completed at exactly 4,194,304 B. The changing `du` values are shared-pod observations, not G220 footage writes. Cleanup freed **0 B** because `--no-part` left no `.part` file. The complete machine-readable record is `g220_amateur_footage_acquisition_2026-09-04_records.json`.

`footage_content_gate.py` was not callable because every request produced no local clip. Had a clip existed, its verdict would have been an ingest decision only and **must never touch a metric denominator**, as its module docstring requires.

## G213 comparison and classification

No acquired clip means no source frame exists to seek with `ffmpeg`, so there are zero new downscaled frames and zero new visual labels. The required five evenly-spaced-frame protocol was not applicable to any unavailable candidate. G213's rubric is retained unchanged: camera style, production tier, overlay, surface visibility, surface appearance, and lighting. If frames had existed, their classification would have been single-labeller eye judgements with no second labeller; there are no labels here to overstate.

G213's exact zero-representation list remains unchanged:

- Handheld game-camera footage.
- Fixed **single-camera** game footage. Tennis is a multi-camera broadcast that
  happens to use a fixed-wide primary play view, not a continuous single-camera
  source.
- Amateur/high-school direct field/court camera acquisition. The one
  amateur/home-produced item is a desktop-commentary screen capture, not an
  amateur game camera.
- Graphics-free footage.
- High playing-surface visibility under the stated typical-frame rubric.
- Dim-gym or otherwise visibly poor-lighting footage.
- Visibly non-standard physical playing surfaces. WNBA 02 supplies one unusual
  court colour treatment only; its markings and physical court remain standard.

| G213 zero category | Before G220 (n=13) | G220 additions | After G220 |
|---|---:|---:|---:|
| Handheld game-camera footage | 0 | 0 | 0 |
| Fixed single-camera game footage | 0 | 0 | 0 |
| Amateur/high-school direct field/court camera | 0 | 0 | 0 |
| Graphics-free footage | 0 | 0 | 0 |
| High playing-surface visibility | 0 | 0 | 0 |
| Dim-gym or visibly poor-lighting footage | 0 | 0 | 0 |
| Visibly non-standard physical playing surfaces | 0 | 0 | 0 |

No missing category closed. This is a full, honest G220 outcome: the reviewed high-resolution section tier was unavailable from this environment, so the corpus remains without an amateur game camera. No tracking conclusion follows.

## Verifier self-check and NOT VERIFIED

Section B self-check: B1 has no metric; B2-B4 change no schema or gate behavior; B5 made no pod deployment; B6 moves no module; B7 has no acquired render set; B8 fits no model; B9 has no denominator; and B10 changes no threshold. Q does not apply because G220 is not an S-row and makes no scored claim. The results-ledger line below is this row's register entry. Every named evidence path exists at commit time.

Not verified: that any reviewed candidate is currently playable at another quality tier; a 720p-or-better clip or its actual dimensions; any content-gate verdict; any G213-rubric label or inter-rater agreement; any future corpus membership; and any tracking, detection, calibration, or other system outcome. The earlier local runner interruptions produced no complete media or `.part` artifact; the final bounded run above is the auditable six-candidate outcome.
