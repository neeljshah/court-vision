# G149 - persist decoded-frame denominator

## Result

**NOT VALIDATED.** The additive producer is present in both this worktree and
the pod source tree, and the one new focused successful-row test passes. The
required real new ledger row cannot be observed without starting or restarting
the daemon, which G149 expressly forbids. No process was started, restarted,
killed, or otherwise changed by this lane.

The read-only pod census reproduced the stated before condition: **0/12** of
the most recent physical ledger rows carries `decoded_frames`. The 12 game IDs
are `soccer_PwqdSwPQFFw`, `wnba_08`, `ncaa_basketball_4Drw9t7xqgg`, `wnba_09`,
`tennis_08`, `ncaa_basketball_VIlUnUeCMmE`, `wnba_10`,
`soccer_DtzIyXc56f4`, `ncaa_basketball_owTX2OPmIVw`, `wnba_OdGDLXvM76w`,
`kbo_8UMcAyU1pi0`, and `mlb_FGtFanovws4`. This includes the post-G139
denominator-failure rows named in the G149 premise. Every listed row retained
its existing fields; none is rewritten.

At the final read-only check, the live ledger remained at 427 lines, its tail
was still `mlb_FGtFanovws4`, `/workspace/track_daemon.pid` was zero bytes,
and one staged `.mp4` remained. Thus `n = 0` new completed tracked games for
this lane. This does not meet G149's real-cycle acceptance bar and is not
reported as an ACCEPT.

## Manifest and field definition

The relevant success path in
[`track_daemon_done.py`](../../../scripts/platformkit/track_daemon_done.py)
is:

```python
decoded = frame_counter(video)
manifest = build_decode_manifest(decoded, csv_path)
coverage = manifest.summary.completeness
...
"decoded_frames": decoded
```

`frame_counter` defaults to `decoded_frame_count()`, whose ffprobe command is
`ffprobe -count_frames -select_streams v:0` and reads `nb_read_frames`.
`build_decode_manifest()` then validates every emitted index against that
decoder-supplied count. Its summary carries `decoded`, `solved`, `unsolved`,
`non_play`, and `completeness`; only `decoded` is propagated here.

Therefore **`decoded_frames` means the full decoded-frame count of the
selected primary video stream in the staged source clip**. It is not the
number of emitted tracking rows, a sampled stride, the retained rows, or the
manifest's in-play subset. This is the exact denominator needed for a future
adjudication; G149 does not compute or substitute any coverage value with it.

The pod source file SHA-256 was read-only checked against this worktree:

```text
9d97b1780f2d53b8b50737ba1e15213b78960b21283fedb98fa82b3e7d3d3085
```

The hashes matched. The pod's `_finish()` already contains the additive,
success-safe write:

```python
entry.update(decoded_frames=(graded or {}).get("decoded_frames", manifest_frames),
             source_resolution=(source or {}).get("source_resolution"),
             fresh_solves=fresh_solves)
```

It runs before `_record(entry)`. A natural daemon start will therefore write
the existing sidecar's decoded count to a new ledger row without changing the
frozen harness, its 0.90 tennis bar, any coordinate contract, or any verdict.
This lane did not deploy or copy a file: the source was already byte-identical
when inspected.

## Reader survey

All current consumers of `data/tracking/track_daemon_ledger.jsonl` were
checked.

- [`track_daemon.py`](../../../scripts/platformkit/track_daemon.py) is the
  writer and the only diagnostic reader of `decoded_frames`: it computes an
  opt-in rows-per-decoded-frame step marker and returns `None` for legacy or
  malformed values. It does not rename or repurpose a field.
- [`night_report.py`](../../../scripts/platformkit/night_report.py) parses
  each JSON object permissively and uses `.get()` only for its established
  status, pass, row-count, and failure fields. An added key is ignored.
- [`pod_pull_sync.sh`](../../../scripts/platformkit/pod_pull_sync.sh) copies
  the JSONL bytes and does not parse its schema.
- [`tracking/loop_status.sh`](../../../scripts/platformkit/tracking/loop_status.sh)
  tails the tracking results ledger, not the daemon JSONL, and has no daemon
  row-field reader.
- Existing test-only consumers
  [`test_track_daemon.py`](../../../scripts/platformkit/test_track_daemon.py)
  and
  [`test_track_daemon_ledger_denominator.py`](../../../scripts/platformkit/test_track_daemon_ledger_denominator.py)
  read synthetic JSON rows. The latter already covers mixed legacy/new schema
  compatibility.

No current reader rejects an unknown JSON key. No existing field, status,
threshold, verdict, harness, or coordinate declaration was changed.

## Focused test

The sole new G149 test is
[`test_g149_persist_decoded_denominator.py`](../../../scripts/platformkit/test_g149_persist_decoded_denominator.py).
It drives a successful `tracked` completion with a decoder-backed
`decoded_frames=480` sidecar value, asserts it reaches the ledger row, and
asserts the pre-existing lifecycle, verdict, failure, coverage, coordinate,
rung, and evaluation fields are unchanged.

```text
python -m pytest scripts/platformkit/test_g149_persist_decoded_denominator.py -q
1 passed in 0.79s
```

## Verifier contract self-check

### A

- A1: the sole focused test passed in this worktree (1 passed in 0.79s) and
  again in master after explicit archive landing (1 passed in 1.47s).
- A2: read-only parsing of the final 12 physical records gives 0/12 with the
  key; the final read confirms there is no after row to misstate.
- A3: n/a. This is a complete 12-row tail reproduction, not a render metric.
- A4: the 12 before records have 12 distinct game IDs; no after-game ID exists.
- A5: every current ledger reader is enumerated above and is additive-safe.
- A6: this explicit-path commit is prepared for archive landing; results and
  register rows below record NOT VALIDATED rather than an acceptance.
- A7: every evidence path named in this memo exists at self-check time: this
  memo, the producer/manifest files, all surveyed reader files, and the sole
  focused test.

### B

- B1: no metric was computed after excluding an adverse row; all twelve
  records are named and `n=0` after is explicit.
- B2: additive read only; reader survey complete and no field was renamed,
  removed, or repurposed.
- B3-B4: no gate, quarantine, claim, or retention code changed.
- B5: no pod file was copied before verification or at all by this lane.
- B6: no module, test, import, or `-m` reference was moved or retired.
- B7-B8: no render sample or self-fit residual is claimed.
- B9: `decoded_frames` is independently decoder-derived, not emitted-row or
  recycled-ID based.
- B10: no harness threshold, including the 0.90 coverage bar, changed.

## NOT VERIFIED

- The mandatory after row: the daemon is absent and may only take the deployed
  source at its next natural start; this lane may not restart it.
- A game ID and decoded-frame value for that after row.
- Any coverage recomputation, coverage-bar adjudication, harness change,
  threshold change, coordinate-contract change, or verdict change.
- Whether the next naturally completed source will be tennis. The staged file
  observed at the final check is WNBA, but it was not acted upon.
