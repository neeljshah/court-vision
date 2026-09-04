# G220b amateur footage local-slice acquisition - 2026-09-04

This record follows [the tracking verifier contract](VERIFIER_CONTRACT.md).
G220b is acquisition and classification only. Its required premise was
re-measured before any external command, local download, slicing command, pod
connection, or pod write.

## CLOSED AT LIMIT: required premise falsified

G220b and its dispatch state that `data/videos/youtube_cookies.txt` is zero
bytes, and use that condition to require a cookie-free whole-file download
followed by a local bounded slice. The actual local configuration is different:
the file `C:/Users/neelj/nba-track-a5/data/videos/youtube_cookies.txt` exists
and is **3,026 bytes** (mtime UTC `2026-09-01T18:54:15`). Its contents were not
opened or copied: the byte size alone falsifies the stated zero-byte prerequisite
and avoids exposing cookie material.

The user-directed condition is not a harmless label. The bridge selects its
client behavior from cookie-file presence, so running the required empty-cookie
workaround with this non-empty configuration would exercise a different route.
This row is therefore closed at the prerequisite limit rather than manufacture
a result under changed conditions. The pre-existing modified
`docs/evidence/tracking/specs/G220b_spec.md` was left untouched.

## Construct and outcome

The reviewed construct remains the six specified IDs, with no substitutions.
No candidate was contacted because the common prerequisite failed before the
first candidate. All counters below are observed zeros, not estimates.

| YouTube ID | Outcome | Local whole bytes | Local freed bytes | Slice upload bytes | Actual height | Content gate / five-frame rubric |
|---|---|---:|---:|---:|---|---|
| `jh3fnwMi7dM` | not attempted: prerequisite falsified | 0 | 0 | 0 | not acquired | not run: no slice |
| `qpZfGp_fScU` | not attempted: prerequisite falsified | 0 | 0 | 0 | not acquired | not run: no slice |
| `1MwO3CDkeeM` | not attempted: prerequisite falsified | 0 | 0 | 0 | not acquired | not run: no slice |
| `3asBuhRd_LI` | not attempted: prerequisite falsified | 0 | 0 | 0 | not acquired | not run: no slice |
| `lAs8JaoWNwg` | not attempted: prerequisite falsified | 0 | 0 | 0 | not acquired | not run: no slice |
| `XwpLBtt1G2g` | not attempted: prerequisite falsified | 0 | 0 | 0 | not acquired | not run: no slice |

Running local-download total: **0 B / 20,000,000,000 B**.

Running pod-upload total: **0 B / 4,000,000,000 B**.

Local whole-file cleanup freed **0 B**. Pod cleanup freed **0 B**. No whole
file, slice, partial file, frame, contact sheet, or pod artifact was created.

No pod command started, so there is no pod-load observation and no `dd
conv=fsync` or `du -sm /workspace/nba-ai-system/data` result. This is not a
missing guard: no upload was attempted for the guard to bracket. `df` was not
consulted. The pod daemon, keeper, bridge supervisor, watchdog, and existing
corpus were not contacted or changed.

## G213 baseline and scope

No acquired media means no `ffprobe`, no `ffmpeg -c copy`, no content-gate
call, and no five-frame eye classification. The content gate is an ingest
decision only and must never touch a metric denominator. Consequently G213's
exact zero-representation list is unchanged:

- Handheld game-camera footage.
- Fixed **single-camera** game footage. Tennis is a multi-camera broadcast that
  happens to use a fixed-wide primary play view, not a continuous single-camera
  source.
- Amateur/high-school direct field/court camera acquisition. The one
  amateur/home-produced item is a desktop-commentary screen capture, not an
  amateur game camera.
- Graphics-free footage.
- High playing-surface visibility under the stated typical-frame rubric.
- Dim-gym or otherwise visibly poor-lighting footage.
- Visibly non-standard physical playing surfaces. WNBA 02 supplies one unusual
  court colour treatment only; its markings and physical court remain standard.

There are no new classifications, so the single-labeller/no-second-labeller
qualification is inapplicable rather than omitted. No tracking, routing,
queueing, detection, calibration, robustness, or corpus-membership conclusion
is made.

## Verifier self-check and NOT VERIFIED

Section B self-check: B1 has no metric or excluded rows; B2-B4 make no schema
or gate change; B5 makes no pod deployment or copy; B6 moves no module; B7 has
no render set; B8 fits no model; B9 has no denominator; and B10 changes no
threshold. A7 passes: the only evidence path named by this memo is this memo,
which exists before commit. A12 does not apply because no allowlisted source
file grew. No test is applicable because this landing adds no harness or code.

Not verified: whether this non-empty cookie file is valid, whether its use
would change whole-file or section availability, whether any of the six IDs is
currently downloadable at any height, the actual heights or durations, any
content-gate verdict, any G213 label, any disk-headroom probe, and any future
tracking or corpus outcome. Those questions require an explicit refreshed
configuration decision; this record does not infer one.
