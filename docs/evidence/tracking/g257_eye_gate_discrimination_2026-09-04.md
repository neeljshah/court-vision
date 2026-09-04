# G257: amateur eye-gate discrimination

**EYE-GATE RESOLUTION: 20 px of the stated synthetic projected-court translation on this footage. Candidate call: CANNOT JUDGE.** The blind labeller marked +20, +40, and +100 px FAIL, and the unchanged candidate plus +5 and +10 px CANNOT JUDGE. This is the current programme-wide eye-gate resolution constraint: an eye-only claim below this 20 px stimulus on this footage is unsupported without another discrimination measurement. It is not a population threshold or calibration acceptance bar.

G253 called this amateur render PASS; G255 called the same withheld geometry CANNOT JUDGE because the evidence was faint, occluded, and ambiguous at the old scale. The amateur headline remains retracted and unresolved. G257 measures the instrument, not the map, and follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`.

## Inputs, lane check, and disk guard

The G257 lane began at 2026-09-04 07:31:10 CDT. Before writing G257 evidence, the exact executable-and-argument process census excluded the full G257 launcher ancestry, this checker, and the checker's parent. It found one other tagged lane, G256 in `C:\Users\neelj\nba-track-a5`; it was not interrupted. This is the permitted two-lane state.

| Input opened | Full path | Bytes | Resolution | SHA-256 |
|---|---|---:|---|---|
| Amateur frame 540 | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g253_line_and_conic_calibration_2026-09-04_artifact\amateur_frame_0540.jpg` | 254981 | 1280x720 | `e09bd6cdd65404ea048967b7eaf2d6f217013a269fe9331b0e579113ff611dd8` |
| Persisted G253 map | `C:\Users\neelj\nba-track-a6\docs\evidence\tracking\g253_line_and_conic_calibration_2026-09-04_artifact\amateur_fit_measurement.json` | 674 | n/a | `1c725599a5e456db818558d95163a95162479a0425d44594a526d75d2a91c45d` |

The candidate is that exact persisted G253 homography. Its SHA-256 matches G255's input record. It was read and rendered unchanged; G257 did not re-fit, relabel, tune, write a map, or change a threshold, court model, coordinate contract, corpus, `src/`, or `domains/` file.

`df` was not used. The remote guard recorded `du -sm /workspace/nba-ai-system/data` = 33135 MB, then wrote 8,388,608 bytes with `dd if=/dev/zero of=/workspace/.g257_dd_probe bs=1M count=8 conv=fsync status=none` and removed that exact probe. The focused test created two G257 bytecode files (6252 + 3054 = 9306 bytes), which were removed. Temporary bytes freed: 8,397,914 total. No corpus source, G253 or G255 artifact, or either abandoned `footage_bridge` partial was deleted.

## Judgeable render and stated perturbation

Every board keeps the full native 1280x720 frame as a 1:1 main panel, with no main-panel resize. A 390-pixel lower strip carries enlarged withheld-only crops, yielding a 1280x1110 JPEG:

| Inset | Main-panel rectangle `(x, y, width, height)` | Withheld evidence |
|---|---|---|
| Left-end three-point arc | `(0, 190, 500, 300)` | Left-end arc and corner legs |
| Painted-end markings | `(0, 300, 390, 250)` | Baseline, lane boundaries, and free-throw marking |

Yellow overlay style is identical in every board. The six JPEGs occupy 1,979,818 bytes and all nine retained artifact files occupy 1,984,725 bytes. This retains a native-scale main frame and useful insets while keeping the committed set near 1.98 MB rather than storing video or lossless duplicate frames.

Let `H` be the unchanged G253 image-to-court map and `P = inverse(H)` its court-to-image projection. Candidate condition is exactly `P`. For a ladder condition `N`, G257 rendered `P_N = T(N, 0) P`, where `T(N, 0)` translates N image pixels to camera right, then used `inverse(P_N)` only for that perturbed render. Every finite projected court point therefore moves exactly N horizontal image pixels. The ladder is 5, 10, 20, 40, and 100 px, spanning G255's 12.0 px median and 18.0 px p90 detector-conditioned offset through an obvious displacement.

This is a defined overlay stimulus, not a real calibration error of N px. A real map error changes with position and perspective and can shear or rotate. The candidate is not known-correct, so separation from synthetic perturbations is consistent with correctness at most; it never proves it.

## Blind checkpoint, unblinding, and result

The renderer assigned opaque boards with `secrets.SystemRandom`. I reviewed only `blind_board_01.jpg` through `blind_board_06.jpg`, which contained opaque board numbers only. The randomized order and all six blind verdicts were committed in `9f65b28f53e4adf6f6f19174a0b6ab1f49286430` before I opened `unblind_key.json`; that checkpoint deliberately excludes the key. The order and verdicts were therefore committed before unblinding, as in G255.

| Condition after unblinding | Opaque board | Blind verdict |
|---|---|---|
| Candidate unchanged, 0 px | `blind_board_01.jpg` | CANNOT JUDGE |
| Translate right 5 px | `blind_board_03.jpg` | CANNOT JUDGE |
| Translate right 10 px | `blind_board_06.jpg` | CANNOT JUDGE |
| Translate right 20 px | `blind_board_04.jpg` | FAIL |
| Translate right 40 px | `blind_board_02.jpg` | FAIL |
| Translate right 100 px | `blind_board_05.jpg` | FAIL |

The headline measurement is **20 px**, the smallest known synthetic perturbation marked FAIL. Denominator: 1 frame, 1 candidate, 5 perturbation magnitudes, 6 boards, 1 footage class, and 1 labeller. The candidate separates from the +20/+40/+100 stimuli, including +40 or more, so the eye gate is not uninformative at 40 px on this footage. But the candidate itself is CANNOT JUDGE, not PASS; the amateur question cannot be settled by looking at this frame.

This does not reverse G242, G244, G247, or G248: fitted or matched statistics do not show correctness. G254 showed an optimizer can improve its own objective while moving the court off markings and failing the eye gate. No calibration verdict, physical dimension, or production change follows; automatic calibration remains 0/17.

## Evidence, checks, and limits

Retained evidence: the six boards, `g257_eye_gate_discrimination_2026-09-04_artifact/blind_order.json`, `g257_eye_gate_discrimination_2026-09-04_artifact/blind_verdicts.json`, and `g257_eye_gate_discrimination_2026-09-04_artifact/unblind_key.json`. Renderer SHA-256: `dc7f8e49e6473f5fe0aa769f610eea0c53a7d6a93b9cdf3034b4b412b06e14fb`; focused-test SHA-256: `7c7abd09e9e08f5832f9cf19b808d63a55a756def0e4480e828f9e65f6124b2c`.

```text
python -m pytest scripts/platformkit/tracking/test_g257_eye_gate_discrimination.py -q -p no:cacheprovider
3 passed in 2.02s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed in 2.23s
```

A7: every named evidence path exists. B1: every member of the enumerated six-board set is retained; no verdict is excluded. B2-B6: no schema, lifecycle, deployment, production module, or move changed. B7: the entire enumerated decision set is shown, not a head slice. B8: no fitted residual or input geometry is independent evidence. B9: all boards and denominators are named. B10: no bar or threshold moved. Q does not apply. A12: the new renderer is 117 lines and test is 27 lines, neither is allowlisted or over 300 lines; the per-file LOC rail passed.

**NOT VERIFIED:** a ground-truth amateur map; physical dimensions; whether 20 px synthetic translation corresponds to real calibration error; repeatability; blind agreement; any population eye-gate resolution; another frame, camera, sport, or footage class; automatic calibration; tracking/player accuracy; a production change; or a PASS for G253's candidate. One frame, one footage class, and one labeller are not a population property. Eye-label reliability has not cleared 80 percent blind agreement on the programme's four measured criteria, and G246 showed repeatable labels can be uniformly wrong.
