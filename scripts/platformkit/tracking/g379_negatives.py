"""G379 negatives: blind rating batches, adjudication, and the zero-acceptance count.

Sealed in the G379 prereg section 8. The sheets are built by the unchanged G364 renderer and carry
no prediction, probability, margin or geometry. A negative is a frame whose ADJUDICATED reference
label is CLOSEUP or CROWD_GRAPHICS; the cascade is run on every one of them and must accept none.
`NO_LINES`, `NO_VALIDATION`, `NO_CANDIDATES`, `REFUSED*` and `TIMEOUT` are counted as themselves and
never as passes (contract B1, B3).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from scripts.platformkit.tracking.g364_sheets import sheet_name

LABELS = ("USABLE_COURT", "CLOSEUP", "CROWD_GRAPHICS", "UNKNOWN")
NEGATIVE_LABELS = ("CLOSEUP", "CROWD_GRAPHICS")
BATCH_SIZE = 40
PROMPT = (
    "You are rating still frames from basketball broadcast video. For each image listed below, "
    "open it and assign exactly one label: USABLE_COURT if the frame is a wide game view in which "
    "the painted court and its markings are visible enough to be measured; CLOSEUP if it is a "
    "close or tight shot of people, a bench, a huddle, an interview or a replay inset where the "
    "court cannot be measured; CROWD_GRAPHICS if it is crowd, arena, studio, graphics, titles or a "
    "commercial; UNKNOWN only if you genuinely cannot tell. Judge only what the image shows. "
    "Output one line per image, exactly `<basename without extension>,<LABEL>`, no other text.")


def _rows(path: Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def batches(manifest: Path, sheets_dir: str, out: Path, size: int = BATCH_SIZE) -> None:
    """Split the sealed pool into fixed batches of at most `size` sheets, in manifest order."""
    rows = _rows(manifest)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prompt.txt").write_text(PROMPT + "\n", encoding="ascii")
    count = 0
    for start in range(0, len(rows), size):
        count += 1
        names = [sheet_name(row["frame_key"]) + ".jpg" for row in rows[start:start + size]]
        (out / ("batch_%02d.txt" % count)).write_text(
            "\n".join(sheets_dir.rstrip("/") + "/" + name for name in names) + "\n",
            encoding="ascii")
    print("BATCHES n=%d frames=%d size=%d" % (count, len(rows), size))


def ingest(manifest: Path, replies: Path, out: Path) -> None:
    """Read every rater reply file into one ratings table, keyed back to the sealed frame keys."""
    keys = {sheet_name(row["frame_key"]): row["frame_key"] for row in _rows(manifest)}
    rows, seen = [], set()
    for path in sorted(Path(replies).glob("*_batch_*.txt")):
        rater = path.name.split("_batch_")[0]
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = [part.strip() for part in line.strip().split(",")]
            if len(parts) != 2 or parts[1] not in LABELS:
                continue
            name = parts[0].replace(".jpg", "")
            if name not in keys or (rater, name) in seen:
                continue
            seen.add((rater, name))
            rows.append({"frame_key": keys[name], "rater": rater, "label": parts[1]})
    _write(out, rows, ("frame_key", "rater", "label"))
    counts = Counter(row["rater"] for row in rows)
    print("RATINGS rows=%d raters=%s" % (len(rows), dict(counts)))


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen kappa over the four-label vocabulary; 1.0 when both raters are constant and agree."""
    n = len(pairs)
    if not n:
        return float("nan")
    agree = sum(left == right for left, right in pairs) / n
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    chance = sum(left_counts[label] * right_counts[label] for label in LABELS) / (n * n)
    return 1.0 if chance >= 1.0 else (agree - chance) / (1.0 - chance)


def adjudicate(ratings: Path, decisions: Path, out: Path) -> None:
    """Agreed pairs stand; only disagreements read the adjudication file. No override."""
    by_key: dict[str, dict[str, str]] = {}
    for row in _rows(ratings):
        by_key.setdefault(row["frame_key"], {})[row["rater"]] = row["label"]
    settled = ({row["frame_key"]: row["label"] for row in _rows(decisions)}
               if decisions and Path(decisions).exists() else {})
    rows, pairs, pending = [], [], []
    for key, labels in sorted(by_key.items()):
        raters = sorted(labels)
        if len(raters) < 2:
            rows.append({"frame_key": key, "reference_label": labels[raters[0]],
                         "source": "single_rater"})
            continue
        left, right = labels[raters[0]], labels[raters[1]]
        pairs.append((left, right))
        if left == right:
            rows.append({"frame_key": key, "reference_label": left, "source": "agreed"})
        elif key in settled:
            rows.append({"frame_key": key, "reference_label": settled[key],
                         "source": "adjudicated"})
        else:
            pending.append({"frame_key": key, "terra": left, "sol": right})
    agree = sum(left == right for left, right in pairs)
    _write(out, rows, ("frame_key", "reference_label", "source"))
    _write(out.with_name("disagreements.csv"), pending, ("frame_key", "terra", "sol"))
    print("ADJUDICATE n=%d agreed=%d kappa=%.6f pending=%d labels=%s"
          % (len(pairs), agree, kappa(pairs), len(pending),
             dict(Counter(row["reference_label"] for row in rows))))


def join(reference: Path, predictions: Path, rows_path: Path, sources: Path, out: Path) -> dict:
    """Build `negatives.csv` and count cascade acceptances; every state is kept distinct."""
    presence = {row["frame_key"]: row for row in _rows(predictions)}
    geometry = {row["frame_key"]: row for row in _rows(rows_path)}
    sections = {row["section_id"]: row for row in _rows(sources)}
    rows = []
    for entry in _rows(reference):
        key = entry["frame_key"]
        head = presence.get(key, {})
        fit = geometry.get(key, {})
        accepted = int(head.get("prediction") == "COURT"
                       and fit.get("selection_status") == "ACCEPT"
                       and fit.get("validation_status") == "VALID")
        section = head.get("section_id") or fit.get("section_id", "")
        rows.append({
            "frame_key": key, "section_id": section,
            "game_id": sections.get(section, {}).get("game_id", ""),
            "reference_label": entry["reference_label"], "reference_source": entry["source"],
            "is_negative": int(entry["reference_label"] in NEGATIVE_LABELS),
            "presence_prediction": head.get("prediction", ""),
            "selection_status": fit.get("selection_status", ""),
            "validation_status": fit.get("validation_status", ""),
            "raw_state": fit.get("raw_state", ""), "cascade_accepted": accepted})
    _write(out, rows, ("frame_key", "section_id", "game_id", "reference_label",
                       "reference_source", "is_negative", "presence_prediction",
                       "selection_status", "validation_status", "raw_state", "cascade_accepted"))
    negatives = [row for row in rows if row["is_negative"]]
    summary = {
        "pool_rated": len(rows), "negatives": len(negatives),
        "negative_sections": len({row["section_id"] for row in negatives}),
        "negative_games": len({row["game_id"] for row in negatives}),
        "cascade_accepted_negatives": sum(row["cascade_accepted"] for row in negatives),
        "cascade_accepted_pool": sum(row["cascade_accepted"] for row in rows),
        "negative_presence": dict(Counter(row["presence_prediction"] for row in negatives)),
        "negative_selection": dict(Counter(row["selection_status"] for row in negatives)),
        "negative_validation": dict(Counter(row["validation_status"] for row in negatives)),
        "negative_raw_state": dict(Counter(row["raw_state"] for row in negatives)),
        "reference_labels": dict(Counter(row["reference_label"] for row in rows))}
    print("NEGATIVES " + json.dumps(summary, sort_keys=True))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="G379 blind negatives")
    parser.add_argument("action", choices=("batches", "ingest", "adjudicate", "join"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sheets-dir", default="")
    parser.add_argument("--replies", type=Path)
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--rows", type=Path)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "batches":
        batches(args.manifest, args.sheets_dir, args.out)
    elif args.action == "ingest":
        ingest(args.manifest, args.replies, args.out)
    elif args.action == "adjudicate":
        adjudicate(args.ratings, args.decisions, args.out)
    else:
        join(args.reference, args.predictions, args.rows, args.sources, args.out)


if __name__ == "__main__":
    main()
