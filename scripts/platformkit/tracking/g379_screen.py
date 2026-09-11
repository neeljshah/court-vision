"""G379 premise, source census, the frozen presence screen and the sealed six-section draw.

Every rule here is sealed in `docs/evidence/tracking/g379_broadcast_geometry_2026-09-10/
g379_prereg_2026-09-10.md` sections 1-3. Nothing in this file reads a fit, a residual or a rater
label, and nothing changes a G362 / G364 / G365 / G371 constant: the tick rule, the frame key, the
embedder and the head are imported from their landed modules and called unmodified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from scripts.platformkit.tracking.g364_sampler import frame_key, interior_indices

SEED_STRING = "G379"
SCREEN_TICKS = 12
COURT_SHARE = 0.50
SECTIONS_WANTED = 6
SOURCE_FIELDS = ("section_id", "game_id", "video_id", "offset_s", "source_path", "bytes",
                 "source_sha256", "width", "height", "fps", "frame_count", "duration_s",
                 "codec_name")
MANIFEST_FIELDS = ("frame_key", "source_path", "frame_index", "section_id", "game_id",
                   "source_sha256", "tick_rank")
GID = re.compile(r"^(?P<stem>.+)_s(?P<off>\d+)$")


def _rows(path: Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict], fields) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def premise(evidence: Path, out: Path) -> dict:
    """Print the landed numbers the row rests on and the broadcast-registration search (Q8)."""
    known = json.loads((evidence / "g362_registration_refusal_2026-09-09"
                        / "known_h.json").read_text(encoding="utf-8"))
    g365 = json.loads((evidence / "g365_fitter_refinement_2026-09-09"
                       / "summary_b.json").read_text(encoding="utf-8"))
    g371 = json.loads((evidence / "g371_symmetry_margin_2026-09-09"
                       / "summary.json").read_text(encoding="utf-8"))
    model = json.loads((evidence / "g364_learned_court_presence_2026-09-09"
                        / "model.json").read_text(encoding="utf-8"))
    memo = (evidence / "g374_court_presence_validation_2026-09-10.md").read_text(encoding="utf-8")
    hits = []
    for path in sorted(evidence.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.split("\n"), start=1):
            low = line.lower()
            if "forward" in low and "median" in low and "broadcast" in low:
                hits.append({"path": path.name, "line": number, "text": line.strip()[:200]})
    state = {
        "g362_known_h": known,
        "g365_summary_b": {k: g365[k] for k in sorted(g365) if not isinstance(g365[k], (list, dict))},
        "g371_summary_keys": sorted(g371),
        "g364_threshold": model["threshold"],
        "g364_head_sha256": hashlib.sha256(
            (evidence / "g364_learned_court_presence_2026-09-09" / "model.json")
            .read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "g374_verdict_line": memo.split("\n", 1)[0],
        "broadcast_forward_median_hits": hits,
        "premise_false": False,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, sort_keys=True, indent=1) + "\n", encoding="ascii")
    print("PREMISE known_h_gap_px=%s state=%s | g371_keys=%d | head_threshold=%s | hits=%d"
          % (known["reprojection_median_px"], known["state"], len(g371), model["threshold"],
             len(hits)))
    return state


def census(pinned: Path, out: Path) -> list[dict]:
    """Turn the raw pin file into `source_identity.csv`; the JSON column is parsed by position."""
    rows = []
    for line in Path(pinned).read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        path, size, digest, rest = line.split(",", 3)
        probe = json.loads(rest.strip().strip('"'))
        stream = probe["streams"][0]
        stem = Path(path).stem
        match = GID.match(stem.rpartition("__")[2] or stem)
        num, den = (stream.get("avg_frame_rate") or "0/1").split("/")
        rows.append({
            "section_id": stem, "game_id": stem.rsplit("_s", 1)[0],
            "video_id": (match["stem"].rpartition("-")[2] if match else ""),
            "offset_s": (match["off"] if match else ""), "source_path": path, "bytes": size,
            "source_sha256": digest, "width": stream["width"], "height": stream["height"],
            "fps": round(float(num) / float(den or 1), 6),
            "frame_count": int(stream.get("nb_frames") or 0),
            "duration_s": stream.get("duration", ""), "codec_name": stream.get("codec_name", "")})
    rows.sort(key=lambda row: (row["game_id"], row["section_id"]))
    _write(out, rows, SOURCE_FIELDS)
    print("CENSUS sections=%d games=%d min_frames=%d"
          % (len(rows), len({r["game_id"] for r in rows}), min(r["frame_count"] for r in rows)))
    return rows


def ticks(sources: Path, count: int, out: Path) -> list[dict]:
    """Expand every pinned section into its fixed evenly spaced strict-interior tick frames."""
    rows, short = [], []
    for source in _rows(sources):
        try:
            indices = interior_indices(int(source["frame_count"]), count)
        except ValueError:
            short.append(source["section_id"])
            continue
        for rank, index in enumerate(indices):
            row = {"source_sha256": source["source_sha256"], "section_id": source["section_id"],
                   "frame_index": str(index)}
            rows.append({**row, "frame_key": frame_key(row), "source_path": source["source_path"],
                         "game_id": source["game_id"], "tick_rank": rank})
    _write(out, rows, MANIFEST_FIELDS)
    print("TICKS frames=%d sections=%d too_short=%d"
          % (len(rows), len({r["section_id"] for r in rows}), len(short)))
    return rows


def eligible(predictions: Path, out: Path) -> list[dict]:
    """Per-section COURT share over its ticks; ABSTAIN and NON_COURT are counted, never COURT."""
    sections: dict[str, dict] = {}
    for row in _rows(predictions):
        entry = sections.setdefault(row["section_id"], {
            "section_id": row["section_id"], "game_id": row["game_id"], "n_ticks": 0,
            "n_court": 0, "n_non_court": 0, "n_abstain": 0})
        entry["n_ticks"] += 1
        entry["n_%s" % row["prediction"].lower()] += 1
    rows = []
    for entry in sorted(sections.values(), key=lambda item: (item["game_id"], item["section_id"])):
        share = entry["n_court"] / entry["n_ticks"]
        rows.append({**entry, "court_share": round(share, 6),
                     "eligible": int(share >= COURT_SHARE)})
    _write(out, rows, ("section_id", "game_id", "n_ticks", "n_court", "n_non_court", "n_abstain",
                       "court_share", "eligible"))
    keep = [row for row in rows if row["eligible"]]
    print("SCREEN sections=%d eligible=%d eligible_games=%d"
          % (len(rows), len(keep), len({row["game_id"] for row in keep})))
    return rows


def draw(screen: Path, out: Path, wanted: int = SECTIONS_WANTED) -> list[dict]:
    """The sealed seeded even draw: one section per game per pass, games ordered by seed digest."""
    keep = [row for row in _rows(screen) if row["eligible"] == "1"]
    games: dict[str, list[dict]] = {}
    for row in sorted(keep, key=lambda item: (item["game_id"], item["section_id"])):
        games.setdefault(row["game_id"], []).append(row)
    order = sorted(games, key=lambda game: hashlib.sha256(
        ("%s|%s" % (SEED_STRING, game)).encode("ascii")).hexdigest())
    passes = -(-wanted // max(1, len(order)))
    chosen: list[dict] = []
    for index in range(passes):
        for game in order:
            members = games[game]
            if len(members) <= index:
                continue
            position = ((index * (len(members) - 1)) // max(1, passes - 1)
                        if passes > 1 and len(members) > 1 else index)
            pick = members[min(position, len(members) - 1)]
            if pick["section_id"] in {row["section_id"] for row in chosen}:
                pick = next((m for m in members
                             if m["section_id"] not in {r["section_id"] for r in chosen}), None)
            if pick is not None and len(chosen) < wanted:
                chosen.append({**pick, "draw_rank": len(chosen), "draw_pass": index})
    _write(out, chosen, ("section_id", "game_id", "n_ticks", "n_court", "n_non_court", "n_abstain",
                         "court_share", "eligible", "draw_rank", "draw_pass"))
    print("DRAW selected=%d games=%d ids=%s"
          % (len(chosen), len({row["game_id"] for row in chosen}),
             ",".join(row["section_id"] for row in chosen)))
    return chosen


def margin_audit(predictions: Path, embeddings: Path, model_path: Path, out: Path) -> dict:
    """Reproduce the frozen head, add the true top-two margin, and preserve the legacy column."""
    import numpy as np

    from scripts.platformkit.tracking.g364_train import decisions, probabilities

    model = json.loads(Path(model_path).read_text(encoding="utf-8"))
    archive = np.load(embeddings)
    keys = [str(key) for key in archive["keys"]]
    values = np.asarray(archive["embeddings"], dtype=float)
    probs = probabilities(model, values)
    order = np.sort(probs, axis=1)
    calls = decisions(model, values, float(model["threshold"]))
    truth = {key: (float(row[-1] - row[-2]), float(prob[0]), call)
             for key, row, prob, call in zip(keys, order, probs, calls)}
    rows, legacy_ok, category_ok = [], 0, 0
    for row in _rows(predictions):
        top_two, court_probability, call = truth[row["frame_key"]]
        legacy = float(row["margin"])
        same_legacy = abs(legacy - top_two) <= 1e-9
        same_call = row["prediction"] == call
        legacy_ok += int(same_legacy)
        category_ok += int(same_call)
        rows.append({"frame_key": row["frame_key"], "section_id": row["section_id"],
                     "prediction": row["prediction"], "recomputed_prediction": call,
                     "court_probability": row["court_probability"],
                     "recomputed_court_probability": "%.9f" % court_probability,
                     "margin": row["margin"], "top_two_margin": "%.9f" % top_two,
                     "legacy_margin_reproduces": int(same_legacy),
                     "prediction_reproduces": int(same_call)})
    _write(out, rows, ("frame_key", "section_id", "prediction", "recomputed_prediction",
                       "court_probability", "recomputed_court_probability", "margin",
                       "top_two_margin", "legacy_margin_reproduces", "prediction_reproduces"))
    print("MARGIN_AUDIT n=%d legacy_margin_reproduces=%d prediction_reproduces=%d"
          % (len(rows), legacy_ok, category_ok))
    return {"n": len(rows), "legacy_margin_reproduces": legacy_ok,
            "prediction_reproduces": category_ok}


def main() -> None:
    parser = argparse.ArgumentParser(description="G379 premise, census, screen and draw")
    parser.add_argument("action", choices=("premise", "census", "ticks", "eligible", "draw",
                                           "margin-audit"))
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--pinned", type=Path)
    parser.add_argument("--sources", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--embeddings", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--screen", type=Path)
    parser.add_argument("--count", type=int, default=SCREEN_TICKS)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "premise":
        premise(args.evidence, args.out)
    elif args.action == "census":
        census(args.pinned, args.out)
    elif args.action == "ticks":
        ticks(args.sources, args.count, args.out)
    elif args.action == "eligible":
        eligible(args.predictions, args.out)
    elif args.action == "draw":
        draw(args.screen, args.out)
    else:
        margin_audit(args.predictions, args.embeddings, args.model, args.out)


if __name__ == "__main__":
    main()
