# G139 decoded-frame denominator

## Result

**ACCEPT -- the check was too strict for ordinary MPEG-TS program metadata.**
At the read-only ledger snapshot, all **426** physical ledger rows were read.
Six rows, representing **six distinct games**, had
`decoded_frame_denominator` as their first failure head; all six also lay in
the current final 60 physical rows. The failures span KBO (2), NCAA basketball
(1), soccer (1), tennis (1), and WNBA (1), rather than a single sport or
source. They are tightly concentrated from 2026-09-02 21:52:34 UTC through
2026-09-03 01:30:36 UTC, i.e. the post-bridge-repair acquisition interval.
The complete row table is
[`affected_rows.csv`](g139_denominator/affected_rows.csv), with the raw count
snapshot and per-sport aggregation in
[`ledger_snapshot.json`](g139_denominator/ledger_snapshot.json) and
[`per_sport_counts.csv`](g139_denominator/per_sport_counts.csv).

Five of the six rows share the ffprobe line-count message. The remaining
tennis row has the separate, preserved cause `emitted frame index outside
decoded range: 24290`; it is included in the prefix metric but is not claimed
to be fixed by this change.

## Check quoted from the code

`track_daemon_done.adjudicate()` first calls `frame_counter(video)`, then
`build_decode_manifest(decoded, csv_path)`. The default `frame_counter` is
`decoded_frame_count()` in `scripts/platformkit/tracking/decode_manifest.py`:

```python
command = [
    ffprobe, "-v", "error", "-count_frames", "-select_streams", "v:0",
    "-show_entries", "stream=nb_read_frames",
    "-of", "default=nokey=1:noprint_wrappers=1", str(video_path),
]
result = subprocess.run(command, check=True, capture_output=True, text=True)
values = [line.strip() for line in result.stdout.splitlines()
          if line.strip() and line.strip() != "N/A"]
```

Before this landing, it required `len(values) == 1`. Thus it asks ffprobe for
`nb_read_frames` of selected `v:0`, removes blank and `N/A` output, and
requires exactly one remaining count line. `build_decode_manifest()` then
uses that decoder-supplied count as the frame denominator; CSV rows only mark
which in-range decoded frames were solved.

## Read-only reproduction and cause

On affected `soccer_cS4OpYJ0Pps`, the exact command exited 0 and produced:

```text
39000
39000
```

That is two identical numeric lines where the old code required one, so it
reproduces the ledger failure directly. The paired ffprobe stream inventory is
in [`ffprobe_reproduction.txt`](g139_denominator/ffprobe_reproduction.txt):
the source is `mpegts` and contains one AAC audio stream and one H.264 video
stream, index 1, with `attached_pic=0`; there is no second video, cover image,
or data stream. ffprobe exposes that selected stream in both the program and
top-level stream sections, and its default count writer emitted the same count
twice.

The named KBO game `kbo_8UMcAyU1pi0` is also retained and has the same normal
topology (one AAC stream plus one H.264 video stream, no attached image). Its
full-duration count was not used as a substitute for the named soccer
reproduction.

## Remedy

The decoder check remains a decoder-derived denominator and retains the
pre-existing `v:0` query. The small `decode_manifest.py` change accepts output
only when its set of non-empty, non-`N/A` values has cardinality one. Therefore
the duplicated `39000` result is accepted as one denominator, while no value,
non-numeric output, or two different values still fails. This is not a silent
"take the first output line" rule: a genuinely ambiguous two-count result
remains rejected. G139 observed one actual video stream, so it does not add a
multi-video selection rule; a future file with multiple candidate video streams
must have an explicit primary-stream rule rather than relying on `v:0`. The
new focused test reproduces the two-identical-line case and passed. The change
has **not** been copied to the pod or deployed; the live daemon and all
existing verdicts stay unchanged.

## Verifier-contract self-check

- A2: parsed all 426 physical ledger lines and recomputed six target rows and
  six unique `game_id` values from the evidence table; the per-sport total is
  also six.
- A4: the metric unit is a distinct `game_id`; each of the six target rows has
  a different game ID. The raw ledger-row count is separately reported.
- A5: all `decoded_frame_count` readers were grepped: the daemon adjudicator,
  `build_from_decoder`, and the function itself. The return type and call
  contract are unchanged; no ledger field or schema was changed.
- A7: every evidence path named in this memo exists at this self-check:
  `g139_denominator/affected_rows.csv`,
  `g139_denominator/ledger_snapshot.json`,
  `g139_denominator/per_sport_counts.csv`, and
  `g139_denominator/ffprobe_reproduction.txt`.
- B1: the metric includes every matching ledger row; no failed row was
  excluded. The tennis sub-cause is named rather than erased.
- B2-B6: no field/status rename, reader break, absent-evidence quarantine,
  claim lifecycle change, pod deployment, module move, or orphan was made.
- B7: no render or head-slice evidence is used; the required eye check is an
  actual affected-file ffprobe stream inventory.
- B8-B9: no fitted residual, reused unit, or degenerate denominator is
  reported.
- B10: no harness threshold, coordinate contract, gate, or verdict changed.

## NOT VERIFIED

- Whether each of the other four ffprobe-line-count failures has the same
  program/global duplicate representation; the named soccer reproduction is
  sufficient to establish the observed cause, but no broader media claim is
  made without opening each file.
- A policy for a file with multiple candidate video streams. The reproduced
  source has exactly one, and G139 deliberately does not make `v:0` a silent
  cover-image or multi-program selection policy.
- A correction for `tennis_08`'s out-of-range emitted frame index; it remains
  a separate denominator failure.
- Live-pod behavior after this landed code; deployment is deliberately outside
  this evidence task.
