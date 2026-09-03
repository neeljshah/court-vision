# G169 - emitted-frame discrepancy is different input, not nondeterminism

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A2, A7,
section B, and Q7-Q8. This is an evidence-only investigation. No adapter,
harness, threshold, coordinate contract, verdict, tracking store, pod daemon,
or deployment was changed.

## Q8 premise re-measurement

The premise is reproduced from the landed, immutable evidence before testing an
explanation:

| Source | Rows | Distinct emitted frames | Decoded frames |
|---|---:|---:|---:|
| G152b local reference run | 6,770 | 2,597 | 28,773 |
| Existing pod `tennis_smoke` table | 1,861 | 726 | 28,773 |

The discrepancy is `2,597 / 726 = 3.5771x` (reported originally as 3.6x).
I independently recomputed the current pod table's 1,861 rows and 726 unique
`frame` values from its CSV in the read-only pod batch below. G152b deliberately
used a disposable local scratch CSV, which is no longer retained; its committed
memo is the durable source for its independently recomputed 6,770/2,597 values.

## Candidate checks, in required order

### (a) Different input - CONFIRMED

The inputs are not byte-identical and are not even comparable in size. The
local file is the reference used by G152b in the main local worktree; this a3
worktree does not have its ignored `data/` copy. It was read only, not copied.

| Input | Bytes | SHA-256 |
|---|---:|---|
| Local `C:\\Users\\neelj\\nba-ai-system\\data\\videos\\reference\\tennis.mp4` | 2,024,970,178 | `9F675346833087EAD186376F4F375109DF794F3FCD75969763C62126A32362F3` |
| Pod `data/videos/tennis_smoke.mp4` | 38,094,576 | `685b25d113f1c62e02e7de1f53fcfbad0bfefbefb45feff6c22d63aca89c18db` |

This eliminates the proposition that G152b and `tennis_smoke` tracked the same
input. It fully explains why comparing their emitted-frame counts is not a
nondeterminism test. No later candidate is needed to resolve the row.

### (b) Different frame budget - checked, not the explanation

The pod entry point has an explicit default limit of 30,000 and passes it to
the adapter:

```python
parser.add_argument("--max-frames", type=int, default=30000)
...
options = {"max_frames": args.max_frames, "stride": plan.stride}
...
frame = adapter.process_video(video, **options)
```

Both source paths decode 28,773 frames, below 30,000. Therefore this default
does not truncate either count. No invocation-specific `--max-frames` override
is retained for the historical `tennis_smoke` command; it is NOT needed for the
resolution because candidate (a) already excludes equal input.

### (c) Different decode environment - observed, but not causal evidence here

The current direct version readings are local OpenCV 4.11.0 and pod OpenCV
5.0.0. The pod's sequential decode count is 28,773. G152b's committed local
sequential `VideoCapture.read()` count is also 28,773, so the available counts
do not differ. The pod has changed since the earlier environment memo that
recorded 4.14.0; that historical version is not substituted for the current
readout.

The environments are nevertheless different, so this is not a controlled
cross-environment comparison. It is also unnecessary to isolate an environment
factor after the input mismatch is conclusive.

### (d) Genuine nondeterminism - NOT ENTERED

This branch is reached only after (a)-(c) are eliminated. Candidate (a) is
confirmed, so a second tracker run would add cost without answering the stated
comparison. No local re-track was run. No pod tracking job was launched; hence
no `nohup` job, no daemon interaction, and no shared-store write occurred.

This outcome is also consistent with, but does not rely on, G52's prior
same-environment tennis repeats: 30 pod repeats there were bit-identical. G52
was a different code/environment moment and is not a substitute for an input
identity check here.

## Exact commands and raw outputs

Local source availability, size, and hash:

```powershell
PS> Get-Item -LiteralPath 'C:\Users\neelj\nba-ai-system\data\videos\reference\tennis.mp4' | Select-Object FullName,Length

FullName                                                          Length
--------                                                          ------
C:\Users\neelj\nba-ai-system\data\videos\reference\tennis.mp4 2024970178

PS> $hash = (Get-FileHash -LiteralPath 'C:\Users\neelj\nba-ai-system\data\videos\reference\tennis.mp4' -Algorithm SHA256).Hash; Write-Output "LOCAL_SHA256=$hash"; Write-Output "LOCAL_BYTES=$((Get-Item -LiteralPath 'C:\Users\neelj\nba-ai-system\data\videos\reference\tennis.mp4').Length)"
LOCAL_SHA256=9F675346833087EAD186376F4F375109DF794F3FCD75969763C62126A32362F3
LOCAL_BYTES=2024970178

PS> python -c "import cv2; print('CHECK_CV2='+cv2.__version__)"
CHECK_CV2=4.11.0
```

One batched, read-only pod SSH inspection (the Python loop is sequential
`VideoCapture.read()`, releasing the capture after EOF):

```powershell
PS> ssh -o BatchMode=yes -o ConnectTimeout=30 config.pod <the following one-shot bash payload>
set -eu
cd /workspace/nba-ai-system
stat -c 'REMOTE_PATH=%n REMOTE_BYTES=%s' data/videos/tennis_smoke.mp4
sha256sum data/videos/tennis_smoke.mp4
python3 - <<'PY'
import cv2
path = 'data/videos/tennis_smoke.mp4'
cap = cv2.VideoCapture(path)
n = 0
while True:
    ok, _ = cap.read()
    if not ok:
        break
    n += 1
cap.release()
print('REMOTE_CV2=' + cv2.__version__)
print('REMOTE_DECODED_FRAMES=' + str(n))
PY
grep -n -- '--max-frames' scripts/platformkit/adapter_run.py
python3 - <<'PY'
import csv
with open('data/tracking/tennis_smoke/tracking_data.csv', newline='') as handle:
    rows = list(csv.DictReader(handle))
print('REMOTE_TENNIS_SMOKE_ROWS=' + str(len(rows)))
print('REMOTE_TENNIS_SMOKE_DISTINCT_FRAMES=' + str(len({r['frame'] for r in rows})))
PY

REMOTE_PATH=data/videos/tennis_smoke.mp4 REMOTE_BYTES=38094576
685b25d113f1c62e02e7de1f53fcfbad0bfefbefb45feff6c22d63aca89c18db  data/videos/tennis_smoke.mp4
REMOTE_CV2=5.0.0
REMOTE_DECODED_FRAMES=28773
81:    parser.add_argument("--max-frames", type=int, default=30000)
REMOTE_TENNIS_SMOKE_ROWS=1861
REMOTE_TENNIS_SMOKE_DISTINCT_FRAMES=726
```

The command above is one SSH round trip, performed before any possible tracker
run. It has no copy, process-control, deployment, restart, kill, or write
operation.

## Resolution

**Different input holds.** The 3.5771x emitted-frame difference is not evidence
of tracker nondeterminism because the compared files have different sizes and
SHA-256 values. The identical sequential decode count does not restore input
identity; a same frame count is compatible with different encodes or content.

No threshold, bar, adapter, harness, coordinate contract, or existing verdict
moved. This is a boring full success: it removes the apparent premise that a
single clip yielded incompatible tracking results.

## Counterfactual impact if nondeterminism had held

No landed result is disturbed by the actual different-input finding. Had two
same-input, same-environment runs differed instead, the affected landed results
would be:

- **G152b:** its one-run declaration rate (2,597/28,773), strict geometry
  frame rate (1,350/28,773), and row geometry share would need repeat-run
  uncertainty before being used as a stable adapter measurement.
- **G161:** its hand labels and 113/300 rally-view share would remain valid,
  but its two rally-normalised coverage figures would be affected because they
  treat G152b's 2,597 and 1,350 adapter numerators as fixed.
- **G162+G163:** the static epoch-churn code trace would remain valid, but the
  `tennis_smoke` rows, distinct-frame count, track-length distribution,
  duplicate count, and jump-pair denominator would need same-environment
  repeat confirmation before they were stable output measurements.
- **G157:** its exhaustive one-directory census and zero-ledger observation
  would remain valid, while its `tennis_smoke` snapshot metrics (1,861 rows,
  726 frames, and 1,558/1,861 solved share) would need the same confirmation.

Results not affected by a tracker-nondeterminism branch are G161's manually
labelled rally census and its blind relabel agreement, G152b's sequential decode
denominator as a decode measurement, G162's static source-code explanation of
epoch resets, and G157's count of one table directory / zero ledger rows. G52's
existing 30 same-environment bit-identical pod repetitions would be contrary
evidence, not invalidated evidence; a new positive result would need its own
scope explanation because G52 used an earlier pod environment.

## Verifier-contract self-check

### A and Q

- **A2:** Recomputed the current `tennis_smoke` row and unique-frame counts
  directly from the pod CSV. Recomputed the headline ratio as 2,597/726 from
  the durable G152b and current-pod counts. G152b's disposable CSV is absent,
  and that limitation is named rather than silently re-created.
- **A4 / B9:** Rows and unique frames are reported separately; every frame
  denominator is a distinct `frame` value, never a track id or repeated row.
- **A7:** Before commit, the evidence paths used here were checked to exist:
  this memo; G152b; G161 rally README; G162+G163; G52; RESULTS_LEDGER; and
  VERIFIER_CONTRACT.
- **Q7:** This is a construct reproduction, not a sampled score. Its eye
  check is the quoted reproduction commands and raw output; no head slice or
  render claim is made.
- **Q8:** The 2,597-versus-726 premise was re-derived before candidate work.

### B

- **B1:** Clear. Neither output set is filtered; all 1,861 pod rows and all
  726 distinct pod frame values are counted.
- **B2:** Clear. No schema, field, reader, or status changed.
- **B3:** Clear. No absence is classified as a bad result; the missing G152b
  scratch CSV is explicitly named as unavailable.
- **B4:** Clear. No claim, queue, retry, or ownership path changed.
- **B5:** Clear. Pod interaction was one read-only batch before any tracker
  run. No pod file was copied or deployed.
- **B6:** Clear. No module, import, test, or command was moved or retired.
- **B7:** Clear. No visual or row sample is offered as evidence.
- **B8:** Clear. No fit or independence claim is made.
- **B10:** Clear. No threshold, gate, coordinate contract, or verdict changed.

## NOT VERIFIED

- The precise provenance or content relationship between the 2.02 GB local
  reference and the 38 MB pod file; the mismatch alone resolves the comparison.
- The original historical `tennis_smoke` invocation's explicit command-line
  arguments, including whether it supplied a non-default `--max-frames`.
- A new same-input, same-environment two-run determinism trial. It is correctly
  not run because candidate (a) holds.
- Which individual decode-environment factor changed since G52's recorded pod
  OpenCV 4.14.0 to the current pod's 5.0.0; isolation is not needed here.
- Any new tracking quality, geometry, coverage, calibration, or downstream
  conclusion. This memo only resolves the comparability premise.

No code was added, so no per-file test applies. No full pytest run was made.
