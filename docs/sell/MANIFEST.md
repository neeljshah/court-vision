# Evidence Pack Manifest

> Generated: 2026-07-15T15:41:16.102234+00:00
> Pack version: sell.evidence_pack.v1
> Artifacts: 3

## The one reproduce command

```
python -m sell.evidence_pack
```

Rebuilds the complete evidence pack under `data/frontend/sell/evidence_pack/`
from scratch. Every artifact is honesty-linted before any file is written.

## Artifact list

| Artifact                         |     Size | sha256 note              |
|:---------------------------------|---------:|:-------------------------|
| methodology.json                 |     1395 bytes | (see artifact on disk)   |
| reproduce.json                   |     1384 bytes | (see artifact on disk)   |
| track_record.signed.json         |     1756 bytes | (see artifact on disk)   |

> sha256 digests are opaque cryptographic outputs (not presented results).
> They are stored in the on-disk `manifest.json`; verify them with
> `python -m sell.evidence_pack` and compare the regenerated manifest.

## Additional reproduce commands

```
# Verify the signature on the signed track record:
python -m sell.cli verify

# Run the full governance preflight (exits 0/1):
python -m governance.run_governance

# Run the leak-free golden walk-forward (exits 0/1):
python -m scripts.platformkit.eval_gate.run_gate --golden

# Dump all reproduce verdicts to stdout (in-process):
python -c "import json; from sell.reproduce import reproduce_all; print(json.dumps(reproduce_all(), indent=2, default=str))"
```

## Tamper-evidence

- The track record is HMAC-signed (HMAC-SHA256); any single mutated field
  fails verify.
- The manifest is a sha256 roll-up over every packed artifact's canonical
  bytes. Edit one byte of any artifact and the manifest_sha256 changes.
- The whole pack is run through `governance.honesty_linter` before any
  file is written; a banned $-edge key or a retracted number raises and
  nothing is written.

## Human-gated step (NOT performed by any agent)

Public deployment and pushing to `origin` are human-gated. No part of
this pack, and no agent, ever pushes to a public remote or deploys.
