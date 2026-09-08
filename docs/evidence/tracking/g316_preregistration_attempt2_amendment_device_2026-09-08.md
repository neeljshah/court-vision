# G316 attempt-2 prereg AMENDMENT 1 -- reader device only (sealed before any scoring metric)

Amends `docs/evidence/tracking/g316_preregistration_attempt2_2026-09-07.md`
(seal `23a01551e94d1ab3cbd8e0ab7655886547a53f762c5acf0ea688d244b0820fc4`, commit
`558771cb4`). **Exactly one line of that prereg changes: the reader's device.**

## What changes

Prereg section 6 declared `easyocr.Reader(["en"], gpu=False)`. It now declares

    easyocr.Reader(["en"], gpu=True)      # CUDA, RTX 3090, EasyOCR 1.7.2

and each per-frame record's `reader` field records the device it actually ran on
(`easyocr==1.7.2 cuda` or `easyocr==1.7.2 cpu`). Nothing else moves.

## What does NOT change (Q3 / B10 / B1)

The 0.90 bar, the 400-frame denominator, the four sealed regions R1..R4, the
presence rule `white(R2) >= 0.04 and edge(R2) >= 0.07`, `WHITE_MIN = 200`,
`EDGE_MIN = 40`, `CONF_MIN = 0.30`, `UPSCALE = 4`, the union-of-regions token
rule, the verbatim `_parse_scoreboard_text` parse, the sampling rule, the design
set, the clip list, the hand-read protocol and the verdict rule are all
byte-identical to the sealed prereg. The engine and its version are unchanged --
EasyOCR 1.7.2 runs the same weights and the same `readtext(detail=1,
paragraph=False)` call on either device.

## Why, measured

The CPU route was launched first, exactly as sealed, as 20 shards over the 400
scoring frames on the pod. After 49 minutes each worker had consumed 1,442 CPU
seconds and **zero** of the 20 shards had completed: the box is shared with
`track_daemon --workers 16`, so 20 x `OMP_NUM_THREADS=8` got about 0.49 cores
each. At the measured ~1,100 CPU seconds per frame that route needs roughly
12 hours of contended CPU. One frame timed on the GPU takes 8.6-9.3 s for all
four regions against 129.5-159.7 s on the CPU. Free VRAM at the switch was
16,465 MiB, well over the spec's 2,048 MiB gate; `track_daemon` (pid 288450) was
not signalled, stopped or restarted.

## Nothing was observed before this seal (Q1)

The aborted CPU run wrote **0 records**. Its merged
`g316_frame_records.jsonl` had 0 lines, its summary was computed over an empty
list, and its sheet stage raised `IndexError: list index out of range` on an
empty record set. No parsed-clock rate, no per-skin count and no rendered
scoring tile was computed, printed or viewed before this amendment was sealed and
committed. The aborted run's empty outputs were deleted; the 400 scoring frames
and their manifest (digest
`0ba4886b0604caba24476d6bccf7e1a91f9c86470cd355bed72ffce66a1fcb35`) are unchanged
and were extracted before the CPU attempt.

SHA256(amendment, all bytes above this line, LF-normalized) = 325fc52c07bac989571e698a1e3f1ddfa5a79e160a17f5b9647847295a37002b
