# G156: bound the daemon's ffprobe adjudication exposure

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), sections A (including
A5 and A7) and B. This is the code half of G156. The measurement half is
[g156a_ffprobe_stall_cost_2026-09-03.md](g156a_ffprobe_stall_cost_2026-09-03.md)
and was not repeated.

## Change

tick() now starts a finished job's unchanged verdict() on a daemon thread.
An adjudicating job does not count toward workers, so the same tick can claim a
new tracking job. The thread computes a non-publishing verdict; the parent poll
loop alone publishes the atomic sidecar, appends the ledger row, and retains
source video after the thread has finished. Thus two simultaneous adjudications
cannot interleave ledger appends: tick() remains single-threaded and is the only
caller of _finish().

The preserved partial patch had no deadline. This landing gives an adjudication
1,800-second ceiling, twice G156a's 900-second upper full-broadcast stall
extrapolation. On expiry, the parent writes an additive
verdict: ADJUDICATION_TIMEOUT and adjudication_timed_out: true, retains the
source out of STAGE, and keeps polling/claiming. The detached daemon thread has
no sidecar or ledger write path; if its count ever returns, its result is
discarded. This bounds the daemon's job/worker exposure without changing the
exact count. It does not attempt to kill a Python thread.

decoded_frame_count, its ffprobe -count_frames invocation, build_decode_manifest,
and the coverage calculation have a zero-line diff in this commit. The count
therefore remains the same exact decoder count for every input; it merely runs
outside the poll loop.

## Cost already measured

Eligible denominator: 4 real local reference clips over 20 MB, each timed once
by G156a. This is the complete eligible set from that measurement, not a newly
selected sample.

| Video | Size GB | Seconds | Seconds/GB | Decoded frames |
|---|---:|---:|---:|---:|
| kbo.mp4 | 0.0326 | 4.87 | 149.5 | 28,800 |
| football.mp4 | 0.0808 | 12.59 | 155.9 | 28,771 |
| handball.mp4 | 0.7663 | 173.91 | 227.0 | 79,500 |
| baseball.mp4 | 0.4006 | 96.75 | 241.5 | 49,079 |

The exact count costs 149.5-241.5 seconds/GB. G156a's 2.0-3.7 GB broadcast
extrapolation is 450-900 seconds. Against the four observed completed job
runtimes (296, 791, 368, and 301 seconds), the unpaired range is 450/791 =
0.569 to 900/296 = 3.041 of a job runtime. The direct live observation was at
least 237/296 = 0.801 before sampling ended. These are throughput-cost ratios,
not performance claims, and the full-broadcast figures remain explicitly
extrapolated.

## Reproduction: before and after

The before reproduction deliberately models the HEAD-before-G156 serial reap
control flow: it cannot reach claim logic until synchronous verdict() returns.
It is local only and never contacts the pod.

Command:

~~~powershell
@'
import threading
started = threading.Event(); release = threading.Event(); claimed = []
active = {"finished": {"done": True}}
def verdict():
    started.set(); release.wait(1)
def old_tick():
    for name, job in list(active.items()):
        if job["done"]:
            verdict(); active.pop(name)
    if not active:
        claimed.append("queued")
runner = threading.Thread(target=old_tick); runner.start()
assert started.wait(1)
print("before: verdict_in_flight=True claimed=%s active=%s" % (claimed, sorted(active)))
release.set(); runner.join(1)
print("before: after_release claimed=%s active=%s" % (claimed, sorted(active)))
'@ | python -
~~~

Raw output:

~~~text
before: verdict_in_flight=True claimed=[] active=['finished']
before: after_release claimed=['queued'] active=[]
~~~

After command (the one permitted per-file test run):

~~~powershell
python -m pytest scripts/platformkit/test_track_daemon.py -q -s
~~~

Raw output excerpt from the changed state, followed by the test result:

~~~text
tracking queued (tennis), 2 active
finished adjudication exceeded 1800s -- recording timeout
finished tennis thin rows=0 passed=None
29 passed in 2.91s
~~~

test_daemon_claims_during_adjudication_and_times_out holds a mocked verdict in
flight, proves queued is claimed with workers=1, then advances its monotonic
start time past 1,800 seconds and proves the finished job is removed with the
additive timeout marker. This is the required after demonstration; the complete
command output is retained in the execution log above rather than fabricated as
a pod result.

## A5 reader survey

Searches run:

~~~powershell
git grep -n -E 'track_daemon_ledger\.jsonl|TRACK_DAEMON_LEDGER|track_daemon_ledger' -- ':!data' ':!vault'
git grep -n -E 'harness_verdict\.json|VERDICT_FILE|read_adjudicated|write_adjudicated|adjudicate\(' -- ':!data' ':!vault'
git grep -n -E 'decode_manifest|build_decode_manifest|decoded_frame_count|build_from_decoder|DecodeManifest' -- ':!data' ':!vault'
~~~

Programmatic ledger readers are night_report.py (general JSON rows),
tracking/loop_status.sh (tail display), and pod_pull_sync.sh (byte copy). The
dedicated daemon tests construct and inspect rows; evidence documents and test
fixtures only quote historical rows. No reader rejects unknown JSON keys, and no
reader references the new adjudication_timed_out key. Existing status, verdict,
and every other field name are retained.

Sidecar readers/writers are track_daemon_done.py (write_adjudicated,
read_adjudicated, and adjudicate), plus track_daemon.py's duplicate check. The
parent is now the sole new-path writer: after its thread is no longer alive it
writes the sidecar first and then the ledger. A timed-out thread was invoked with
publish=False, so it cannot write a late sidecar.

Decode-manifest readers are track_daemon_done.py (the daemon adjudication path),
decode_manifest.py's build_from_decoder, and its focused tests. The counting
function and manifest builder are unchanged; other grep matches are documents
and stored artifacts, not runtime readers of this changed path.

## Verifier self-check

| Check | Result |
|---|---|
| A2 | Timing and stall-share arithmetic is recomputed above from the committed G156a table: 450/791 = 0.569, 900/296 = 3.041, and 237/296 = 0.801. |
| A5 | Ledger, sidecar, and decode-manifest readers are surveyed above. |
| A7 | This memo, G156a, the contract, spec, result ledger, and register all exist at commit preparation. |
| B1 | No metric, eligible set, or exclusion changed. |
| B2 | No field was renamed or removed; adjudication_timed_out is additive and readers were checked. |
| B3/B4 | A timed-out adjudication is terminally recorded and its video is retained out of STAGE, so it is not silently dropped or re-claimed. |
| B5 | No pod file, process, daemon, or deployment was touched. |
| B6 | No module moved or retired. |
| B7/B8/B9 | No rendered sample, fit, or recycled metric is used. The timing denominator is the stated 4 eligible clips. |
| B10 | decode_manifest.py has a zero-line diff; no harness threshold, gate, coverage definition, coordinate contract, or verdict criterion changed. |

## NOT VERIFIED

- A real pod claim during a live post-change adjudication; the pod was strictly
  read-only and its running daemon was not restarted or deployed.
- A full 2.0-3.7 GB broadcast exact-count timing; G156a labels its production
  duration estimate as an extrapolation.
- Physical cancellation of a stuck Python thread. The bounded property is the
  terminal job/worker/sidecar exposure, exercised by the focused test.
