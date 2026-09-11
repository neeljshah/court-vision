VERDICT: CLOSED AT LIMIT for this option -- one paired DEV shadow shows imgsz 1920 is strictly worse than imgsz 960 on all three sealed continuation components.

# G398 A8 High Resolution DEV Shadow

## Premise (step 0, before any inference)

Preregistration seal `47d81b921baa4941e4db36601486bc88ddf6a6bf89dea77900364129bdaed700` re-derived from the LF bytes on disk. The three sealed G389 inputs re-hash to their recorded digests. The DEV manifest holds all 1,071 keys over 28 games and 28 sections, labelled 531 VISIBLE / 425 ABSENT / 115 UNKNOWN; 530 of the VISIBLE keys carry a training box over 27 games and one VISIBLE key has an adjudicated centre but no training box. Held-out coverage is 549 keys, 32 games, 35 sections; key, game and section overlap with the DEV tensors is 0 in every direction and no held-out pixel was opened. All 1,071 native 1920x1080 sheets re-hash to the sealed G373 manifest digest.

G394's independent disposition is NOT VALIDATED (landed `85a91a9f3`). Recounting its landed per-frame table reproduces all 549 held-out counts exactly: A8 90 TP / 169 FP / 212 FN, A10 84 / 156 / 218, A0 0 / 8 / 302. The archived A8 checkpoint was located by digest at `/workspace/wt/a7/.g394_scratch/a8_final_epoch.pt`, copied to lane scratch and re-hashed to `0f05a61618687bda2005ce4ac8343c5987f60ba0076245597de59f7380398762` (6,259,242 bytes, 365 torch-zip members read back). No substitute checkpoint was used.

## Method actually run

One paired shadow launch, charged prospectively (`launch_accounting.json` written before the first frame) with a 60-minute GPU-stage deadline, 30 interleaved quantile bins over the sorted game/section/frame-index/key order, arm order alternating by bin, sequential GPU use, threads 1, six cores. Both arms share the archived A8 weights and one argument set -- conf 0.05, IoU 0.70, max_det 300, agnostic NMS off, half precision, augment off -- and differ only by imgsz. The GPU stage took 42.9 s of the 3,600 s allowance; the allowance is now spent. Both traversals covered all 1,071 keys with one archived row per key, silence recorded explicitly as `NO_DETECTION` rather than dropped. Raw predictions and timing were archived before any score. Before charging the launch, a synthetic all-black 1920x1080 probe exercised the two predict calls; it opened no reference pixel and its output was discarded.

Scoring used the frozen G363 rule unchanged -- rank-0 OBSERVED only, centre tolerance `max(3 px, diameter_720p/2)`, native-to-720p by height, sheet_scale 1.0 so no centre is doubled -- on the full DEV denominators, with UNKNOWN observations charged as false positives.

## Measured result (DEV only, one run)

| arm | TP | FP | FN | C0 = TP/1071 | Wilson95 precision lower | ALL FP / 425 ABSENT | ABSENT-only FP | UNKNOWN FP |
|---|---|---|---|---|---|---|---|---|
| imgsz 960 (baseline) | 251 | 198 | 280 | 0.2344 | 0.5128 | 0.4659 | 89 | 35 |
| imgsz 1920 (candidate) | 121 | 310 | 410 | 0.1130 | 0.2404 | 0.7294 | 68 | 53 |

The sealed continuation rule requires all three of: candidate C0 strictly higher, candidate Wilson lower not smaller, candidate ALL FP/N_absent not larger. All three fail -- C0 falls by 0.1214, the Wilson lower bound falls by 0.2724 and ALL FP/N_absent rises by 0.2635. Per game, 1920 has fewer true positives in 26 of 28 games, equal in 2 and more in none. This closes the fixed resolution attempt AT LIMIT; the row allocates nothing and proposes no successor experiment. Per the spec, reference growth via G386 to at least 1,500 audited DEV boxes remains the stated route before another training arm.

The historical benchmark bars 0.25 / 0.90 / 0.01 are printed unchanged and are NOT tested by this row. Neither arm ran on held-out frames; the held-out A8 C0 0.164 remains context only. The DEV denominator reuses 530 training-positive frames, so the 960 DEV C0 of 0.2344 is a training-contaminated figure and is not comparable to any held-out number.

## Discipline receipts

One run, one launch, no seed replicate, no lower-resolution retry, no threshold sweep, no training: the result is descriptive and supports neither a causal nor a repeatable-system conclusion. Two fresh scorer processes replayed the saved predictions and returned identical counts (`repeats.json`), which establishes arithmetic only. Thirty evenly spaced paired native cards span all 1,071 DEV keys and cover 16 VISIBLE, 8 ABSENT and 6 UNKNOWN states including silence (18 of 30 cards have no 960 detection). Latency and peak VRAM are disclosed without any operational promise: median 18.7 ms per key at 960 and 18.8 ms at 1920, 20.0 s versus 22.8 s total, torch peak reserved 117,440,512 bytes for both arms on a shared RTX 3090. Environment: Python 3.12.3, torch 2.8.0+cu128, ultralytics 8.4.146, CUDA 12.8; ultralytics warns that `half` is deprecated but still honours it.

`g398_q6_scan.py` scanned every G398 text artifact plus the modules and the test: 0 non-opaque hits. Its boundary rule was aligned with the landed G394 scanner so that digit runs inside measured floats stay opaque; the character-code pattern set is unchanged.

## NOT VERIFIED

- No held-out inference ran, so no benchmark bar moved and no detector qualified.
- A single unreplicated pair cannot separate the resolution effect from run-to-run variation, although the per-game direction is uniform.
- Latency and VRAM come from one shared-GPU run and are not an operational commitment.
- Whether a different resolution, a tiling or crop stage, or a retrain at native scale would help is untested here and would need its own seal.
