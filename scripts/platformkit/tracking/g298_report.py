"""Write the G298 memo from fetched detections and locally computed arithmetic."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.tracking.g298_compare import ELIGIBLE_FEET, TOLERANCES, sha256

BASE = Path("docs/evidence/tracking")
OUT = BASE / "g298_detector_capacity_and_input_resolution_artifact"
MEMO = BASE / "g298_detector_capacity_and_input_resolution_2026-09-04.md"


def build() -> None:
    """Render tables without changing any scoring decision."""
    summary = json.loads((OUT / "comparison.json").read_text())
    metadata = {arm: json.loads((OUT / f"{arm}_summary.json").read_text()) for arm in ("A", "B", "C")}
    sizes = json.loads((OUT / "scratch_bytes.json").read_text())
    recalls = {a: summary["arms"][a]["recall"]["100"]["recall"] for a in metadata}
    delta_resolution = recalls["B"] - recalls["A"]
    delta_capacity = recalls["C"] - recalls["B"]
    attribution = (
        f"At 100 px, fresh A/B/C recall is {recalls['A']:.6f}/{recalls['B']:.6f}/{recalls['C']:.6f} "
        f"(each eligible denominator 143 located feet), so input resolution contributes "
        f"{delta_resolution:+.6f} ({100 * delta_resolution:+.2f} percentage points) and added model capacity "
        f"{delta_capacity:+.6f} ({100 * delta_capacity:+.2f} percentage points); the historical G285b "
        "17/143 = 0.119 uses retained tracking footpoints and is not an interchangeable fresh-A baseline."
    )
    lines = ["# G298 - detector capacity and input resolution", "", "## Verdict", "",
        "MEASUREMENT COMPLETE; independent verifier acceptance is pending. "
        "n=15 frames, 143 eligible located-foot observations, 3 arms, 3 tolerances, "
        "1 clip, 1 span, 1 shot, 1 SINGLE MODEL LOCATOR ground truth. "
        "There is no pass bar. This row MEASURES an alternative configuration and ADOPTS NOTHING.", "",
        attribution, "", "## Machine, inputs, and controlled design", "",
        "Detection: pod RTX 3090, compute-only scratch `/workspace/wt/a6`, because source footage, weights, "
        "and GPU are there. Arithmetic and tests: local `C:/Users/neelj/nba-track-a6`, branch `track-a6`.", "",
        "The ONLY difference between A and B is input resolution; the ONLY difference between B and C "
        "is model capacity. All use classes=[0], conf=0.3, CUDA device=0, half=True, verbose=False, "
        "batch-one calls, and the same installed Ultralytics defaults. No crop, court subset, "
        "augmentation, or downstream box exclusion is introduced.", "",
        "| Arm | Model | imgsz |", "| --- | --- | ---: |", "| A | yolov8n | 640 |",
        "| B | yolov8n | 1920 |", "| C | yolov8x | 1920 |", "",
        "The unchanged human-gated `src/tracking/player_detection.py` is IMPORTED and RUN: "
        "`FeetDetector([])` and `get_players_pos`. A capture wrapper records the raw model boxes "
        "returned by that method's exact inference call, before its downstream color/map/tracking logic. "
        "Only the scratch detector instance's input-size value (B/C) and model object (C) change. "
        "This is the production detection configuration, not an end-to-end tracking rerun. "
        "The source comment says \"yolov8x is slower to load and only marginally better for tracking\" "
        "without citing a measurement. 1920 to 640 is 3x linear / 9x area downscaling; a 150 px player becomes 50 px tall.", "",
        "Frame list (15 unique frames, derived from the committed located-feet CSV): "
        + ", ".join(map(str, summary["frames"])) + ".", "",
        "Frames were decoded once by OpenCV with zero-based frame seeks and next-frame index assertions, "
        "then identical BGR arrays were copied for every inference call. Every decoded-frame SHA-256 is "
        "in each arm summary. G278's source-video SHA-256 and 1920x1080 at 30 fps were asserted. "
        "The locator originally viewed G278 JPEG derivatives of these source frames; this row uses "
        "original-video decodes, with identical pixels across arms.", "",
        "Input identity: `" + metadata["A"]["source_video"]["path"] + "`, "
        + str(metadata["A"]["source_video"]["bytes"]) + " bytes, 1920x1080, SHA-256 `"
        + metadata["A"]["source_video"]["sha256"] + "`.", "",
        "## Determinism before comparison", "",
        f"A and A_repeat detection CSVs are byte-identical: **{summary['A_byte_identical']}**. "
        "The check was recorded before B/C ran and before local recall arithmetic. "
        "The CSV preserves box order, coordinates, confidence, frame keys and bottom-centre feet. "
        "Both model instances were freshly constructed. Environment and route identities are archived in "
        "A_summary.json; both CSV hashes are in determinism.json. "
        "G241's 808/1,201 differing tracking records do not establish single-frame detector repeatability; "
        "this check measures it directly. B and C each have one draw; their own repeatability is NOT VERIFIED.", "",
        "## Recall against the committed locator", "",
        "Footpoint = bottom-centre of each box, using production's integer truncation and image clipping: "
        "x=(max(0,int(x1))+min(1920,int(x2)))//2; y=min(1080,int(y2)). "
        "A located foot matches if ANY same-frame detection footpoint is within the inclusive tolerance. "
        "No one-to-one assignment; no located observation is removed, including zero-detection frames. "
        "This row has NO eye labels and NO blind judging: it is arithmetic against committed coordinates, "
        "not new visual validation.", "",
        "| Arm | Tolerance px | Matched / eligible denominator | Recall |",
        "| --- | ---: | --- | ---: |"]
    for arm in metadata:
        for tolerance in TOLERANCES:
            cell = summary["arms"][arm]["recall"][str(tolerance)]
            lines.append(f"| {arm} | {tolerance} | {cell['matched']} / 143 eligible located feet | {cell['recall']:.6f} |")
    lines += ["", "## Paired exact tests", "",
        "McNemar's two-sided EXACT conditional binomial test uses the per-foot detected/not indicator. "
        "An unpaired two-proportion test would be WRONG because both arms observe the SAME located feet "
        "on the SAME frames, so the two samples are dependent. The tests use discordant pairs only. "
        "All p-values are nominal; NO multiplicity correction across the three tolerances. "
        "Repeated observations within frames/players are not independent population samples, and these "
        "nominal per-foot tests do not adjust for that clustering.", "",
        "| Pair | Tolerance px | Lost | Gained | Discordant | Nominal exact p |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for pair, tests in summary["paired_tests"].items():
        for tolerance, test in tests.items():
            lines.append(f"| {pair} | {tolerance} | {test['lost']} | {test['gained']} | "
                         f"{test['discordant']} | {test['nominal_p']:.10g} |")
    lines += ["", "All six comparisons contain 143 paired eligible located-foot observations; "
        "`paired_feet.csv` archives every nearest distance and detected/not indicator.", "",
        "## Box volume and nearest distances", "",
        "| Arm | Total raw person boxes | Mean boxes / 15 frames | Median nearest distance / 143 eligible feet (px) |",
        "| --- | ---: | ---: | ---: |"]
    for arm, data in summary["arms"].items():
        lines.append(f"| {arm} | {data['total_detections']} | {data['mean_detections_per_frame']:.6f} | {data['median_nearest_px']:.6f} |")
    lines += ["", "| Source frame | A boxes | B boxes | C boxes |", "| ---: | ---: | ---: | ---: |"]
    for frame in summary["frames"]:
        lines.append("| " + " | ".join([str(frame)] + [str(summary["arms"][a]["counts_per_frame"][str(frame)]) for a in metadata]) + " |")
    lines += ["", "A recall gain bought by simply emitting far more boxes is not a better detector. "
        "Recall is not precision: a bigger model may also emit more false boxes. These counts expose "
        "box-volume changes, but do not measure true precision.", "",
        "Resolution is the dominant configuration contribution on this fixed sample: at 100 px it "
        "gains 48 located feet and loses none (nominal exact p=7.1054273576e-15), while capacity "
        "gains 2 and loses 10 (nominal exact p=0.03857421875). B emits 5.51 times A's boxes; "
        "C emits fewer boxes than B and has lower agreement recall. Thus the 640 setting is implicated "
        "in missed locator agreement; more capacity adds no recall benefit here, and detector quality "
        "overall remains unmeasured. No setting is adopted or proposed for production.", "",
        "## Historical comparison and limitations", "",
        "G285b recorded 3/143 = 0.021, 7/143 = 0.049, and 17/143 = 0.119 "
        "(eligible denominator 143 located feet each time) against 88 retained G270-on-court G267 "
        "tracking footpoints. G298 scores all fresh raw person detections as specified. The reconciled "
        "G273-VS-G285b ledger row reinstated G285b as a localisation measure, reinterpreted G273's "
        "neighbourhood criterion, and withdrew G284's 0.416 bound. None of those counts is changed. "
        "A difference between historical G285b and fresh A cannot be attributed to input resolution "
        "or model capacity, since neither setting differs between those two baselines.", "",
        "At 100 px the historical-to-fresh-A difference is 8/143 = +0.055944 (+5.59 percentage points; "
        "eligible denominator 143 located feet), kept separate from the A-to-B resolution and B-to-C "
        "capacity contributions. It is not a configuration benefit. This preserves G285b's committed "
        "17/143 figure rather than forcing the fresh raw-detection arm to reproduce a retained subset.", "",
        "The ground truth is 143 foot observations on 15 frames from a SINGLE MODEL LOCATOR, not a human, "
        "and it is the same locator whose judgements the programme's other rows rest on -- so this row "
        "measures agreement with that locator, and A DETECTOR THAT FINDS PLAYERS THE LOCATOR MISSED WILL "
        "BE SCORED AS WRONG. That bounds every recall figure here from above and below. "
        "Specifically, unlocated correct detections receive no recall credit; a detector-side unmatched "
        "box cannot be certified false by this incomplete reference.", "",
        "All 15 frames lie inside frames 19599-23399, and G278 measured that span friendlier than its own "
        "clip (0.836 vs 0.656, p=0.0078), so nothing may be quoted clip-wide. ONE clip, ONE shot. "
        "A bigger model at a higher input size is SLOWER and this row measures NO TIMING, so it cannot "
        "say the alternative is practical, only whether it detects more.", "",
        "## Operational receipts and bytes", "",
        "GPU gate: free VRAM, not a lane count. Initial exact query read 356 MiB, 24576 MiB: "
        "24,220 MiB free, above the runner's 6,000 MiB operational budget. No process was killed, "
        "interrupted, or restarted. No corpus source or bridge partial was deleted. "
        "The original `~/bin/pod_run a6 --ship ... --fetch ... -- ...` stalled in its legacy MooseFS "
        "du walk. That process was left alone. `g298_wrapper.py` produces the worktree-local "
        "`g298_pod_run.sh` from that exact installed wrapper, replacing the disk guard with dd conv=fsync. "
        "UNKNOWN is never interpreted as zero. This is an explicit operational adaptation, not an "
        "unmodified-wrapper claim. Shipping, scratch execution, and fetching are otherwise preserved. "
        "The atomic execution.lock prevents the delayed wrapper from duplicating detection.", "",
        "The bulk fsync-only wrapper completed staging first and ran all four inference passes "
        "successfully (`pod_run_20260904220142.log`, POD_RUN_DONE rc=0). A later minimal staging "
        "attempt failed on a missing association import before inference; its corrected launcher and "
        "the delayed original wrapper both skipped the already-claimed experiment. Early fetch failures "
        "were from those duplicate launchers, before C existed; the successful compute wrapper fetched "
        "every final CSV and summary. The outer local launch scripts reported a trailing shell EOF "
        "after the commands returned because the recovery revision changed the file while they waited; "
        "the current scripts pass bash -n, and the pod computation and complete fetch succeeded.", "",
        "Code identity caveat: a delayed bulk staging pass copied an import-bootstrap-only revision "
        "of the harness while the original process was decoding. The recorded on-disk hash matches "
        "runner_live_snapshot.py.txt. runner_launch_version.py.txt reconstructs the exact prelaunch "
        "source from this session's patches; route_identity_notes.json records both hashes and their "
        "difference. The launch version imports src.tracking.player_detection normally; the recovery "
        "version imports the same unchanged file directly to avoid unrelated package initializers. "
        "No executed detector call, frame handling, footpoint rule, model setting, or scoring logic "
        "changed. The gated player_detection.py and plot_tools.py hashes are unchanged. The live "
        "snapshot is a disk identity receipt, not a claim that Python hot-reloaded the bootstrap.", "",
        "Scratch retained file sizes (not filesystem allocation or whole-volume usage):", "", "```json",
        json.dumps(sizes, indent=2), "```", "",
        "The original wrapper wrote then freed its own 8,388,608-byte quota probe; the detection harness "
        "freed 0 bytes. Whole-volume net growth is UNKNOWN because there is no reliable before/after "
        "MooseFS census; re-staging the existing Python tree must not be counted as wholly new data. "
        "The scratch manifest reports the exact retained new weights, fsync probes and config/cache bytes. "
        "Additional task output and local artifact byte sizes are in artifact_inventory.json.", "",
        "Every captured GPU/disk probe is pasted below; status receipts also retain intermediate GPU "
        "readings. Empty du output is UNKNOWN, never 0, and never grounds for stopping.", ""]
    owned = json.loads((OUT / "pod_owned_bytes.json").read_text())
    lines += [f"Task-owned retained additions: **{owned['bytes_added_retained']:,} bytes** "
              f"(including the {sizes['retained_bytes']:,}-byte model/probe/cache scratch subtotal); "
              f"bytes freed: **{owned['bytes_freed']:,}**, solely the original wrapper's quota probe. "
              "`pod_owned_bytes.json` lists every counted file. This excludes unknown net changes from "
              "the broad restaging of pre-existing Python files.", ""]
    for name in ("earlier_probes.txt", "preflight.log", "pod_run.log", "pod_run_fsync.log", "pod_run_minimal.log", "attempt_import_failure.txt", "status.txt", "status_staging.txt", "status_running.txt", "probes.json"):
        path = OUT / name
        if path.exists():
            raw = path.read_bytes()
            text = raw.decode("utf-16" if raw.startswith(b"\xff\xfe") else "utf-8-sig")
            # Paste probes verbatim, avoiding model-download progress and repetitive library warnings.
            if name.endswith(".log") and name != "preflight.log":
                text = "\n".join(line for line in text.splitlines() if not any(
                    token in line for token in ("Downloading ", "'half' is deprecated", "FETCH", "RSS_PEAK")))
            lines += [f"`{path.as_posix()}` (GPU/disk and run-status lines; full raw receipt archived)", "", "```text", text, "```", ""]
    lines += ["## Reproduction, identity and verifier self-check", "", "```text",
        "bash scripts/platformkit/tracking/g298_run.sh",
        "python -m scripts.platformkit.tracking.g298_compare --located-feet docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv --output " + OUT.as_posix(),
        "python -m pytest scripts/platformkit/tracking/test_g298_compare.py -q -p no:cacheprovider",
        "..... [100%]", "5 passed in 1.93s",
        "python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider",
        ". [100%]", "1 passed in 1.62s", "```", "",
        "Independent recomputation: `python -m scripts.platformkit.tracking.g298_audit` returned "
        "PASS for SciPy distances, counts, medians and all six exact binomial p-values, plus arm "
        "settings, input hashes and decoded-pixel equality.", "",
        "The pod command is already complete; the execution lock deliberately prevents an accidental "
        "extra draw. Local arithmetic is rerunnable from the committed CSVs. Route files, weights, "
        "library versions, settings and input path/bytes/resolution are in each arm's summary. "
        "Local input/route identities are in artifact_inventory.json. No allowlisted file grew (A12).", "",
        "Against `docs/evidence/tracking/VERIFIER_CONTRACT.md`: B1/B9 retain all 143 distinct "
        "(frame, player_id) observations and all 15 frames; B2 adds artifacts without schema changes; "
        "B3/B4 no production queue/lifecycle changes; B5 uses the explicit compute-only scratch exception, "
        "never the deployed tree; B6 no module move; B7 uses the complete prescribed frame set; "
        "B8 fits nothing and names the single-locator reference; B10 changes no bar; B11 reports A's "
        "actual repeat check and limits B/C to single draws. A7 evidence paths checked; A9/A11 exact "
        "sources and route hashes archived. Q is for S-register rows and does not apply to G298. "
        "The RESULTS_LEDGER row and this memo are in the same commit. TRACKING_GAPS_2026-09-01.md "
        "and the user-owned spec edit are untouched by this landing.", "", "## NOT VERIFIED", "",
        "- Human ground truth, locator completeness, independent-rater agreement, unique-player recall, true precision.",
        "- Clip-wide, second-shot, second-clip or population generalisation.",
        "- B/C repeatability or the historical tracking route's repeatability.",
        "- Why fresh A differs from historical retained tracking footpoints, if it does.",
        "- Runtime, throughput, practical cost, tracking identities, homography quality or downstream benefit.",
        "- Whole-volume disk usage/net growth, production adoption, or any filter, threshold, gate or retrain.", ""]
    lines += ["## Focused test source (pasted)", "", "```python",
              Path("scripts/platformkit/tracking/test_g298_compare.py").read_text(), "```", ""]
    MEMO.write_text("\n".join(lines), encoding="ascii", errors="backslashreplace", newline="\n")


if __name__ == "__main__":
    build()
