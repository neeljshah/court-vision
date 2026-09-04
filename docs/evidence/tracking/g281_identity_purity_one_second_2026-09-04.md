# G281: one-second same-ID identity purity

**Verdict: ACCEPT (measurement only).** The sample yields 43 SAME PERSON and 3 DIFFERENT PERSON judgments among 46 judgeable person-person pairs at a 30-frame (1.00 s) horizon: estimated purity is 0.935, with 95% Wilson interval [0.825, 0.978]. This is the programme's first positive, bounded local identity evidence. It does not validate tracker identity generally, does not justify a production change, and does not establish a per-player quantity as safe to use.

This record follows [G281_spec.md](specs/G281_spec.md) and [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). The code, sealed orders, verdicts, rendered crops, unblinded maps, and summary are in [g281_identity_purity_one_second_artifact/](g281_identity_purity_one_second_artifact/). No production path, source, model, feature flag, threshold, or daemon changed.

## Question and frozen input

The question is deliberately narrow: when an emitted detector-box `track_id` is observed again exactly 30 source frames later, does it still refer to the same visible human? The input is the committed G267 artifact [g267_measurement.json](g267_court_space_physical_plausibility_artifact/g267_measurement.json), SHA-256 `183b195f0f3ea7b8a81c47a384c229b4e10ca464dc32f2ecfc1a52ccef6fdedb`. Its inherited video is `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, 1920x1080, 30 fps, source frames 19599--23399. Analysis of the records was local; crop rendering used the pod only.

These are detector boxes and emitted IDs, not authenticated players. The crop is a fixed 512x640 native-resolution footpoint-centred neighbourhood, not the detector's inferred bounding box. A one-second result is one horizon: 3 s or 10 s is a different, plausibly worse, measurement.

## Record population and selection

There are 98 distinct emitted IDs. Exclusive source-span length across those IDs is 0 / 186 / 2,226 frames (min / median / max), or 0.0 / 6.2 / 74.2 seconds; observation-count length is 1 / 120 / 1,639. Eighty-three IDs span at least 30 frames and 66 span at least 90 frames.

The full record has 20,551 same-ID pairs exactly 30 source frames apart. That is the **pre-on-court pair population**, not the measurement denominator. Applying G270's unchanged inclusive on-court definition at both endpoints (`0 <= court_x_ft <= 50` and `0 <= court_y_ft <= 94`) and requiring finite coordinates at both endpoints leaves **15,207 eligible same-ID detector-box pairs**. This is the eligible denominator; it matches neither a claimed player population nor an identity-verified population.

Before any crops or verdicts, the harness divided the selectable first-frame span into 80 equal-width source-frame bins and made one seeded random draw from each, with an emitted-ID cap of four pairs. The result was 80 sampled pairs from 59 IDs, across bins 1--80; first endpoints run from source frame 19621 to 23361 and second endpoints from 19651 to 23391. Selection conditioned on neither speed, displacement, jumps, identity outcome, nor person-ness. `local_population.json` preserves all 20,551 pairs, the 15,207 eligible pairs, and the selected rows.

## Two sealed passes

Pass 1 measured person-ness. All 160 endpoint crops from the 80 sampled pairs were pooled into one seeded random order with no pair, endpoint, ID, or frame information visible. The order commitment, review boards, and verdict table were committed in `f58b27e29` before unblinding. G273's unchanged categories gave 146 PLAYER on court of play, 4 PERSON NOT PLAYER IN PLAY, 20 NOT A PERSON, and 0 CANNOT JUDGE.

Only 62 sampled pairs had both endpoints classified as PLAYER or PERSON NOT PLAYER IN PLAY. Pass 2 assessed those pairs in a separately seeded random order. It necessarily showed the two endpoint crops together, because pairing is needed for the identity judgment; that is exactly why person-ness was separately measured first with the pairing hidden. Its order, paired renderings, and verdicts were committed in `5e583c149` before unblinding. The verdicts were 43 SAME PERSON, 3 DIFFERENT PERSON, and 16 CANNOT JUDGE.

The full funnel is therefore:

`80 sampled pairs -> 62 both-endpoints-person pairs -> 46 judgeable person-person pairs -> 43 SAME PERSON / 3 DIFFERENT PERSON`.

The 16 CANNOT JUDGE cases are separate from the 46 judgeable pairs. Purity is **not** reported against the 80 sampled-pair count: `43 / (43 + 3) = 0.935`, with a two-sided 95% Wilson interval of **[0.825, 0.978]**. It is an estimate, not an exact identity rate.

## Interpretation and limits

The result supports only this bounded statement: in this sampled, eligible detector-box population, a same emitted ID often still showed the same judgeable visible person one second later. A low result would have ruled out carrying per-player quantities through IDs; this high local point estimate is the first positive identity evidence, but it remains far short of system-wide identity validation.

Most importantly, **fragmentation is out of scope**. This asks whether one ID stays on one person. It does not ask whether one person is split over several IDs, the opposite failure mode; a good purity result cannot be read as good identity overall. Also, endpoint-only judgment bounds this purity from above: it cannot observe an ID that drifts onto a third person and returns within the intervening second.

This is one non-deterministic detector draw, one clip, one pre-cut shot, one arena, and one labeller. The G278 result says this source span is measurably more court-bearing than the clip (0.836 versus 0.656, nominal p=0.0078), so this purity cannot be quoted clip-wide; the direction of any effect on tracking quality outside the span is unmeasured. The categorical crop review is also not G257's subpixel 20-px map sensitivity, and labeller reliability does not clear an 80% blind-agreement criterion because there was one labeller only.

## Pod custody and disk guard

The crop command ran under `~/bin/pod_run a6 --ship ... --fetch ...` in `/workspace/wt/a6`, with the required guard inside the rendered command. Before rendering, `du -sm /workspace` was 39,507 MB. The in-command 8 MiB `dd conv=fsync` probe passed and was removed; 7,320,182 crop bytes were rendered. Occupancy was recorded as evidence only: peer worktree set `{ /workspace/wt/a17 }`, the observed Python ARGS were `python -m scripts.platformkit.eval_gate.s276_incumbent_conformal_band_full_attempt2`, and `nvidia-smi` reported 0% GPU, 0% memory utilisation, 1 MiB / 24,576 MiB. No action was taken on those observations and no new N was proposed.

The launcher timing ceiling interrupted its automatic fetch after the remote job completed, so the already-rendered output was fetched as a 7,454,720-byte disposable archive, then that archive was removed on both pod and local transfer storage. The exact pod scratch artifact was then resolved and removed, freeing 36,182,543 bytes. No corpus source and no bridge partial download was deleted. The committed local artifact is 49,450,709 bytes. The shipped route hashes were `dfa11e6e8b1b0076835c7e14d1c1e8a48b1473587be58ea0456f8b97f262759a` for the Python harness and `c1fdd593b0073f174ed66d0bfc9e959bf93c46348f2eb5d087807513d0046a37` for the pod command. Occupancy and all guard evidence are retained in the artifact.

## NOT VERIFIED

- Identity purity at any horizon other than exactly 30 frames / 1.00 s.
- Identity in another shot, clip, arena, broadcast, sport, detector draw, or court-visibility regime.
- Any clip-wide purity, causal explanation, or production remedy.
- Fragmentation: whether one human is split across multiple emitted IDs.
- The hidden path between endpoints, including a drift to a third person and back.
- Second-labeller agreement or label correctness beyond this one labeller's categorical judgment.
- That a positive endpoint purity makes any per-player quantity valid.
