# G251: Calibratable amateur-source acquisition screen

**VERDICT: CLOSED AT LIMIT.** I screened four distinct amateur basketball
sources with short explicit-HLS sections. None supplies a same-frame set of
four distinct, named, unoccluded basketball painted intersections with
two-dimensional spread. No source was landed. The 4/4 screen-out result is
the result: calibratable amateur views were not found in this bounded,
deliberately wide-camera search; the criterion was not relaxed.

This is acquisition and verification only. It changes no production code,
threshold, coordinate contract, `court_points_for_sport` key, label file,
corpus source, `src/`, or `domains/` file. In particular, no homography, gate,
render, detector, or tracking run was performed.

## Prior evidence and lane check

I read the landed G245, G249, and G250 memos and
`VERIFIER_CONTRACT.md` before evaluating the candidates. G250 is controlling:
the retained coaches-camera amateur source has no same-frame four-point set;
its best three named points are collinear. Cross-frame combination was not
considered because the camera pans.

The row began in `C:\\Users\\neelj\\nba-track-a6` on branch `track-a6`.
An initial local process listing was too broad because it printed this row's
wrapper, so it is not used as lane evidence. Before the remote guard, the
corrected executable-and-argument check excluded this row and its checker and
found the active `pythonw.exe` launcher for
`--tag g248_projected_line_image_agreement` in
`C:\\Users\\neelj\\nba-track-a5`. G248 was the permitted other lane and was
not interrupted. No video was copied to the pod while that measurement lane
was live.

## Disk guard

`df` was not used. The required remote check passed before any potential pod
write:

```text
du -sm /workspace/nba-ai-system/data
33091  /workspace/nba-ai-system/data
dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g251_disk_probe.bin bs=1M count=1 conv=fsync status=none
rm -f /workspace/nba-ai-system/data/footage_bridge/.g251_disk_probe.bin
G251_DD_PROBE_PASS
```

The two protected abandoned partials were observed and not changed:
`baseball__npb_05.mp4.part` is 2,490,710,544 bytes and
`football__football_m8UWuQoflJo.mp4.part` is 4,999,500,276 bytes.

## Candidate screen

Each candidate is a distinct uploaded source, not another section of G245's
failed coaches camera. Every section targeted source time `00:20:00-00:20:20`.
The normal explicit HLS pair was `-f '232+233'`; Fairbanks did not expose 232,
so its available 720p HLS video rung `311+233` was used immediately rather
than waiting on a nonexistent selector. Contact sheets take one decoded frame
per four seconds and are the initial framing evidence.

| Candidate and source | Short local section | Screen outcome | Reason |
|---|---:|---|---|
| [MVHS vs Timpanogos Wide Angle 20250110](https://www.youtube.com/watch?v=CloCfLWhLJI), Jared Olsen | 5,064,995 bytes | Reject on framing screen | The wide court is visible, but the foreground bleacher crowd covers the camera-side boundary and near painted-end geometry. It does not present four identity-safe points. [Sheet](g251_calibratable_amateur_source_2026-09-04_artifact/mvhs_screen_contact_sheet.jpg) |
| [Fairbanks (varsity) at Mechanicsburg](https://www.youtube.com/watch?v=lRDuhk2T6dE), Jon Dunn | 5,128,332 bytes | Reject on framing screen | The elevated view shows a far sideline and central court, but the scorer-table/bench foreground obscures the camera-side boundary and painted-end crossings in every evenly spaced frame of the 20-second screen. [Sheet](g251_calibratable_amateur_source_2026-09-04_artifact/fairbanks_screen_contact_sheet.jpg) |
| [Dwight Morrow High vs Fort Lee High School Boys' Varsity Basketball](https://www.youtube.com/watch?v=ykh-IZ745TU), DMHS Athletics | 6,131,436 bytes | Reject on framing screen | The view is elevated but crops the camera-side playable boundary; visible centre and far-side markings do not supply near-side painted geometry. [Sheet](g251_calibratable_amateur_source_2026-09-04_artifact/dwight_morrow_screen_contact_sheet.jpg) |
| [Full court basketball game shot with insta360 camera](https://www.youtube.com/watch?v=eu37QzeJ1g4), X2GO | 4,032,209 bytes | Reject after identity review | This is the only screen with whole-court framing. Its exact frame contains overlapping black, white, green, and blue multi-use-gym markings, while players cover several plausible basketball junctions. I could not name four *basketball* painted intersections at unique pixels without guessing which marking system a crossing belongs to. G246 makes that ambiguity a stop, not a licence to fit. [Sheet](g251_calibratable_amateur_source_2026-09-04_artifact/insta360_screen_contact_sheet.jpg); [exact decoded review frame](g251_calibratable_amateur_source_2026-09-04_artifact/insta360_f0360.png) |

The final section's independently measured identity was 1280x720, 715 decoded
video frames, 30000/1001 fps, 20.052000 seconds, 4,032,209 bytes, SHA-256
`4fa6a42d1168063c69560c4dfb88f46d877797da54397ade2b4b3039db238a8eb`.
Frame `f0360` is zero-based in that section. It is retained as review evidence
only, not a corpus clip.

The final source gets no four point names, identity crops, quadrilateral area,
or point-to-other-three distance because there is no identity-safe four-point
set to measure. Reporting invented coordinates and then a large quadrilateral
would violate the acquisition criterion. Thus its conditioning result is
N/A, not a near-zero-spread pass or failure.

## Acquisition commands and cleanup

The command template used for the three normal HLS candidates was:

```text
yt-dlp --cookies data/videos/youtube_cookies.txt --merge-output-format mp4 --no-part --no-playlist -f '232+233' --download-sections '*00:20:00-00:20:20' -o 'data/videos/bridge/g251_screen_<name>.%(ext)s' 'https://www.youtube.com/watch?v=<id>'
```

Fairbanks used the same command with `-f '311+233'` because that source did
not offer 232. All four temporary videos were deleted locally; 20,356,972
bytes were freed (16,324,763 bytes for the first three rejects and 4,032,209
bytes for the identity-review reject). Exploratory review images totalling
3,038,423 bytes were also deleted. The five linked JPEG/PNG evidence files
remain in this commit. No video was uploaded, no corpus source was deleted,
and the existing `basketball__amateur_jh3fnwMi7dM.mp4` remains untouched.

There is deliberately no corpus identity or final `ls -la` proof: no source
met the acceptance criterion, so landing any of these files would contradict
G250. The landed `footage_bridge.py` was read but not invoked.

## Limitations and verifier-contract self-check

This is four sources and short sections, not a prevalence estimate. A passing
source would establish only test material meeting a necessary geometric
criterion, not calibration, detection, tracking, player identity, or coordinate
accuracy. Suitability and identity judgements are single-labeller eye
judgements. Eye-label reliability in this programme has not cleared 80 percent
blind agreement on the measured criteria, and G246 showed that repeatable
labels can still be wrong. "Amateur" is source description, not a controlled
condition. The court model remains assumed rather than measured; an oblique
uncalibrated view cannot establish physical court dimensions. Automatic
calibration remains 0/17.

A7: every linked contact sheet and exact review frame exists in this commit.
B1: all four attempted sources and their outcomes are named; no screen-out is
excluded. B2-B6: no schema, lifecycle, deployment, module move, or production
code changed. B7: each sheet is evenly sampled over its complete 20-second
section, rather than a head slice. B8: no fit or self-fit metric is reported.
B9: the denominator is four distinct source URLs, not repeated sections of
one camera. B10: G250's criterion and all bars are unchanged. Q does not apply
to this acquisition eye-measurement row. No harness or bridge code changed, so
no focused test or A12 adjustment is applicable.

## NOT VERIFIED

- A qualifying amateur camera outside these four sources or outside their
  sampled intervals.
- Four identity-safe basketball intersections in the multi-use-gym source;
  its framing alone is insufficient.
- Any calibration, gate, render, propagation, detector, tracking, or
  coordinate result on any candidate.
- A corpus landing: this row correctly retained none.
