# G192 existing-homography score - FALSIFIED before measurement

**Verdict: FALSIFIED. No solver measurement was run.**

This row was stopped at the mandatory S2 premise re-confirmation, before a
pod connection, solver invocation, harness creation, or any change to `src/`.
The dispatch required that all 68 targets and all 17 committed source decodes
were 640x360. That premise is false in the fixed target construct itself.

## Fixed-construct census

- Target file: `docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`
- SHA-256: `9EDE0561441A062125BB708EE4496E7D22786608872E345D4079C70113000096`
- Rows: 68 targets over 17 frames.
- Resolved JPEGs: 17 of 17 exist. CSV dimensions and native JPEG dimensions
  agree for every frame (zero CSV/JPEG dimension mismatches).
- Actual resolution distribution: 1 frame / 4 targets at 640x360; 12 frames /
  48 targets at 1920x1080; 4 frames / 16 targets at 1280x720.

The 64 targets outside 640x360 are not exclusions: they make the stated
all-640x360 input premise false. Applying an unrequested resize, rescaling the
labels, or silently scoring a mixed-resolution construct would change the
measurement specified in the dispatch.

## Inputs resolved from `source_decode`

| Audit ID | Full JPEG path | Native resolution | Targets |
|---|---|---:|---:|
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg` | 640x360 | 4 |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg` | 1280x720 | 4 |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg` | 1280x720 | 4 |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg` | 1920x1080 | 4 |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg` | 1920x1080 | 4 |
| `wnba__wnba_01_1080p__s01__f001600` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s01__f001600.jpg` | 1920x1080 | 4 |
| `wnba__wnba_01_1080p__s03__f004062` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s03__f004062.jpg` | 1920x1080 | 4 |
| `wnba__wnba_01_1080p__s06__f007539` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_01_1080p__s06__f007539.jpg` | 1920x1080 | 4 |
| `wnba__wnba_02__s11__f021983` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_02__s11__f021983.jpg` | 1280x720 | 4 |
| `wnba__wnba_04__s06__f012223` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_04__s06__f012223.jpg` | 1280x720 | 4 |
| `wnba__wnba_06__s03__f007237` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s03__f007237.jpg` | 1920x1080 | 4 |
| `wnba__wnba_06__s07__f014099` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s07__f014099.jpg` | 1920x1080 | 4 |
| `wnba__wnba_06__s09__f018997` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_06__s09__f018997.jpg` | 1920x1080 | 4 |
| `wnba__wnba_07__s08__f016801` | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g130_recensus\source_decodes\wnba__wnba_07__s08__f016801.jpg` | 1920x1080 | 4 |

## Unrun measurements

No target was excluded. Rather, all 68 remain in the unsatisfied construct.
Therefore the following are **NOT MEASURED**, not zero or pass/fail values:

- Existing-solver per-target reprojection errors, pooled median, p90, and count
  within the 11.39 px label-repeatability floor.
- Per-frame results and the count of solver-unsolved frames.
- B11 fresh-process, three-run homography stability.
- A11 pod route-file SHA-256 identities.
- Five evenly spaced labelled-versus-projected eye-check renders.

## NOT VERIFIED

- Whether the existing homography is within the 11.39 px label-noise floor.
- Whether basketball's coordinate-contract failure is solely a persistence
  choice.
- Any solver quality, calibration, coordinate-contract, threshold, gate, or
  verdict beyond this input-premise falsification.
- Any pod state: the pod daemon and keeper were not contacted, altered, waited
  on, restarted, or deployed over.

## Required correction before rerun

Authorize one explicit construct definition: either score each JPEG at its
native resolution against its native-pixel labels, or identify the committed
640x360 derivative JPEGs and provide their correspondingly scaled target CSV.
This memo makes neither transformation.

## Orchestrator landing note: the falsified premise was MINE, and the stop was right

**A2, recounted independently in master:** 1920x1080 -> 48 targets over 12 frames;
1280x720 -> 16 targets over 4 frames; 640x360 -> 4 targets over 1 frame. 68
targets, 17 frames. The lane's census reproduces exactly.

**How I got it wrong.** I ran `head -3` on the targets CSV, saw `640,360` on the
first data rows, and wrote "The decodes are 640x360" into the spec as a verified
premise. It describes **1 of 17 frames**. I authored contract clause S2 -- "verify
the premise before dispatch, not after" -- earlier the same day, and then broke it
by sampling three rows and generalising to sixty-eight.

**The lane was right to stop** under the letter of the dispatch, and right not to
silently score a mixed-resolution construct or apply an unrequested resize. Under
Q8 a falsified premise is a VALID result and the row closes without a fix.

**But the measurement is not blocked, and this is the important part.** The lane
also verified that CSV dimensions and native JPEG dimensions AGREE for every one
of the 17 frames -- zero mismatches. So each frame's labels are already in its own
native pixel space, and the score is well defined per frame at native resolution.
Only my blanket sentence was wrong, not the construct. G192b re-dispatches with
the real distribution stated and per-frame native scoring required.

**Rule consequence.** S2 as written says "check each premise against the code or
the live system". That is what I believed I did. The failure mode was checking a
SAMPLE and stating it as a property -- the same error as B11, one level up, in the
spec instead of the memo. S2 is amended: a premise about a SET is verified by
computing the distribution over the whole set, never by reading the first rows.
