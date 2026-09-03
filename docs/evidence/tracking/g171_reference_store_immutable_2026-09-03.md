# G171: immutable reference-store audit

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md` (A5, A7, Q7 and Q8).
This is an exhaustive construct over sports with a canonical reference media
file. No pod action was taken and no footage was deleted, restored, copied, or
rewritten during this lane.

## Q8 premise and code mechanism

Q8 is confirmed from the code, not inferred from the tennis symptom. The
pre-change source was `scripts/platformkit/footage_bridge.py` at the parent
revision. Its `keep_reference` docstring at lines 613-621 explicitly said it
would retain the best clip and replace a weaker incumbent. The operative branch
was:

```python
# scripts/platformkit/footage_bridge.py:633-652 (pre-change parent)
incumbent = _reference_clip(sport)
if incumbent is not None:
    if provisional:
        return False
    ...
    if (bool(quality["passed"]), int(quality["rows"])) <= prior_rank:
        return False
local.replace(candidate)
destination = REFERENCE_DIR / (sport + local.suffix)
candidate.replace(destination)
metadata.replace(sidecar)
if incumbent is not None and incumbent != destination:
    incumbent.unlink()
```

Thus an existing reference was overwritten precisely when an incumbent existed,
the candidate was measured (not provisional), and its `(passed, rows)` rank was
strictly greater than the incumbent sidecar rank. `candidate.replace(destination)`
then replaced the canonical same-suffix path; an incumbent with a different
suffix was additionally unlinked. This was intentional best-clip selection, not
an accidental fall-through or a malicious action. The defect was that the store
was documented as permanent while the intended replacement policy was
unversioned and destructive.

The landed code preserves the canonical `<sport>.mp4` path and publishes a
better measured candidate only as a unique `<sport>.<game-id>[.N].mp4` sibling,
with its own `.reference.json` sidecar. The collision loop at
`footage_bridge.py:612-623` ensures that an existing sibling is also never
replaced; the only `replace` calls publish a local staging candidate to a fresh
destination. No existing reference is deleted.

## Exhaustive mtime and size census

Eligible denominator: the 10 sports with a canonical reference media file
(the `*.reference.json` sidecars are not eligible). Values were measured from
`data/videos/reference/` on 2026-09-03 local time.

| Sport | File | Bytes | Mtime | Overwritten since first write? |
|---|---|---:|---|---|
| baseball | baseball.mp4 | 430129314 | 2026-09-01 04:44:09 | No observed evidence |
| football | football.mp4 | 86738254 | 2026-09-01 10:09:35 | No observed evidence |
| handball | handball.mp4 | 822757936 | 2026-08-31 22:19:48 | No observed evidence |
| kbo | kbo.mp4 | 34995723 | 2026-09-01 02:51:59 | No observed evidence |
| mlb | mlb.mp4 | 36586110 | 2026-09-01 02:01:03 | No observed evidence |
| ncaa_basketball | ncaa_basketball.mp4 | 76083183 | 2026-08-31 22:33:49 | No observed evidence |
| npb | npb.mp4 | 70281079 | 2026-09-01 08:07:32 | No observed evidence |
| soccer | soccer.mp4 | 85788492 | 2026-09-01 04:53:10 | No observed evidence |
| tennis | tennis.mp4 | 2024970178 | 2026-09-03 09:45:18 | Yes: prior 38094576-byte clip replaced |
| wnba | wnba.mp4 | 831059640 | 2026-08-31 22:19:46 | No observed evidence |

Observed overwritten references: **1/10, tennis**. The tennis mtime and the
known prior 38094576-byte tennis clip establish that replacement; G170 records
the mid-session timeline. The mtime census does not provide an immutable
historical log, so it cannot rule out an undocumented overwrite that happened
before the current mtime of another file.

## A5 reader survey, before the change

The exact-path grep found 24 tracked files. Nineteen evidence/spec readers are
historical or operational references and retain their canonical paths unchanged:

- `confounder_findings_2026-09-01.md`, `corpus_mislabel_2026-09-01.md`
- `football_fieldview_2026-09-01.md`,
  `football_fieldview_2026-09-01/gameA_alabama_georgia_gated_snaps.json`
- `football_imagepx_snap_2026-09-01.md`,
  `football_imagepx_snap/gameA_alabama_georgia_snaps.json`
- `g143_staging_hygiene_2026-09-02.md`,
  `g152_court_feet_declaration_2026-09-03.md`, `g152_declaration/README.md`,
  `g152b_declaration_rates_2026-09-03.md`
- `g161_rally/PROTOCOL.md`, `g161_rally/README.md`, `RESULTS_LEDGER.md`,
  `TRACKING_GAPS_2026-09-01.md`
- `specs/G143_spec.md`, `specs/G152_spec.md`, `specs/G152B_spec.md`,
  `specs/G169_spec.md`, `specs/G171_spec.md`

The five exact-path code readers were checked as follows:

| Reader | Check and outcome |
|---|---|
| `footage_bridge.py` | Writer and canonical reader; changed so better clips use immutable siblings. |
| `render_tracking_demo.py` | Documentation example names a canonical file; it remains valid. |
| `tennis_metric_probe.py` | Documentation/comments name the canonical tennis file; it remains valid. |
| `tracking/footage_census.py` | Its inventory intentionally scans all video files, so an additional sibling is additive. |
| `tracking_regression.py` | Its default root-layout check already rejects the existing flat canonical layout and has no runtime caller; no new sibling-specific behavior is introduced. |

The `REFERENCE_DIR` symbol search also found `test_footage_bridge.py`, which was
updated and passed, plus `vault_organize_multi.py` and `vault_sources.py`; the
latter two only use unrelated generic `reference_dirs` fields and do not read
`data/videos/reference/`.

## Verification and B self-check

- Focused per-file test: `python -m pytest scripts/platformkit/test_footage_bridge.py -q` -> 44 passed.
- B1: no filtered metric; the sport enumeration is explicit. B2: canonical
  filenames and sidecars remain supported, with only additive siblings after
  the A5 survey. B3-B5: no gate, claim loop, pod copy, or deployment changed.
- B6: no module moved or retired. B7-B9: no sampled, fitted, or recycled-unit
  metric is claimed. B10: no threshold, bar, coordinate contract, eligibility
  definition, or verdict changed.

## NOT VERIFIED

- The lost 38094576-byte tennis encoding was not restored and no attempt was
  made to recover it.
- The mtime census cannot prove the absence of an earlier undocumented rewrite
  for the other nine files.
- `.claude/skills/lane-spawn-rails/SKILL.md` is absent in this worktree, so its
  requested RAILS block could not be read. No heavy work was run and the pod
  was not contacted.
