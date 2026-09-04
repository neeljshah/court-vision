# G209 footage heterogeneity census - 2026-09-03

## Scope and safety result

This is a metadata-only characterization of the current POD corpus. It made no
production-code change, decoded no video, used no GPU, did not invoke
`ffprobe -count_frames`, and did not touch the POD daemon, keeper, corpus, or
downloads.

Before any optional eye check, the local active-job log
`cx_g203_decode_determinism_bisect.log` was checked for an `EXIT:` line. None
was present. G203 was therefore still running and **no frames were extracted**
for this row.

The remote census used only this metadata command for each complete clip:

```sh
ffprobe -v error -show_streams -show_format -of json <clip>
```

## Construct denominator and exclusions

**Eligible denominator: 11 of 11 complete corpus clips.** All 11 eligible
MP4s under `/workspace/nba-ai-system/data/footage_corpus` returned a usable
video stream and format record. Their aggregate file size is 25,425,529,914
bytes (25.426 GB decimal; 23.679 GiB).

The two files under `data/footage_bridge` were deliberately excluded from the
eligible denominator because both are incomplete staging downloads, not
complete clips:

| Excluded staging file | Bytes | Reason |
|---|---:|---|
| `football__football_wHZt1eY3A9s.mp4.part` | 3,705,238,507 | Incomplete `.part` download |
| `mlb__mlb_gDv5xF2AA2E.mp4.part` | 77,552,640 | Incomplete `.part` download |

An adjacent `data/videos/tennis_smoke.mp4` file was observed while locating
the named corpus/staging roots. It is outside both roots and is a smoke fixture,
so it is not part of this construct denominator. No other corpus file was
excluded.

The eligible sport allocation is: WNBA 1, NCAA basketball 1, tennis 1, soccer
1, football 2, MLB 1, KBO 2, and NPB 2 (11 clips across 7 sports).

## Per-clip metadata

`Bit rate` is the format-level bit rate reported by `ffprobe`. `CFR by
metadata` means `r_frame_rate == avg_frame_rate`; it is not a decoded-frame
measurement. Each container reports the MP4-family format string
`mov,mp4,m4a,3gp,3g2,mj2`.

| Sport | Clip | Resolution | DAR | FPS (reported) | CFR by metadata | Video codec/profile | Bit rate (Mbps) | Duration (s) | Container | Audio | File size (bytes) |
|---|---|---|---|---|---|---|---:|---:|---|---|---:|
| KBO | `baseball__kbo_06.mp4` | 1920x1080 | 16:9 | 60000/1001 (59.940) | Yes | h264 / High | 5.789 | 887.494 | MP4 | Yes / opus | 642,203,161 |
| KBO | `baseball__kbo_07.mp4` | 1920x1080 | 16:9 | 60000/1001 (59.940) | Yes | h264 / High | 5.743 | 903.934 | MP4 | Yes / opus | 648,964,602 |
| NPB | `baseball__npb_02.mp4` | 640x360 | 16:9 | 30/1 (30.000) | Yes | h264 / Main | 0.523 | 13,706.368 | MP4 | Yes / aac | 895,692,406 |
| NPB | `baseball__npb_03.mp4` | 1280x720 | 16:9 | 30/1 (30.000) | Yes | h264 / High | 1.725 | 14,345.714 | MP4 | Yes / opus | 3,093,450,494 |
| Football | `football__football_Z8Ezd95NnjM.mp4` | 1280x720 | 16:9 | 30000/1001 (29.970) | Yes | h264 / High | 2.074 | 9,617.314 | MP4 | Yes / opus | 2,493,550,705 |
| Football | `football__football_yahhMkUWd7c.mp4` | 1280x720 | 16:9 | 30000/1001 (29.970) | Yes | h264 / High | 2.028 | 10,129.594 | MP4 | Yes / opus | 2,567,704,906 |
| MLB | `mlb__mlb_nLoG6gvC-Nk.mp4` | 1280x720 | 16:9 | 30/1 (30.000) | Yes | h264 / Main | 1.160 | 7,354.174 | MP4 | Yes / opus | 1,066,801,340 |
| NCAA basketball | `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 1920x1080 | 16:9 | 30000/1001 (29.970) | Yes | h264 / High | 4.178 | 6,855.014 | MP4 | Yes / opus | 3,580,059,573 |
| Soccer | `soccer__soccer_dnR5C6WLJI4.mp4` | 1920x1080 | 16:9 | 30/1 (30.000) | Yes | h264 / High | 3.236 | 8,340.034 | MP4 | Yes / opus | 3,373,680,742 |
| Tennis | `tennis__tennis_02.mp4` | 1920x1080 | 16:9 | 60000/1001 (59.940) | Yes | h264 / High | 4.080 | 8,101.714 | MP4 | Yes / opus | 4,131,436,578 |
| WNBA | `wnba__wnba_01.mp4` | 1920x1080 | 16:9 | 30/1 (30.000) | Yes | h264 / High | 4.034 | 5,814.354 | MP4 | Yes / opus | 2,931,985,407 |

## Whole-corpus distributions (n=11)

| Field | Distribution over every eligible clip |
|---|---|
| Resolution | 1920x1080: 6 (54.5%); 1280x720: 4 (36.4%); 640x360: 1 (9.1%) |
| Display aspect ratio | 16:9: 11 (100%) |
| Reported frame rate | 29.970: 3 (27.3%); 30.000: 5 (45.5%); 59.940: 3 (27.3%) |
| Frame-rate mode | CFR by `r_frame_rate == avg_frame_rate`: 11 (100%); metadata-signalled VFR: 0 |
| Video codec | h264: 11 (100%) |
| Video profile | High: 9 (81.8%); Main: 2 (18.2%) |
| Format/container | MP4-family `mov,mp4,m4a,3gp,3g2,mj2`: 11 (100%) |
| Audio presence | Present: 11 (100%); absent: 0 |
| Audio codec | opus: 10 (90.9%); aac: 1 (9.1%) |
| Format bit rate | Min 0.523 Mbps; median 3.236 Mbps; max 5.789 Mbps |
| Duration | Min 887.494 s; median 8,101.714 s; max 14,345.714 s |
| File size | Min 642,203,161 bytes; median 2,567,704,906 bytes; max 4,131,436,578 bytes; total 25,425,529,914 bytes |

## Footage classes: what is and is not represented

The directly measured zero-representation findings are blunt:

- **Variable-frame-rate footage: zero metadata-signalled examples (0/11).**
- **Portrait or non-16:9 footage: zero examples (0/11).**
- **Audio-free footage: zero examples (0/11).**

The corpus does have one sub-720p source, `baseball__npb_02.mp4` at 640x360.
It therefore does **not** support the statement that sub-720p footage has zero
representation. It is only one clip, however, not a robust sub-720p sample.

The following high-value content categories cannot honestly be assigned either
a positive count or a zero count from streams/format metadata alone: amateur or
high-school *capture style* (NCAA competition is not proof of amateur capture),
fixed single-camera footage, heavy scoreboard/graphics overlay, non-green or
non-standard playing surfaces/courts, and poor lighting. The required eye check
was skipped because G203 had not exited. Thus this census establishes no visual
coverage for those categories. In particular, it provides **zero verified
examples** of amateur/home-video capture or fixed single-camera capture; that
is an evidence gap, not a claim that such footage was visually ruled out.

The honest result is narrower than a robustness claim: present metadata varies
in resolution, frame rate, duration, and bit rate, but it is completely
homogeneous in aspect ratio, video codec, container family, audio presence, and
metadata-signalled frame-rate mode. Content-style heterogeneity remains
uncharacterized in this snapshot.

## Player-pixel-height arithmetic projection (not a detector measurement)

This section is an **ARITHMETIC PROJECTION FROM A CODE COMMENT**, not an
observation of players and not detector output. `src/pipeline/unified_pipeline.py`
lines 1007-1009 state that a 1280-wide broadcast has players about 50 px tall,
that `imgsz=480` yields about 19 px (below reliable detection), and that the
configured `imgsz=640` yields about 25 px.

For the requested resolution-only projection, hold the comment's 25 px at
1280-wide / `imgsz=640` baseline fixed and calculate:

```text
projected player height = 25 px * (clip width / 1280)
```

This deliberately ignores unmeasured camera distance, zoom, crop, player
position, letterboxing, and preprocessing behavior. Those omissions are why it
must not be read as measured player height.

| Clip | Native width | Projected player height at `imgsz=640` | Relation to 19 px reference |
|---|---:|---:|---|
| `baseball__kbo_06.mp4` | 1920 | 37.5 px | Above |
| `baseball__kbo_07.mp4` | 1920 | 37.5 px | Above |
| `baseball__npb_02.mp4` | 640 | 12.5 px | **Below** |
| `baseball__npb_03.mp4` | 1280 | 25.0 px | Above |
| `football__football_Z8Ezd95NnjM.mp4` | 1280 | 25.0 px | Above |
| `football__football_yahhMkUWd7c.mp4` | 1280 | 25.0 px | Above |
| `mlb__mlb_nLoG6gvC-Nk.mp4` | 1280 | 25.0 px | Above |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` | 1920 | 37.5 px | Above |
| `soccer__soccer_dnR5C6WLJI4.mp4` | 1920 | 37.5 px | Above |
| `tennis__tennis_02.mp4` | 1920 | 37.5 px | Above |
| `wnba__wnba_01.mp4` | 1920 | 37.5 px | Above |

One clip (1/11), `baseball__npb_02.mp4`, projects below 19 px at 12.5 px.
No clip falls in a 17-21 px near-threshold band under this arithmetic rule; the
next-lowest group is the four 1280-wide clips at 25.0 px. This is a first-class
robustness variable only as a hypothesis for later measurement, not a verdict
from this row.

## NOT VERIFIED

- The one-frame-per-clip eye check: skipped because G203 had no `EXIT:` line.
- Camera style, production tier, scoreboard/graphics load, playing-surface
  visibility or color, court/field standardness, and lighting quality.
- Actual player pixel heights, detector recall, or any tracking outcome.
- Whether equal `r_frame_rate` and `avg_frame_rate` detects every possible
  timestamp-level VFR construction; the statement here is only metadata-based.
- Completion, decodability, metadata, or content of the two excluded `.part`
  staging downloads.
- Any robustness conclusion beyond this 11-clip construct.

## Evidence-path check (A7)

The only new evidence path named by this memo is this file:
`docs/evidence/tracking/g209_footage_heterogeneity_census_2026-09-03.md`.
It exists in this worktree at verification time.
