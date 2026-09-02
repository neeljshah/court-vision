# G112 wide-footage acquisition audit

**Verdict: NOT VALIDATED.** This is an honest acquisition-limit result, not a
claim that no alternative footage can clear the four-constraint requirement.
The requested camera types exist, but this worktree's existing bridge could
not anonymously acquire a valid soccer, football, or baseball decision set
under G112's no-cookie/no-credential rule. It follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including section A and A7;
section B is self-checked below.

## Fixed method

The consolidated `REACH` row says ordinary broadcast is camera-bound:
soccer/football cap at two independent directions, and baseball's four-point
view was rare overhead footage. Before any candidate footage was opened, G112
fixed its 20-stratum seed `1122026`, its semantic point/line rules, and the
G101/G104/G106 direction-family rule in
[`g112_wide_footage/label_protocol.md`](g112_wide_footage/label_protocol.md).
Parallel paint is never promoted to independent constraints. No threshold,
coordinate contract, bridge, queue, cookie, credential, or pod state changed.

## Candidate types and acquisition result

| ID | Sport | Camera and publisher type | Public status | Example / acquisition outcome | Census result and plain verdict |
|---|---|---|---|---|---|
| S1 | soccer | Elevated tactical full-match archive, independent scouting/archive uploader | Public player page | `nLRe7AlSM7g`, a tactical-camera full match. Existing bridge local acquisition with a deliberately nonexistent cookie path left only partial files; an independent two-second bridge-compatible section returned HTTP 403 at ffmpeg. | **NOT MEASURED; NOT VALIDATED.** Public playback did not become bridge-acquirable footage. |
| S2 | soccer | Fixed elevated Veo match recording, team/academy publisher | Conditionally public | Veo permits no-account viewing only after a team admin makes and shares a recording's public link; shared viewers cannot download. No released example URL was supplied. | **NOT MEASURED; NOT VALIDATED.** Requires a team-issued public link and an acquisition route compatible with view-only Veo. |
| S3 | soccer | Professional tactical analysis feed, rights/analytics publisher | Subscription-gated | Wyscout's paid plans and service terms govern video access; no credentials were added. | **NOT MEASURED; NOT VALIDATED.** Requires licensed access/export authorization. |
| F1 | football | SkyCast/overhead alternate broadcast archive, public-video uploader | Public player page | `UNyLHlZr-bI`, Georgia vs Alabama SkyCast. A two-second bridge-compatible anonymous section returned HTTP 403 at ffmpeg. | **NOT MEASURED; NOT VALIDATED.** No bridge-acquired decision set. |
| F2 | football | NFL All-22 coaches film, NFL publisher | Subscription-gated | NFL lists All-22 with NFL+ Premium. | **NOT MEASURED; NOT VALIDATED.** Requires a subscription and permitted export; neither was used. |
| F3 | football | High-sideline/end-zone Hudl coaches film, school/team publisher | Recipient/share-gated | Hudl organizational terms describe sharing to organization-designated recipients. | **NOT MEASURED; NOT VALIDATED.** Requires an authorized team share/export. |
| B1 | baseball | Fixed center-field local-game stream, local league uploader | Public player page, sport unverified | `ZtsLAC-DiBo` yielded a valid anonymous section. Twenty seeded frames span its full 6,438-second duration and are committed. All remain a fixed home-plate view, but the title and footage do not establish baseball rather than another diamond sport. | **NOT SCORED; NOT VALIDATED.** It cannot be silently counted as baseball. |
| B2 | baseball | GameChanger elevated team stream, team/league publisher | Conditionally public | GameChanger allows an `Anyone` stream link, while archived full-event access can depend on audience, team relationship, and plan. No public qualifying full-event URL was supplied. | **NOT MEASURED; NOT VALIDATED.** Needs a team-issued public link and bridge-supported media path. |
| B3 | baseball | Professional overhead/whole-infield special feed, rights holder | Rights-gated | MLB.TV supplies subscription live/on-demand games; no public continuous overhead feed was found. | **NOT MEASURED; NOT VALIDATED.** Requires an explicit public full-camera release or licensed access. |

The detailed register, exact URLs, and requirements are in
[`g112_wide_footage/candidate_register.csv`](g112_wide_footage/candidate_register.csv);
the local attempt log is
[`g112_wide_footage/acquisition_log.md`](g112_wide_footage/acquisition_log.md).
Access-policy sources are recorded in
[`g112_wide_footage/source_access_notes.md`](g112_wide_footage/source_access_notes.md).

## Seeded eye check: B1 content stop

B1 is the only URL from the public examples that produced local sections
without a cookie. Its deterministic sample has 20 unique `(B1, source_frame)`
pairs, one from each equal temporal stratum, seed `1122026`; the source is
640x360 at 30 fps. The reviewed full-set contact sheet and all 20 individual
frames are committed under
[`g112_wide_footage/B1/`](g112_wide_footage/B1/). The per-frame result is
[`content_audit.csv`](g112_wide_footage/B1/content_audit.csv): every sampled
frame is a fixed home-plate view, but no frame is used to label baseball
points, directions, or a >=4-point share because source sport identity is not
verified. This is a content-identity stop, not a zero numerator.

## What the bridge would need

- S1 and F1: a public media path the existing bridge can actually download
  anonymously. Their player pages alone are insufficient; the observed 403 is
  recorded rather than worked around with a cookie.
- S2 and F3: an organizer-issued public share link, plus an existing-bridge
  compatible downloadable media path. No account creation, token, or cookie
  workaround is authorized.
- S3, F2, and B3: a licensed rightsholder export or explicit public full-feed
  release. Stop there; no downloader or credentials were added.
- B2: an `Anyone` GameChanger share URL for a qualifying full event and a
  bridge-supported public media path.
- B1: a source whose sport is independently identifiable as baseball before
  its geometry can enter a baseball denominator.

## NOT VERIFIED

- No candidate has a valid >=20-frame soccer, football, or baseball
  reachability census. Consequently, no independent-direction distribution,
  >=4-point share, or four-constraint pass/fail can be reported for any sport.
- This does not prove that tactical, all-22, SkyCast, Veo, GameChanger, or
  overhead footage could not clear four constraints. It only establishes that
  this bridge/no-cookie acquisition pass did not produce an eligible decision
  set.
- No homography, detector, downloader, queue, credential, cookie, coordinate
  declaration, or pod process was changed.

## Verifier self-check

### Section A

- **A1:** no code was added, so G112 has no per-file test to re-run.
- **A2:** recomputation from `candidate_register.csv` finds nine unique
  candidate IDs (three per sport), three public-player examples, zero valid
  sport-specific reachability decision sets, and twenty unique B1 content-audit
  frames. No metric is quoted without its source record.
- **A3:** B1's 20 frames cover all 20 temporal strata, not a head slice; the
  only eye result is its source-content stop. Other candidates have no renders
  because their footage was not obtained.
- **A4:** the B1 audit has 20 rows and 20 unique `(candidate_id, source_frame)`
  pairs. Candidate IDs are also unique.
- **A5:** no production field or reader changed; there are no readers to grep.
- **A6:** this lane creates additive evidence only. Its explicit-path commit is
  made in a3; verifier archive/landing remains a verifier action.
- **A7:** every evidence path named in this memo exists at memo time. A missing
  path would make this result NOT VALIDATED, never a silent pass.

### Section B

- **B1:** no denominator was filtered into a success metric. B1's source
  identity stop is named, and all twenty seeded rows remain present.
- **B2:** no schema, field, status, or reader changed.
- **B3/B4:** no gate, queue, quarantine, claim, or retry behavior changed.
- **B5:** no pod file was copied and no deployment/process action occurred.
- **B6:** no module moved or retired.
- **B7:** the only reviewed decision set spans all twenty temporal strata.
- **B8:** no fitted residual or self-fit validation is claimed.
- **B9:** units are explicit candidate/source-frame pairs; no recycled unit is
  used.
- **B10:** all thresholds, coordinate rules, and prior reachability results are
  untouched.
