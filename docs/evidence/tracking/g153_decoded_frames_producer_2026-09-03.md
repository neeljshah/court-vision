# G153 - local decoded-frame producer reproduction

## Verdict

**ACCEPT.** The `decoded_frames` producer is present at HEAD and a real local
adapter run produced one durable ledger row with `decoded_frames: 150`.
The producer gap is therefore closed locally; the remaining action is deployment
of the already-versioned producer source. No pod connection, deployment, daemon
start, restart, stop, or poll occurred in this lane.

The source files are clean against HEAD. The SHA-256 of
`scripts/platformkit/track_daemon.py` is
`9d97b1780f2d53b8b50737ba1e15213b78960b21283fedb98fa82b3e7d3d3085`,
which exactly matches the remote-source hash recorded by G149. The commit that
last changed the current producer pair is
`41cc7b8fdaa3f85c9223ccaf15f76cfea1cb1604`; that is the producer commit the
pod needs (the present lane changes no producer code).

## Q8 premise re-measurement and producer path

The premise is true at HEAD: the SUCCESS completion path writes the decoder
denominator to the ledger before appending the row.

`scripts/platformkit/track_daemon_done.py:133-155` obtains the independently
decoded count with `frame_counter(video)`, builds the decode manifest with that
count, and stores it in the durable verdict sidecar as `decoded_frames`.
`scripts/platformkit/track_daemon.py:222-228` takes that sidecar value (using
the per-frame manifest only as a fallback), then calls `_record(entry)` after
the additive update:

```python
manifest_frames, fresh_solves = _fresh_solve_summary(job["game_id"])
entry.update(decoded_frames=(graded or {}).get("decoded_frames", manifest_frames),
             source_resolution=(source or {}).get("source_resolution"),
             fresh_solves=fresh_solves)
entry["rows_per_decoded_frame_step_change"] = _step_change(
    _previous_sport_entry(job["sport"]), entry)
_record(entry)
```

## Local reproduction

An isolated two-second local clip was made from the retained
`tennis__tennis_nyYk2nPZAwY_720p.mp4` active range used by the existing local
sequential-plan evidence. `ffprobe -count_frames` independently reported **150
decoded frames**. The actual production adapter entry point was then run locally:

```text
python -m scripts.platformkit.adapter_run <isolated clip> g153_active --max-frames 75
g153_active rows=71 passed=True failures=[]
```

Its emitted `tracking_data.csv` was then sent through the real
`track_daemon._finish()` completion path with the real `adjudicate()`,
decoder, sidecar writer, ledger writer, and retention logic. Only the module's
relative data roots were redirected to the isolated temporary directory; no
writer or evaluator was mocked. The actual append-only row, read verbatim back
from that local ledger, is:

```json
{"game_id": "g153_active", "sport": "tennis", "status": "tracked", "adjudicated": true, "rows": 71, "verdict": null, "passed": false, "failure_heads": ["coverage 0.20 < 0.90", "ball_valid 0.07 < 0.20"], "failures": ["coverage 0.20 < 0.90", "ball_valid 0.07 < 0.20"], "coverage_pct": 0.2, "coordinate_space": "court_feet", "rung": "COURT_FEET", "evaluated_at": 1788444916, "seconds": 1, "finished_at": 1788444916, "decoded_frames": 150, "source_resolution": null, "fresh_solves": null, "rows_per_decoded_frame_step_change": null}
```

The eligible denominator is the independently decoded **150 frames**, not the
71 emitted tracking rows, sampled adapter limit, or any reused track ID. This
is a complete construct reproduction: `n = 1` real local ledger row and one
known denominator-bearing source clip. Its quality failures are retained as
reported; they are not filtered or used to alter a bar or verdict.

## Reader survey (A5)

`git grep` of the daemon-ledger path found these current consumers:

- `scripts/platformkit/track_daemon.py` is the writer and its only
  `decoded_frames` reader is the diagnostic density marker. It returns `None`
  for missing or invalid legacy values.
- `scripts/platformkit/night_report.py` parses ledger JSON objects permissively
  and uses existing `.get()` fields; the additive field is ignored.
- `scripts/platformkit/pod_pull_sync.sh` copies JSONL bytes and does not parse
  row fields.
- `scripts/platformkit/tracking/loop_status.sh` tails a remote daemon-ledger
  line for status text and does not parse `decoded_frames`.
- The remaining grep hits are focused tests and the existing additive builder
  `track_daemon_ledger.py`; no production reader rejects an extra JSON key.

No ledger field, status, coordinate declaration, frozen 0.90 coverage bar, or
verdict changed in this lane.

## Focused test

Exactly one new per-file test exercises the real local completion writer with a
four-frame temporary video and reads its append-only row:

```text
python -m pytest scripts/platformkit/test_g153_local_decoded_frames_producer.py -q
1 passed in 1.30s
```

## Verifier contract self-check

### A

- A1: the one required per-file test passed locally. No full pytest run occurred.
- A2: the row above was read back from the actual local JSONL after the real
  append; `decoded_frames` is 150.
- A3: Q7 replaces an eye check with reproduction for this construct row; no
  head-slice render evidence is claimed.
- A4: `n = 1` contains one distinct `game_id`, `g153_active`.
- A5: the complete current reader survey is recorded above.
- A6: this lane is committed with explicit pathspecs only; no pod archive or
  deployment was performed.
- A7: the committed evidence memo, two producer files, sole new test,
  `RESULTS_LEDGER.md`, and `TRACKING_GAPS_2026-09-01.md` all exist at this
  self-check.

### B

- B1: no rows were excluded; the sole constructed row and its failed quality
  heads are shown verbatim.
- B2: no schema change was made. The existing additive field and all readers
  were checked.
- B3-B4: no gate, quarantine, claim, retention, or lifecycle behavior changed.
- B5: no pod file was copied and no deployment occurred.
- B6: no module, import, test, or `-m` reference was moved or retired.
- B7-B8: no render sampling or self-fit residual is claimed.
- B9: the denominator is `ffprobe`/decoder-derived 150 source frames, not
  emitted rows or recycled identifiers.
- B10: no harness threshold or gate value changed; the row retains the 0.90
  coverage comparison reported by the unchanged harness.

## NOT VERIFIED

- No pod ledger row exists from this lane; the pod and daemon were deliberately
  untouched.
- No deployment has occurred. The named producer commit still needs the
  orchestrator's approved deployment path before a pod after-row can be read.
- This row does not adjudicate corrected coverage, alter the 0.90 bar, or make
  any claim about tracking quality beyond the persisted denominator.
