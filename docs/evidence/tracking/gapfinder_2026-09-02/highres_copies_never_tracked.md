# The high-resolution copies have never been tracked (2026-09-02)

Read-only on the pod. Corpus names (`data/footage_corpus/*.mp4`, sport prefix
stripped) intersected against the distinct `game_id` values in
`data/tracking/track_daemon_ledger.jsonl` (395 rows, 182 distinct game_ids).

## The number

5 of 61 corpus clips have ZERO ledger rows, and they are exactly the five
high-resolution sibling copies:

    ncaa_basketball_IB-_u4gW3ds_1080p
    npb_01_720p
    soccer_kSgNjoaqCpI_1080p
    tennis_nyYk2nPZAwY_720p
    wnba_01_1080p

Each has a lower-resolution sibling of the same match that DOES have ledger
rows (`ncaa_basketball_IB-_u4gW3ds` 640x360, `soccer_kSgNjoaqCpI` absent,
`tennis_nyYk2nPZAwY` 640x360, `wnba_01` 1280x720). So every daemon-produced
table for those matches comes from the lower-resolution copy, while the
hand-run evidence memos (G05 sequential coverage 0.8970 on
`tennis__tennis_nyYk2nPZAwY_720p.mp4`; the 1080p control) measure the copy the
daemon has never touched. The two production paths do not share a source file.

## The copies are not frame-index aligned either

`tennis_nyYk2nPZAwY`: the 360p copy is 24,024 frames at 25.0 fps (961 s); the
`_720p` copy is 48,048 frames at 50.0 fps (961 s). Same wall clock, 2x frame
index. A harness plan expressed as `--range 15300 15600` is t = 306.0-312.0 s
on the 720p copy and t = 612.0-624.0 s on the 360p copy: two different rallies.

The same mismatch, with different durations rather than different fps:

| match | low copy | high copy |
|---|---|---|
| football_wHZt1eY3A9s | 28,904 fr @ 30 (963 s) | 9,124 fr @ 30 (304 s) |
| ncaa_basketball_IB-_u4gW3ds | 28,905 fr @ 30 (963 s) | 18,115 fr @ 30 (604 s) |
| wnba_01 | 28,861 fr @ 30 (962 s) | 18,060 fr @ 30 (602 s) |

`compute_liveness_metrics` already reports `liveness_verdict UNCALIBRATED`
because no source time base is declared; this is the cost of that.

## Achievable limit

Enqueue the five high-res copies so the daemon and the evidence memos share a
source, and express plan ranges in seconds against a declared source fps
instead of raw frame index. The limit is one ledger field (`source_fps`) plus
a seconds-to-frames conversion at plan build; no threshold moves.
