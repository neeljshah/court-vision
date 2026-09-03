# G201 (orchestrator-run): static census of silent exception handlers in the route

**Static only.** Parsed with `ast`. Nothing was executed, nothing imported from
`src/`, no production file edited. `src/` is human-gated and was READ only.

Reproduce:

    python scripts/platformkit/tracking/silent_handler_census.py \
        --repo . --out docs/evidence/tracking/g201_silent_handlers/route_exception_census.csv

## Counts over the seven route files (CONSTRUCT, exhaustive)

| quantity | count |
|---|---:|
| exception handlers | **114** |
| silent (body is only `pass`/`continue`/`break`/`return`) | **54** |
| silent AND broad (catches bare `except` or `Exception`) | **37** |

The ELIGIBLE DENOMINATOR is the 114 handlers in the seven files the `run_clip`
route executes: `unified_pipeline.py` (4,780 lines), `advanced_tracker.py`
(1,884), `color_reid.py`, `court_detector.py`, `rectify_court.py`,
`video_handler.py`, `run_clip.py`. Per-handler rows are in
`route_exception_census.csv`.

## Why 37 is the number that matters

A handler that catches a NARROW exception and continues is a design decision. A
handler that catches `Exception` and does nothing converts **any** failure --
including one nobody anticipated -- into normal-looking operation. Those are the
37.

Four of them sit on paths this programme has already spent rows chasing:

| site | what it makes invisible |
|---|---|
| `unified_pipeline.py:283` `_decode_loop()` | The decode thread catches everything, then pushes the EOF sentinel regardless. **A decode CRASH is indistinguishable from a clean end of video**, so a truncated run reports fewer frames and no error. |
| `unified_pipeline.py:1171` `_try_recover_court_M1()` | Court-matrix recovery failure. G194 measured 5 fresh-solve attempts and 0 successes per run, then a silent fall back to a matrix the code's own comment calls invalid for broadcast frames. |
| `unified_pipeline.py:1283` `_get_homography()` | Homography failure, on the path that produces the DEGENERATE projection G194 rendered. |
| `advanced_tracker.py:286`, `:348`, `:380`, `:404` (all in `__init__`) | **Model loading.** If a re-ID, pose or supervision component fails to construct, the tracker runs permanently degraded and says nothing. |

## What this DOES and does NOT establish

**Established:** the counts above, by exhaustive static parse, and the fact that
each named site would swallow a broad failure without emitting anything.

**NOT established, and it is the load-bearing question:** *which of these
handlers actually FIRE at runtime, and how often.* A handler that never fires is
harmless. One firing every frame is masking a live defect. Nothing here measures
that, and no claim in this memo should be read as saying any specific handler
did fire. Turning 37 static sites into a ranked runtime list needs an
instrumented route run, which is queued rather than done, because the pod is
currently measuring a timing-sensitive row (G198) and extra load would
contaminate it.

**Also not established:** that these handlers CAUSED any known failure. The
claim is narrower and still serious -- they are why those failures presented as
normal operation instead of as errors.

## Relationship to the programme

This is the structural answer to a standing question about why defects in this
route keep being discovered late and by inference rather than by an error
message. It is a measurement, not a fix: every site listed is inside `src/`,
which is human-gated, so none of them may be changed without the user.
