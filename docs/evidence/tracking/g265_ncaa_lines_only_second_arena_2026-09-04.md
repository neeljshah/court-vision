**COMBINED GATE: NOT RUN / CLOSED AT LIMIT (n=1 clip, 300 chronological survey frames, 0 legal four-line frames, 0 fitted frames, 0 boards, 1 labeller).** The re-screen found no frame with four independently identifiable directly observed painted lines. Therefore G253's unchanged lines-only solver, the blind ladder, and withheld offsets were not run.

# G265: NCAA lines-only second-arena screen

This measurement-only row follows the verifier contract. It changes no production code, label, threshold, court-model key, coordinate contract, `src/`, or `domains/` file. The existing NCAA contract remains 94x50 ft with a 12-ft lane and 19-ft paint depth; no WNBA lane was used.

## Source and corrected disk guard

The Pod source `/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` measured 3,580,059,573 bytes and SHA-256 `9b35bd59d8b5b0e04737389b6661d7f8d37fac07a348056b081a6815ff5eea40`, matching the specification before any decode. The exact G260 executable-and-argument lane census was empty before this check. `df` was not used. `du -sm /workspace` was 36,885 MB; a 1,048,576-byte `/workspace/.g265_disk_probe.bin` `dd conv=fsync` probe passed and was removed. Bytes freed: 1,048,576. No corpus source or bridge partial was changed.

## Re-screen and identity stop

I reused and reviewed all 15 committed G264 sheets (the complete fixed-stride 300-frame set), rather than re-surveying the clip. Result: **0/300** four-line configurations. The strict three-line count is **1/300**, frame 129465: physical far sideline, centre line, and far-end baseline are directly visible; the far-end free-throw line is missing. The remaining 299 frames offer fewer than three such directly identifiable lines under the same standard. Near-side boundary geometry was not used.

Frame 129465 was checked at native 1920x1080 resolution before any fit. The apparent free-throw-line region is the dark paint and free-throw semicircle interior, not a directly visible straight free-throw line. It was rejected before fitting; no line was inferred through a player, logo, paint fill, or beyond the observed mark. Hence there are no fitted-line crops, line endpoints, homography, residual, pairwise angles, concurrence/parallelism diagnosis, condition number, candidate render, blind order, verdicts, unblinding, discrimination threshold, or G252 offsets.

G253 remains the passing WNBA lines-only positive control (2.849 px median and 4.344 px max over 231 shared in-frame samples). G257's 20-px synthetic eye-gate resolution and G252's WNBA 5-px median / 19-px p90 are comparison context only: no candidate exists here to compare. This is a camera/configuration limit, not a failure of the G253 method.

## NOT VERIFIED

Any NCAA candidate map, cross-arena generalisation, automatic calibration (still 0/17), a blind gate, real calibration error, physical court dimensions, repeated labeller agreement, player/tracking accuracy, propagation, or a production change. One clip and one labeller are not a population; short observed lines would amplify angular error when extrapolated.

## Contract self-check

A7: this memo names only retained G264 evidence. B1: the 300-frame denominator is complete and the one three-line near miss is named. B2-B6: no schema, lifecycle, deployment, production module, or move changed. B7: all 15 chronological sheets were reviewed. B8: no self-fit is offered. B9: all denominators are named. B10: no bar, model, label, threshold, or harness setting moved. No harness was added, so no test or LOC-rail change applies.
