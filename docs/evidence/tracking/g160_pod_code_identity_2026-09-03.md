# G160 pod code identity -- 2026-09-03

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`. This is a read-only
measurement. It separately establishes source-file parity and the code loaded
by the live daemon.

## Verdict

**ACCEPT WITH CORRECTIONS.** The source tree is substantially at current HEAD
on an LF-normalized comparison, but the live daemon is stale. A foreign archive
deployment also wrote `/workspace/nba-ai-system`; source parity is not proof
that PID 33064 runs HEAD.

## Exhaustive LF-normalized comparison

The enumeration is complete. The HEAD expected set is every tracked file under
`scripts/platformkit/` and `domains/` (eligible denominator **4,691**). The
pod set is every regular file under those same directories (eligible denominator
**5,083**). The union comparison denominator is **5,084**. Each side hashes
`bytes.replace(b"\\r\\n", b"\\n")` with SHA-256, so git-archive CRLF conversion
does not count as drift.

| Result | Count | Meaning |
|---|---:|---|
| IDENTICAL | 4,689 | exact LF-normalized match in the 5,084-path union |
| DIFFERS | 1 | same source path exists on both sides but normalized hashes differ |
| MISSING_ON_POD | 1 | HEAD source path has no pod file |
| POD_ONLY | 393 | pod file has no HEAD counterpart |
| Non-identical total | 395 | 1 + 1 + 393 of 5,084 |

The non-compiled source differences are:

1. `scripts/platformkit/tracking/worktree_data_links.py` -- `DIFFERS` after LF normalization.
2. `scripts/platformkit/test_g153_local_decoded_frames_producer.py` -- `MISSING_ON_POD`.

The remaining 393 names are pod-only `__pycache__/*.pyc` runtime artifacts.
Every one of their paths, the two source discrepancies, hashes, byte counts,
and pod mtimes is named in the committed exhaustive comparison table; no item
is sampled or excluded.

## Reproduction and raw output

The following committed artifacts contain the full raw output for every quoted
read-only collection command and the complete per-path result:

- `g160_identity/remote_lf_sha256.ndjson` -- one remote collector run. It used
  `ssh -o BatchMode=yes -T config.pod <base64-decoded /bin/sh payload>`, then
  `PYTHONDONTWRITEBYTECODE=1 python3 -B` to recursively read regular files,
  normalize LF bytes in memory, and print one JSON record per path. Its raw
  summary is `eligible_denominator: 5083`.
- `g160_identity/remote_process_and_foreign_snapshot.txt` -- one remote,
  read-only `/proc` plus bootstrap/MD5 snapshot, invoked with the same SSH
  wrapper. It prints the daemon's cmdline, start ticks, cwd, executable, open
  files, workspace maps, then `stat`, SHA-256, and raw contents for the three
  foreign-deploy inputs.
- `g160_identity/lf_normalized_comparison.tsv` -- local reproduction against
  `git ls-tree -r --name-only HEAD -- scripts/platformkit domains`, with the
  identical normalization and a row for every union path.

Before the local reproduction, `git diff --quiet HEAD -- scripts/platformkit
domains` passed, so the local bytes used for the HEAD comparison were not
working-tree edits. No pod file was copied, deployed, written, or deleted.

## Running-process identity

Direct `/proc/<pid>/cmdline` inspection found one daemon:

```text
pid=33064
cmdline=python -u -m scripts.platformkit.track_daemon --workers 10 --forever --interval 15
cwd=/workspace/nba-ai-system
exe=/usr/bin/python3.12
started_utc=2026-09-03T14:13:59.180000Z
open files=/dev/null, /workspace/track_daemon.log (stdout and stderr), two pipes
mapped_workspace_files=[]
```

The remote source inventory records these post-start files:

| Pod mtime UTC | File | Process implication |
|---|---|---|
| 2026-09-03T14:28:41Z | `scripts/platformkit/track_daemon.py` | PID 33064 predates it and does not execute this version. |
| 2026-09-03T14:28:41Z | `scripts/platformkit/footage_bridge.py` | Post-start source; not asserted loaded by the daemon. |
| 2026-09-03T14:28:41Z | `scripts/platformkit/g154_local_table_census.py` | Post-start utility; not part of the daemon command. |

The G151 premise is **partly VERIFIED and partly FALSIFIED**. It is verified
for the daemon-side change: current `track_daemon._record()` calls
`_write_probe(LEDGER.parent, "track_daemon")` before append, but PID 33064
loaded `scripts.platformkit.track_daemon` 14 minutes 42 seconds earlier. It
does not execute that write/fsync/readback probe, the append fsync, or the
added path-specific failure behavior. It is falsified as a daemon claim for
the bridge probe: `footage_bridge._pod_write_probe()` is in a separate bridge
process, and this daemon's command, open files, and workspace maps do not show
that module loaded. No process was restarted.

Practical consequence: any pod-ledger number written by PID 33064 from its
2026-09-03T14:13:59Z start until a future daemon restart was produced by the
pre-G151 `track_daemon` process. Those rows are not evidence that the new
daemon-local durability probe, append fsync, or diagnostics ran, even though
the on-disk source now largely matches HEAD. This applies only to rows emitted
by PID 33064; static parity counts, bootstrap records, and values written by
other processes are not retroactively changed by its stale import.

## Foreign-write finding

**FOREIGN DEPLOY CONFIRMED.** `/workspace/bootstrap.log` has mtime and ctime
`2026-09-03 14:03:01Z` and contains:

```text
== 2. tree: shipped by the caller (git archive | tar -x)
```

`/workspace/pod_md5.txt` has mtime `14:02:27Z` and 4,837 MD5 records;
`/workspace/pod_md5n.txt` has mtime `14:05:19Z` and 4,846 unique MD5 records.
All predate daemon start and document a caller's archive-tree write outside
this G160 session. The bootstrap preflight failed and did not boot anything.
The raw metadata, hashes, contents, and failure tail are in
`g160_identity/remote_process_and_foreign_snapshot.txt`.

## NOT VERIFIED

- The exact Python in-memory code object cannot be byte-dumped from `/proc`:
  no workspace source is mapped or left open beyond the daemon logs. The `-m`
  command and source start/mtime ordering prove G151 daemon-side staleness.
- No claim is made that a bridge process is live, stale, or has loaded the
  bridge-side G151 probe.
- This snapshot does not predict a future deployment or restart.
- Pod-only `.pyc` files are named and counted, but not decompiled or treated
  as source deployment.

## Verifier-contract self-check: section B

| Condition | Self-check |
|---|---|
| B1 circular metric | No row was excluded: HEAD, pod, and union populations are explicit. |
| B2 non-additive schema | No schema, field, status, or reader changed. |
| B3 fall-through loss | No gate or quarantine behavior changed. |
| B4 re-claim loop | No claim lifecycle changed. |
| B5 pre-verification deploy | G160 made no pod deployment or copy; all remote commands were read-only. |
| B6 orphans | No module moved, retired, or edited. |
| B7 head-slice evidence | Exhaustive CONSTRUCT enumeration; full path table replaces sampling. |
| B8 self-fit as independent | No fit or residual is claimed. |
| B9 degenerate denominator | HEAD 4,691, pod 5,083, and union 5,084 are explicit and per-path. |
| B10 moved bar | No threshold, gate, coordinate contract, or verdict was changed. |

A7: this memo and all three named `g160_identity/` files exist before commit.
Q7 applies the CONSTRUCT exception: the raw command outputs and full table are
the reproduction. Q8 was performed first: the G151 premise was re-measured
from PID, command line, source mtimes, and source code. No code was added, so
no test applies.
