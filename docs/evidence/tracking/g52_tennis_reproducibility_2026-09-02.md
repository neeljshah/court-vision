# G52 RESOLVED: the pipeline is deterministic in each environment; the two runs came from different ones

Date: 2026-09-02. Gap: G52, with the G59 remediation as its control arm.
Two pod measurements: the bisection job (pid 214874, 50 records) and the control
arm run immediately after removing the rejected selector.

**Verdict: RESOLVED. The original framing is false, my replacement hypothesis
was falsified, and the actual cause is an environment difference between two runs
that were assumed to be from one environment.** See section 4. G52 was recorded as "the tennis
pipeline is NOT REPRODUCIBLE run to run". On the pod it is exactly reproducible.
I then proposed that the rejected player selector was deterministically moving
solver coverage; the control arm refutes that as well.

## 1. What the bisection actually found

The driver re-ran the 15 committed sequential ranges (seed 20260901, 300 decoded
frames each) and compared against `EXPECTED`, which holds the CONTROL column
from the G26b experiment. Then, because the premise did not reproduce, it ran
each of two ranges five times in each of three modes.

| finding | result |
|---|---|
| ranges matching the control column | **9 of 15** |
| repeats within a mode (3 modes x 2 ranges x 5) | **all 30 bit-identical** |
| frame decode, 10 reads of the same frame | **byte-identical**, both probes |
| gpu_baseline vs gpu_pinned vs cpu_pinned | **no difference at all** |

cv2 4.14.0 throughout. So the four candidate sources G52 named -- detector
nondeterminism, thread count, GPU nondeterminism, frame-decode drift -- are all
**ruled out on the pod**. The pipeline is deterministic there.

The 6 ranges that differ from the control column are precisely the 6 the G26b
memo recorded as changing between its control and treatment runs, and the pod
reproduces the TREATMENT value in every one:

| range | control column | pod measured | treatment column |
|---|---:|---:|---:|
| nyYk 5715 | 0.6100 | **0.6000** | 0.6000 |
| nyYk 33105 | 0.9900 | **0.9933** | 0.9933 |
| nyYk 33855 | 0.9967 | **1.0000** | 1.0000 |
| nyYk 43830 | 0.5600 | **0.5300** | 0.5300 |
| tennis09 5070 | 1.0000 | **0.9967** | 0.9967 |
| tennis10 150 | 0.3967 | **0.3933** | 0.3933 |

## 2. The hypothesis this suggested, and its control arm

The pod was, at that moment, running the G26 attempt-1 selector that a verifier
had REJECTED (G59). So the obvious reading was: the selector deterministically
changes solver coverage -- a coupling from player selection into the court
solver that should not exist. That would have been a real and more actionable
defect than nondeterminism.

**The control arm refutes it.** The G59 remediation deployed master's
`adapter.py` (md5 `21348856206e2bee53f5a151445c8e3c`, identical both sides) and
REMOVED `player_select.py` entirely, then re-ran the same ranges with the same
`run_range` entry point. With the selector gone:

| range | control column | selector REMOVED | verdict |
|---|---:|---:|---|
| nyYk 5715 | 0.6100 | 0.6000 | still treatment |
| nyYk 33105 | 0.9900 | 0.9933 | still treatment |
| nyYk 33855 | 0.9967 | 1.0000 | still treatment |
| nyYk 41985 | 0.5733 | 0.5733 | unchanged in both columns |
| nyYk 43830 | 0.5600 | 0.5300 | still treatment |
| tennis09 615 | 0.7067 | 0.7067 | matches control (never a changed range) |

Removing the rejected selector did not restore a single value. **The selector is
not the cause.** `player_select.py` was absent from the filesystem for this run,
which is as clean a removal as exists.

## 3. What this narrowed to (superseded by section 4)

At this point the pod was established as deterministic and the selector was
ruled out, leaving "the local environment" as the remaining candidate. That was
the right next question and section 4 answers it directly, so this section is
kept only to show the order the reasoning actually went in.

The original framing must not be quoted as-is: "the tennis pipeline is not
reproducible run to run" is false on the pod AND false locally.


## 4. RESOLVED: it is an environment difference between two runs assumed to be one

The decisive test was cheap and should have been run first. `nyYk` is one of the
four clips available locally, so the same `run_range` entry point was invoked on
this machine, on master's code, with `player_select.py` absent -- the identical
configuration the pod ran.

| range | G26b control | LOCAL (cv2 4.11.0) | POD (cv2 4.14.0) |
|---|---:|---:|---:|
| nyYk 5715 | 0.6100 | **0.6100** | 0.6000 |
| nyYk 43830 | 0.5600 | **0.5600** | 0.5300 |
| nyYk 33105 | 0.9900 | **0.9900** | 0.9933 |
| nyYk 41985 | 0.5733 | **0.5733** | 0.5733 |

**Local reproduces the control column on 4 of 4 ranges.** The pod reproduces the
treatment column. Both machines are internally deterministic -- the pod at 30 of
30 identical repeats, and local matching the control column that was recorded on
a different day.

So the G26b "control" and "treatment" columns were not a control and a treatment
at all. They are one local run and one pod run, compared as though they came from
the same environment. Nothing about the selector was ever being measured by that
difference. G52's premise -- "the tennis pipeline is NOT REPRODUCIBLE run to run"
-- is false in both environments taken separately.

The environments differ in several ways at once, recorded by the G62 stamp:

| | local | pod |
|---|---|---|
| cv2 | 4.11.0 | 4.14.0 |
| OS | Windows-10-10.0.26200 | Linux |
| python | 3.10.0 | 3.12 |

**Which specific factor causes the divergence is NOT established.** cv2 is the
leading candidate because the solver's Hough and LSD calls live there and a
different build gives different segments, but this experiment varied all three
together and cannot separate them. Pinning cv2 to 4.14 locally, changing nothing
else, is the one-variable test and it has not been run.

### What this costs, and what it is worth

Every tennis before/after comparison that mixed a local run with a pod run is
invalid, including the G26 acceptance rule that tried to hold coverage constant
as a control. But the pipeline itself is sound: it is deterministic on both
machines, and G22's treatment for soccer (pinned decode, seeds, single-thread
cv2) is not what tennis needed. What tennis needed was for anyone to record
where a number was computed -- which is exactly the G62 gap.

## NOT VERIFIED

- **The specific environment factor is not isolated.** Local differs from the pod
  in cv2 build, OS and python version simultaneously. Pinning cv2 to 4.14 locally
  and changing nothing else is the one-variable test; it has not been run.
- **I contaminated part of my own control arm.** At about 18:20 UTC, while it was
  running, I deployed 13 modules to the pod, and `tennis_sequential_plan.py`
  imports one of them (`source_timebase.py`). Ranges recorded before 18:20 are on
  one code state; ranges after are not. Every number in section 2 above is from
  the PRE-deploy window (18:10-18:15 UTC) and is clean, but the full 15-range
  verdict is not, and the set must be re-run on the settled code state before any
  15-range claim is made. This is my error, not the lane's.
- The G26b runs were local; the pod is a different machine, OS and cv2 build.
  The cross-environment comparison is suggestive, not controlled. Nobody has run
  the control column on the pod under master's selector AND master's
  `court_lines.py` together.
- `domains/tennis/tracking/court_lines.py` on the pod was still the pre-G41
  `found[:, 0, :]` form during both measurements. Under cv2 4.14 that is
  behaviourally identical to master's reshape (the array is (N,1,4) either way),
  so it is PREDICTED to be a no-op, but that prediction is not yet measured.
- No renders were viewed for this row. It is a numerical result about
  reproducibility, not a claim about what the solver sees.
- The G26b `report.json` carries no environment metadata at all -- no host, no
  timestamp, no library versions -- which is why the local runs cannot be
  reconstructed. That gap is worth its own row.
