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
