# G255: Independent amateur gate check

## Part one: committed blind re-judgement

This checkpoint was written and committed before I opened G253's top-level
`Verdict` text or its `Degeneracy check and independent render gate` section.
I first read the required G252 method, verifier contract, G253 source/method
material, and G253-VERIFIER-DENOMINATOR ledger row; then I opened the two
renders and recorded the calls below. G253's binding-control method paragraph
does state that its control passed, so the control call is documented as a
fresh constrained visual review but is not blind to that single textual claim.
The amateur call was made without reading any G253 amateur gate verdict.

| Render / input opened | Full path | Bytes | Resolution | SHA-256 | Withheld geometry reviewed only | G255 call |
|---|---|---:|---:|---|---|---|
| Amateur line-plus-conic | `docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact/amateur_line_conic_render.jpg` | 274661 | 1280x720 | `080d4925195c6a9e02c26c9b08cadef5a59017e1966fa08bf9a2682cb776c04a` | Left-end three-point arc and painted-end markings; excluded fitted far sideline, centre line, and centre circle | **CANNOT JUDGE** |
| WNBA lines-only control | `docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact/control_lines_only_render.jpg` | 656890 | 1920x1080 | `71eb4f39ec4b8f460a5650d259e3db5bb463f141c8ee8dcd972c263f1f852bc5` | Near-end withheld three-point curve / visible sideline only; excluded fitted near baseline, lane boundaries, and near free-throw line | **PASS** |

The amateur withheld arc and painted-end evidence is too faint, occluded, and
visually ambiguous at this render scale to support a PASS or a FAIL from this
additional labeller. The WNBA control call deliberately ignores the extensive
off-court full-model projection, which is expected in this hoop-end view.

The numerical withheld-geometry measurement and G253 agreement statement are
added only after this committed checkpoint.

## Part two: fixed withheld-geometry normal offsets

After committing `ce9b75318d98684ea30a85784c3f84f590a01cbc`, I read G253's
gate text. G253 called both the control and amateur renders `PASS`. Thus the
control call agrees, while the amateur call **DISAGREES**: G255 is `CANNOT
JUDGE`, not `PASS`.

The measurement uses
`scripts/platformkit/tracking/g255_amateur_gate_independent_check.py` and
reuses G252's landed normal-offset machinery, with the same 4-px projected
sampling, Canny `(low=50, high=150, aperture=3, L2gradient=True)`, and
integer normal search from -24 through +24 px. The G252 committed route is
commit `e7c880287206abfb37b1d8d4f2e127df3b7926ca`, content SHA-256
`0f1ea9e2b7d6ac9636bdcde50fc2c5cd139f1a734eaa083939d91f0c78d968af`;
the current worktree has no diff from that committed route. No map, input,
model, label, or threshold was changed.

For the amateur, the sampled geometry is only the left-end three-point curve
and its corner legs, plus the left-end baseline, lane boundaries, and
free-throw line. The fitted far sideline, centre line, and centre circle have
zero samples in this report. For the control, the sampled geometry is only the
near three-point curve/corner legs and both withheld sidelines; its fitted near
baseline, lane boundaries, and near free-throw line have zero samples here.

Each reported distance is conditional on finding at least one Canny strong-edge
candidate. Every no-candidate sample stays in its named denominator. A found
24-px value is right-censored: the actual offset can be larger, and an absent
candidate can mean either no detected strong edge or an offset beyond 24 px.
Neither outcome is evidence of a small offset. A candidate can also be a logo,
bench/crowd edge, or another non-marking edge rather than painted court ink.

| Footage / fit | Frames | Withheld sample points | Found | No candidate | Median px | P90 px | Censored max px |
|---|---:|---:|---:|---:|---:|---:|---:|
| WNBA seeded points (G252 VALID) | 27 | 565510 | 43530 | 521980 | 5.0 | 19.0 | 24.0 |
| WNBA lines-only control (G255) | 1 | 689 | 414 | 275 | 5.0 | 16.0 | 24.0 |
| Amateur line-plus-conic (G255) | 1 | 80 | 63 | 17 | 12.0 | 18.0 | 24.0 |

| G255 fit | Withheld group | Samples | Found | No candidate | Median px | P90 px | Censored max px |
|---|---|---:|---:|---:|---:|---:|---:|
| WNBA lines-only control | Near three-point curve and corner legs | 485 | 363 | 122 | 5.0 | 16.0 | 24.0 |
| WNBA lines-only control | Both sidelines | 204 | 51 | 153 | 5.0 | 15.0 | 23.0 |
| Amateur line-plus-conic | Left-end three-point curve and corner legs | 75 | 60 | 15 | 12.5 | 18.2 | 24.0 |
| Amateur line-plus-conic | Left-end painted-end markings | 5 | 3 | 2 | 3.0 | 3.8 | 4.0 |

The WNBA lines-only control is numerically close to G252's seeded WNBA result
at the median and has a somewhat lower p90. The amateur pooled median is more
than twice either WNBA median, though its p90 is within the same censored range.
The paint subgroup has only five in-image samples, so it cannot override the
arc's ambiguous visual evidence. These are detector-conditioned pixel offsets,
not ground-truth calibration error.

## Verdict and limits

**DISAGREES / NOT REPLICATED:** across 2 renders, 1 frame per render, and 1
additional labeller, G255's amateur withheld-geometry judgement is `CANNOT
JUDGE` where G253 reported `PASS`. The control is `PASS` in both rows, but the
amateur headline cannot be reported as replicated by an independent labeller.
G253's amateur `PASS` must be re-stated as a single-labeller one-frame render
judgement, or retracted; this row does not repair it. After this row the
amateur record has 2 labellers on 1 frame, which is a disagreement/replication
attempt, not a reliability measurement.

The amateur model is assumed rather than physically measured: an offset against
its 84x50-ft model inherits that assumption. One frame per footage class is not
a population result. This consumes manual geometry and is not automatic
calibration, which remains 0/17. G242, G244, G247, and G248 remain controlling:
no fitted residual or match statistic indicates correctness.

## Lane check, disk guard, verification, and NOT VERIFIED

At the G255 start on 2026-09-04 America/Chicago, the process check excluded
this process, its checker, and the checker's parent ancestry. It found G254 in
a5; that lane was not interrupted. `df` was not used. Before any G255 evidence
write, `du -sm /workspace/nba-ai-system/data` was **33121 MB** and
`dd if=/dev/zero of=/workspace/.g255_dd_probe bs=1M count=8 conv=fsync
status=none` succeeded. The 8,388,608-byte probe was removed. No corpus source,
G253 artifact, or abandoned `footage_bridge` partial was deleted. No worker
temporary artifact was created. The focused local test created then deleted two
G255 Python bytecode files (9033 and 2745 bytes), so total temporary bytes
freed were **8,400,386**.

Input identities for the numerical run:

| Input opened | Full path | Bytes | Resolution | SHA-256 |
|---|---|---:|---:|---|
| Amateur frame | `docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact/amateur_frame_0540.jpg` | 254981 | 1280x720 | `e09bd6cdd65404ea048967b7eaf2d6f217013a269fe9331b0e579113ff611dd8` |
| Control frame | `docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact/control_seed_frame_19599.jpg` | 623569 | 1920x1080 | `27a54f61e76a8c759fb412b0998d1c3be02b87a92557702bb043162bf61e5d36` |
| Amateur persisted map | `docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact/amateur_fit_measurement.json` | 674 | n/a | `1c725599a5e456db818558d95163a95162479a0425d44594a526d75d2a91c45d` |
| Control persisted map | `docs/evidence/tracking/g253_line_and_conic_calibration_2026-09-04_artifact/control_measurement.json` | 1961 | n/a | `faf98ec5679bf8a973f6fa8aa2a586109896442e85d52520253fbee6b53f5d3c` |
| G255 output | `docs/evidence/tracking/g255_amateur_gate_independent_check_2026-09-04_artifact/g255_measurement.json` | 19337 | n/a | `673161b934aabd82bf837ad71b8024368949bce8dd50cb88038f4d46357b2810` |

Focused test:

```text
python -m pytest scripts/platformkit/tracking/test_g255_amateur_gate_independent_check.py -q -p no:cacheprovider
3 passed in 3.03s
```

I independently recomputed the two pooled summaries directly from the retained
distance arrays: amateur `63 found + 17 no candidate = 80 samples`, median
12.0, p90 18.0, max 24.0; control `414 + 275 = 689`, median 5.0, p90 16.0,
max 24.0. A7 evidence paths named here exist. B1 retains every no-candidate
sample; B2-B6 add no production schema, lifecycle, deployment, or move; B7 has
two enumerated one-frame renders rather than a head slice; B8 samples only
withheld image geometry; B9 names both frame and point denominators; and B10
changes no existing threshold or gate. Q does not apply.

**NOT VERIFIED:** semantic identity of any Canny candidate; uncensored offsets
beyond 24 px; line visibility when no candidate is found; physical amateur
court dimensions; a ground-truth amateur map; independent blind reliability;
generalisation beyond one frame per footage class; automatic calibration;
tracking/player accuracy; or any production change.
