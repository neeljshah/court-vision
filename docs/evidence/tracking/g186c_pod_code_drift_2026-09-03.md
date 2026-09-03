# The pod was running stale code, and it is not a git repository

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md) A2, A7. Measured and
remedied by the orchestrator, 2026-09-03. No production logic was changed; this
records a DEPLOYMENT state and its correction.

## What was found

G184's memo recorded source SHA-256 hashes on both sides and noted they differ.
Following that up:

    pod$ git rev-parse --is-inside-work-tree
    fatal: not a git repository (or any parent up to mount point /)

**The pod is not a git checkout.** It was seeded from a gzipped `git archive`
tarball during the 2026-09-03 bootstrap, so it carries no git metadata, has no
remote, and cannot be brought up to date by `git pull`. There is no way to ask
it what commit it corresponds to.

The practical consequence, which is larger than "the daemon has not restarted":
**every code fix landed to master today was absent from the pod's files
entirely.** The daemon was not running yesterday's code pending a restart; the
files themselves were the bootstrap snapshot.

| file | pod before | pod after | local |
|---|---|---|---|
| `domains/tennis/tracking/adapter.py` | `c7314449...` | `f7687c56...` | `f7687c56...` |
| `domains/tennis/tracking/court_lines.py` | `799c1bf2...` | `0f0f3fa3...` | `0f0f3fa3...` |
| `scripts/platformkit/tracking/decode_manifest.py` | `deb6f194...` | `27400554...` | `27400554...` |

## What was deployed, and what is actually live

4,327 Python files under `scripts/platformkit/` and `domains/` were shipped as a
10.5 MB tarball, excluding `__pycache__`. Both human-gated trees were untouched.
All three sampled hashes now match local exactly, and an import smoke test of
`track_daemon`, `adapter_run`, `decode_manifest`, `track_daemon_done` and the
tennis adapter passes on the pod.

**Be precise about what this makes live.** `adapter_run` is spawned as a fresh
subprocess per job, so it picks up new code on the next job. The daemon process
(pid 33064) imported its modules at start and holds the OLD ones in memory, so
any daemon-level fix stays inert in it until it next cycles. The standing rule is
never to kill anything on the pod, so that restart is not taken here.

## Consequence for earlier measurements

**Every pod-side measurement taken before this deploy was made against the
bootstrap snapshot, not against master.** G184 flagged exactly this and kept its
two populations separate for that reason, which was the right call. Its pod
distribution should be read as a measurement of the code the pod was running.
Nothing is retracted; the caveat is now explained rather than merely noted.

## NOT VERIFIED

- That any behaviour changed as a result. This is a file-state correction; no
  before/after tracking result is claimed.
- Which specific landed fixes were absent, file by file. Only three files were
  hash-sampled; the deploy covered all 4,327 without a per-file diff.
- Whether any pod-local edit was overwritten by the deploy. The pod had no git
  metadata, so a local divergence there could not be detected before shipping.
- Whether the daemon's in-memory modules differ behaviourally from the deployed
  ones in a way that affects rows produced between now and its next restart.
