# G151 quota failures fail loudly

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`. This is a two-call-site
construct check (`n = 2`); no threshold, gate, coordinate contract, worker
count, verdict, or pod file was changed.

## Premise first: code before the change

The ledger's original `_record` was:

```python
LEDGER.parent.mkdir(parents=True, exist_ok=True)
with LEDGER.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(entry) + "\n")
```

It had no write probe, `fsync`, readback, or contextual error. An `OSError`
does propagate from this function; it does not return success. `tick()` and
`main()` do not catch `_finish()`/`_record()` errors, so the code did not prove
the stated "return quietly" mechanism. It did leave a quota failure without a
durable-write check or a call-site error message identifying the ledger path.

The staged upload's original call was:

```python
subprocess.run(["scp", "-o", "StrictHostKeyChecking=no", "-P", POD_PORT,
                str(local), "%s:%s.part" % (POD_HOST, remote)],
               check=True, timeout=7200, capture_output=True, text=True)
```

`check=True` already raises `CalledProcessError`; this path was therefore
already loud for a nonzero `scp` exit. It did not probe the quota-limited pod
directory first, identify the failure as a failed pod write, or report whether
the target `.part` remained. That missing diagnostic is the only upload change.

## After

`track_daemon._record()` now calls `_write_probe()` before each append. The
probe writes a small named file in the ledger directory, flushes and fsyncs it,
reads it back, and removes it in `finally`. The append itself now flushes and
fsyncs, and either probe or append failures raise a path-specific
`RuntimeError`.

Both bridge upload entry points now call `_upload_to_pod()`. It runs the same
write/fsync/read/delete procedure on the remote stage through `ssh` before
`scp`. An `scp` failure remains an exception, now with its error tail and, for
the staged path, an explicit `stranded .part remains`, `no .part remains`, or
`could not verify .part` report. The implementation does not delete a remote
partial after a quota failure.

## Reproduction

The only new per-file test is:

```text
python -m pytest tests/platformkit/test_g151_quota_fails_loud.py -q
2 passed
```

It injects a ledger-probe quota failure and verifies no ledger row is written.
It injects a pod-probe quota failure, verifies `scp` is not reached, and
verifies the raised message records a stranded staged `.part`.

For the required guard-removal check, the two new call sites were temporarily
removed locally and that exact test file was re-run. It failed `2/2`: the
ledger test reported `DID NOT RAISE`, and the upload test reached its
`scp must not run after a failed write probe` assertion. Both calls were
restored immediately; the same test then passed `2/2`. No full test suite ran.

## One live pod observation

One successful read-only pod session created `/workspace/.g151_write_probe`,
fsynced 17 bytes, read back the exact 17 bytes, and deleted it in `finally`:

```text
G151_WRITE_PROBE=PASS bytes=17
2.0K  /workspace/bootstrap.log
0     /workspace/keep_track_daemon.log
2.0K  /workspace/keep_track_daemon.sh
512   /workspace/keepalive.log
2.5G  /workspace/nba-ai-system
399K  /workspace/pod_md5.txt
400K  /workspace/pod_md5n.txt
0     /workspace/track_daemon.log
512   /workspace/track_daemon.pid
```

This establishes present writeability of the one probe file, not a quota-byte
headroom value: `du` reports occupied visible paths and the spec explicitly
disallows treating `df` as quota evidence. No process was started, restarted,
or killed; no deployed file was changed.

## NOT VERIFIED

- A real quota-exhausted failure was not induced; that would require filling or
  modifying the pod and is outside this read-only task.
- The git-only changes were not copied to the pod, so no live daemon append or
  production `scp` used them.
- No existing remote `.part` was inspected, removed, or retried.

## Contract self-check: section B

- B1: no scored or filtered metric.
- B2: no schema or field change; all `track_daemon_ledger` readers were grepped.
- B3-B4: no gate, quarantine, or claim path changed.
- B5: no file was copied to the pod before acceptance.
- B6: no module moved or retired; both upload callers route through the helper.
- B7-B9: no rendered sample, fit, or denominator metric.
- B10: no threshold or gate value changed.
