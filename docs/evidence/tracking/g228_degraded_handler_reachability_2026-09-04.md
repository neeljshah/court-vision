# G228 degraded-handler reachability

This local-only measurement executes
`docs/evidence/tracking/specs/G228_spec.md` and cites
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changed no file in `src/`,
contacted no pod, changed no threshold, flag, corpus, or ledger row, and made
no deployment. The helper is
`scripts/platformkit/tracking/g228_degraded_handler_reachability.py`; it uses
temporary monkey patches only within its own Python process.

The distinction in every result below is deliberate:

- **Reachability** is whether the ordinary current tracked route/configuration
  executes the named handler. A forced patch never proves this.
- **Forced behavior** is only what the caller does when this local helper makes
  the prerequisite callee fail. It is a counterfactual control experiment.

## Local machine and inputs

Measurement machine: local worktree `C:\Users\neelj\nba-track-a7`, branch
`track-a7`, using `conda run -n basketball_ai`; the pod was not contacted.
`kornia_spec=False`, `COURTV_NO_LOFTR=None`, and OpenCV was 4.11.0 in the
checked local environment. The unset environment value uses the source default
`COURTV_NO_LOFTR=1` behavior.

| Opened input | Exact path | Bytes | Resolution / role |
|---|---|---:|---|
| Pipeline route | `C:\Users\neelj\nba-track-a7\src\pipeline\unified_pipeline.py` | 252711 | Source text |
| Tracker route | `C:\Users\neelj\nba-track-a7\src\tracking\advanced_tracker.py` | 94139 | Source text |
| Current tracker configuration | `C:\Users\neelj\nba-track-a7\config\tracker_params.json` | 522 | JSON text |
| Standard clip route | `C:\Users\neelj\nba-track-a7\scripts\run_clip.py` | 35853 | Source text |
| Per-period route | `C:\Users\neelj\nba-track-a7\scripts\process_game.py` | 20928 | Source text |
| Full-game route | `C:\Users\neelj\nba-track-a7\scripts\full_game_pipeline.py` | 40550 | Source text |
| G218 static audit | `C:\Users\neelj\nba-track-a7\docs\evidence\tracking\g218_degraded_substitute_audit_2026-09-04.md` | 18366 | Markdown text |
| G221 runtime method | `C:\Users\neelj\nba-track-a7\docs\evidence\tracking\g221_denominator_defect_runtime_evidence_2026-09-04.md` | 8980 | Markdown text |
| G194 context only | `C:\Users\neelj\nba-track-a7\docs\evidence\tracking\g194_which_M1_2026-09-03.md` | 9476 | Markdown text; pod evidence, not used as G228 runtime evidence |
| Local source metadata only | `C:\Users\neelj\nba-track-a7\tmp\g136_source_clips\ncaa_basketball__ncaa_basketball_mRkuGgeECak.mp4` | 487249282 | 1920x1080, 30000/1001 fps; no G228 frame decode was started |

Current code identities:

| File | SHA-256 |
|---|---|
| `src/pipeline/unified_pipeline.py` | `bb92310f54c06ffa4c7caf6bea23861a29c35f3588b6fb4a375aeaf74b6b15f8` |
| `src/tracking/advanced_tracker.py` | `fa3b6db7dd180f1da5d12f962e95a9f052f3abdee3373c7c2dcade10cc7a1477` |
| `config/tracker_params.json` | `136387022793202cd79de3eae647d80de83106307992a826f6646fb67fd744bd` |

Before any possible G228 decode, process discovery matched executable and full
arguments. It found a separate lane's active `ffmpeg.exe` writing
`data/videos/g220_amateur_footage/g220__jh3fnwMi7dM.mp4`. G228 therefore did
not run a concurrent decode. This leaves no normal local recovered-M1 success
observation; that absence is reported as `UNDETERMINED`, not converted into a
pass or a forced-reachability claim.

## Per-handler verdicts

| Rank and handler | Current-route reachability | Evidence for that answer | Forced behavior and matched control | Durable degradation signal / caller distinction |
|---|---|---|---|---|
| 3, `unified_pipeline.py:1171` M1 sanity check | **UNDETERMINED** | `run()` calls `_try_recover_court_M1` on every non-suspended frame, but this handler additionally needs the local recovery detector to return a matrix. No normal local input was decoded while the other lane's decoder was active. G194's positive-recovery absence is pod-only and is not substituted for local evidence. | Clean and forced in-process controls both supplied the same synthetic recovered matrix. In the forced case only, `cv2.perspectiveTransform` raised. Both calls returned `None`, installed the candidate as `M1`, `_M1_raw_clip`, and `_last_good_M1`, reset staleness to zero, and emitted empty direct Python stdout/stderr. | No validation result, failure count, log, or durable output identifies the forced sanity failure. A caller inspecting only the method return cannot distinguish it from clean recovery; inspecting the installed matrix cannot say whether validation ran. The forced result proves behavior only, not normal reachability. |
| 4, `advanced_tracker.py:500` ByteTrack reset | **NOT REACHED** | `_reset_per_game` is defined but has no tracked production call. `run_clip`, `process_game`, and `full_game_pipeline` construct a new `UnifiedPipeline` for each clip/period/game, which constructs a new tracker. No retained tracker crosses those units in the current tracked routes. | Not forced: its prerequisite reset call is not reached, so a synthetic constructor failure would not answer the production question. | No reset failure occurs on this route. If a future caller invokes the method, its `pass` supplies no reset-status field; that is a source counterfactual, not current runtime evidence. |
| 5, `advanced_tracker.py:490` colour-tracker reset | **NOT REACHED** | Same `_reset_per_game` caller analysis as rank 4; the colour and ByteTrack reinitializers are adjacent conditional bodies of the same uncalled reset method. | Not forced for the same reason. | No reset failure occurs on this route. A future reached reset failure would have no explicit reset-status field, but that is not a current runtime claim. |
| 9, `unified_pipeline.py:609` detector inference | **NOT REACHED in the standard current configuration** | `run_clip --yolo` defaults to `None`; `process_game` and `full_game_pipeline` pass `yolo_weight_path=None`. A local ordinary no-weight probe constructed `YoloDetector`, observed `available=False`, and `predict` returned `[]` through the pre-inference availability guard. It did not enter the inference `try`. A user-supplied readable weight can make the precondition possible, so this is not generalized to all deployments. | Synthetic available-model clean detection returned one person. A same-input clean-empty control and forced `model.predict` exception both returned `[]`, zero direct Python stdout, and zero direct Python stderr. | The forced exception output is indistinguishable from the clean-empty result at `YoloDetector.predict`. The normal no-weight construction did emit a startup warning to process stderr that shot detection was disabled, but it is not a durable per-run status and is distinct from the silent available-model inference handler. |
| 10, `unified_pipeline.py:1283` learned Kornia/LoFTR fallback | **NOT REACHED in this local configuration** | Kornia is absent locally and the unset environment selects the source's disabled-by-default LoFTR path. `_kornia_matcher` therefore remains `None`; the attempted learned-matcher `try` and its `except` do not execute. SIFT is initialized as the ordinary selected route. | Not forced: the learned route is neither installed nor attempted locally, so an artificial matcher exception would not establish current reachability. | No learned-route degradation occurs locally. The ordinary SIFT selection is only an initialization choice and does not write a durable matcher-choice status. |

Rank 6 (`advanced_tracker.py:286`) remains settled exactly as the specification
requires: this worktree's active configuration has `yolo_model: yolov8n`, and
the non-default model branch is not selected. It was not re-tested.

## Forced-control record

The helper ran without decoding media:

```text
conda run -n basketball_ai --no-capture-output python -m scripts.platformkit.tracking.g228_degraded_handler_reachability
```

The M1 clean/forced pair produced identical caller-visible results: `None`
return, candidate installed in all three M1 state fields, failed attempts `0`,
staleness `0`, and empty captured direct Python streams. The detector controls
produced counts `1` (clean expected detection), `0` (clean empty), and `0`
(forced exception). The forced and clean-empty return lists were exactly `[]`.

These are in-process monkey-patch experiments. They answer **does this when
forced**, never **does this occur in production**.

## Human-gated proposal coverage only

No source proposal or patch is added here. The pre-existing G218 durable
per-run degradation-status proposal would cover all five named handlers if
they fire: recovered-M1 validation, colour and ByteTrack reset outcomes,
available-model detector inference failure, and learned-to-SIFT fallback.

## Cleanup and limitations

No G228 scratch media, render, section, or output file was created, so cleanup
freed **0 bytes**. The pre-existing NCAA source was metadata-inspected only and
was not changed or deleted.

NOT VERIFIED:

- A normal local clip with a non-`None` recovered M1 reaching the sanity check.
- Any pod, different local acquisition, live service, or user-supplied YOLO-NAS
  weight configuration.
- A process topology outside the tracked standard routes or an external dynamic
  caller of `_reset_per_game`.
- Kornia/LoFTR behavior in an environment where Kornia is installed and
  `COURTV_NO_LOFTR=0`.
- The remaining fourteen G218 degraded-substitute handlers.

## Focused verification and verifier self-check

```text
conda run -n basketball_ai --no-capture-output python -m pytest scripts/platformkit/tracking/test_g228_degraded_handler_reachability.py -q
2 passed, 1 warning
```

The warning is the pre-existing `RequestsDependencyWarning`; it is not a
handler signal. The test imports the helper using the required full package
path. No source file crossed 300 lines, so no existing LOC allowlist entry was
grown.

Section B self-check: B1 has no score or excluded metric; all five constructed
handlers are named. B2-B4 add no schema, claim path, or gate. B5 made no pod
copy or access. B6 adds a matching focused test and moves no module. B7-B9 use
no renders, fit, or recycled denominator. B10 changes no threshold or bar.
Section Q does not apply: G228 is a G-row runtime-behavior measurement, not an
S-register quant addition. The memo is the required evidence path and exists
in this commit candidate.
