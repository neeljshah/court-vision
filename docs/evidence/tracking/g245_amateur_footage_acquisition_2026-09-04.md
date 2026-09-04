# G245: Amateur Basketball Footage Acquisition

**VERDICT: ACCEPT.** A bounded amateur/high-school basketball section was acquired, visually checked, and retained in the declared corpus. It establishes only that test material exists, not calibration, detection, or tracking quality.

## Lane and premise check

G245 began on 2026-09-04 at approximately 04:43 America/Chicago in `C:\Users\neelj\nba-track-a6`, branch `track-a6`. Immediately beforehand, the executable-and-argument process check found `pythonw.exe` PID 18132 running `codex-sport a5 g241b_seed_horizon_to_failure`, cwd `C:/Users/neelj/nba-track-a5`. G241b was not interrupted; permanent residents were not touched.

G243's premise correction was confirmed before acquisition: the pod corpus held nine professional-broadcast clips and no amateur basketball source. Candidate page metadata says `Coaches Camera - Lorain High vs Bedford High School Boys' Varsity Basketball 1-25-22`, uploader `Lorain Schools TV20`, upload date 2022-01-26.

## Disk guard and candidates

The pod was used only for the declared corpus write and verification; source discovery, acquisition, decoding, and frame extraction were local. Before download/upload, this pod guard passed and its 1,048,576-byte output was removed:

```text
dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g245_disk_probe.bin bs=1M count=1 conv=fsync status=none
```

`du -sm /workspace/nba-ai-system/data` was 32,992 MB. No `df` result was used. Existing partials were measured but unchanged: `/workspace/nba-ai-system/data/footage_bridge/football__football_m8UWuQoflJo.mp4.part`, 4,999,500,276 bytes, 2026-09-04 03:25:21 UTC; and `/workspace/nba-ai-system/data/footage_bridge/baseball__npb_05.mp4.part`, 2,490,710,544 bytes, 2026-09-04 03:38:36 UTC.

One candidate was tried. Its format inventory exposed HLS video `232` (1280x720) and audio `233`. yt-dlp warned that the local cookie export might have rotated, but the explicit pair completed in 9.3 seconds; no stalled selector was retried.

| Candidate | Result | Reason |
|---|---|---|
| `jh3fnwMi7dM` | Retained | High-school gym basketball; wide near-fixed view and painted geometry visible across the committed sample. |

## Acquisition and media identity

Source URL: `https://www.youtube.com/watch?v=jh3fnwMi7dM`

```text
yt-dlp --cookies 'data/videos/youtube_cookies.txt' --merge-output-format mp4 --no-part --no-playlist -f '232+233' --download-sections '*00:20:00-00:22:00' -o 'data/videos/bridge/basketball__amateur_jh3fnwMi7dM.%(ext)s' 'https://www.youtube.com/watch?v=jh3fnwMi7dM'
```

The local staging output was uploaded through the landed `scripts/platformkit/footage_bridge.py` guarded `_upload_to_pod` route as a remote `.part`, then atomically moved to the corpus. The local staging video was deleted only after remote byte and media identity matched, freeing 24,523,745 bytes. No corpus source or abandoned partial was deleted.

| Field | Value |
|---|---|
| Exact corpus path | `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4` |
| Bytes | 24,523,745 |
| SHA-256 | `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea` |
| Resolution | 1280x720 |
| Frames | 3,601 decoded video frames (`ffprobe -count_frames`) |
| FPS | 30/1 (30 fps) |
| Duration | 120.100000 seconds |
| Download interval | source time 00:20:00 through 00:22:00 |

Remote `sha256sum` and `ffprobe -count_frames` reproduced every value above after the move.

## Suitability eye check

The five equally spaced committed images in [`g245_amateur_footage_acquisition_2026-09-04_frames/`](g245_amateur_footage_acquisition_2026-09-04_frames/) are at elapsed 0, 30, 60, 90, and 119 seconds (`t000.jpg`, `t030.jpg`, `t060.jpg`, `t090.jpg`, `t119.jpg`).

By eye, this is suitable for a next calibration attempt. Across the frames, painted baseline and sideline are visible; lane boundaries and free-throw geometry are clear; three-point arcs are visible at both ends; and the centre circle is visible in the wide midcourt views. The high elevated camera pans modestly to follow play but has no hard cuts or zooms in the retained section, so it is near-fixed rather than fully static. It is visibly an amateur/high-school gym broadcast rather than professional broadcast.

This is a single-labeller judgement, not a measurement. Eye-label reliability has not cleared 80 percent blind agreement for any of the programme's four measured criteria. Amateur is source description, not a controlled condition: camera height, framing, encoder, and resolution vary. Automatic calibration remains 0/17.

## Route identity and contract self-check

The local bridge files exercised were `scripts/platformkit/footage_bridge.py` SHA-256 `55358f81a2ae7666d07416975c7c5c35897db03f917a4379f69b544c6d4da23d` and `scripts/platformkit/section_fallback.py` SHA-256 `3e89d4771864bfdfd8f7038c9d61e48b14cdabaa6c69242f03f37afc8e782ac0`. No production code, test, harness, threshold, coordinate contract, daemon, keeper, `src/`, or `domains/` file changed, so no focused test was required and A12 does not apply.

Contract self-check: A7 names this memo, the five committed JPEGs, and the same-commit ledger row, all present before commit. B1 has no excluded metric; B2-B6 change no schema, lifecycle, deployment, module location, or production code; B7 uses evenly spaced rather than head-slice frames; B8 does not use fitted geometry or construction-zero drift; B9 has no recycled denominator; B10 changes no bar. Q does not apply to this acquisition row.

## NOT VERIFIED

- Automatic calibration, detection, tracking, player identity, or coordinate accuracy on this clip.
- Reliability of the single-labeller suitability judgement.
- Suitability beyond the retained 120.1-second interval, including later cuts or zooms.
- A controlled comparison of amateur with professional footage.

## Final corpus-presence proof

Final command: `ls -la /workspace/nba-ai-system/data/footage_corpus/`

```text
total 22882856
drwxrwxrwx  2 root root    3002181 Sep  4 09:51 .
drwxrwxrwx 14 root root    3003203 Sep  4 08:49 ..
-rw-rw-rw-  1 root root  570482444 Sep  4 02:52 baseball__kbo_10.mp4
-rw-rw-rw-  1 root root 2364316804 Sep  4 02:35 baseball__npb_04.mp4
-rw-rw-rw-  1 root root   24523745 Sep  4 09:50 basketball__amateur_jh3fnwMi7dM.mp4
-rw-rw-rw-  1 root root 3188876596 Sep  4 02:52 mlb__mlb_gDv5xF2AA2E.mp4
-rw-rw-rw-  1 root root 1066801340 Sep  3 19:19 mlb__mlb_nLoG6gvC-Nk.mp4
-rw-rw-rw-  1 root root 3580059573 Sep  4 00:39 ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4
-rw-rw-rw-  1 root root 2341768743 Sep  4 02:21 soccer__soccer_Z6NTDyxcODs.mp4
-rw-rw-rw-  1 root root 4131436578 Sep  3 19:31 tennis__tennis_02.mp4
-rw-rw-rw-  1 root root 3225784665 Sep  4 02:41 tennis__tennis_03.mp4
-rw-rw-rw-  1 root root 2931985407 Sep  3 19:36 wnba__wnba_01.mp4
```
