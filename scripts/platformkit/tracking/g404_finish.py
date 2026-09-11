"""G404 gate-audit scoring, contact sheet and delivery tables.

Joins the reviewer's blind labels to the sealed audit draw, applies the SEALED
joint-label bars through the prepared rails and records honestly that a single
reviewer can never satisfy a two-rater bar. Nothing here re-labels, re-draws or
re-renders a card.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g404_gate import read_csv, write_csv
from scripts.platformkit.tracking.g404_score import gate_audit_pass

AUDIT_FIELDS = ("card_id", "dispatch_position", "stratum", "frame_key", "video_id",
                "canonical_game", "competition", "pts", "frame_index", "width", "height",
                "card_sha256", "claude_label", "claude_support", "terra_label",
                "sol_label", "joint_label")
CONTACT_COLUMNS = 6
CONTACT_TILE = 320


def label_map(path: Path, rater: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return {row["card_id"]: row for row in read_csv(path) if row["rater"] == rater}


def joint(*labels: str) -> str:
    """A joint label exists only when every present rater agrees; else UNRESOLVED."""
    present = [value for value in labels if value]
    if len(present) < 2:
        return "SINGLE_REVIEWER_NO_JOINT_LABEL"
    return present[0] if len(set(present)) == 1 else "DISAGREEMENT"


def contact_sheet(rows: list[dict], cards: Path, out: Path) -> str:
    """One evenly ordered contact sheet over every audited card, both strata."""
    tiles = []
    for row in rows:
        image = cv2.imread(str(cards / (row["card_id"] + ".jpg")))
        if image is None:
            continue
        height = max(1, int(round(CONTACT_TILE * image.shape[0] / image.shape[1])))
        tiles.append(cv2.resize(image, (CONTACT_TILE, height), interpolation=cv2.INTER_AREA))
    if not tiles:
        raise ValueError("no card could be read for the contact sheet")
    tile_height = max(tile.shape[0] for tile in tiles)
    canvas_rows = []
    for start in range(0, len(tiles), CONTACT_COLUMNS):
        chunk = tiles[start:start + CONTACT_COLUMNS]
        padded = []
        for tile in chunk:
            frame = cv2.copyMakeBorder(tile, 0, tile_height - tile.shape[0], 0, 0,
                                       cv2.BORDER_CONSTANT, value=(0, 0, 0))
            padded.append(frame)
        while len(padded) < CONTACT_COLUMNS:
            padded.append(padded[-1] * 0)
        canvas_rows.append(cv2.hconcat(padded))
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.vconcat(canvas_rows), [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    return hashlib.sha256(out.read_bytes()).hexdigest()


def run(args) -> int:
    out = Path(args.out_dir)
    draw = read_csv(out / "gate_audit_draw.csv")
    claude = label_map(Path(args.claude_labels), "claude_finisher")
    terra = label_map(Path(args.terra_labels), "terra") if args.terra_labels else {}
    sol = label_map(Path(args.sol_labels), "sol") if args.sol_labels else {}
    rows = []
    for row in draw:
        mine = claude.get(row["card_id"], {})
        rows.append({**{field: row.get(field, "") for field in AUDIT_FIELDS},
                     "claude_label": mine.get("label", "UNVISITED"),
                     "claude_support": mine.get("support", ""),
                     "terra_label": terra.get(row["card_id"], {}).get("label", "NOT REACHED"),
                     "sol_label": sol.get(row["card_id"], {}).get("label", "NOT REACHED"),
                     "joint_label": joint(mine.get("label", ""),
                                          terra.get(row["card_id"], {}).get("label", ""),
                                          sol.get(row["card_id"], {}).get("label", ""))})
    write_csv(out / "gate_audit.csv", AUDIT_FIELDS, rows)
    admitted = [row for row in rows if row["stratum"] == "ADMITTED"]
    excluded = [row for row in rows if row["stratum"] == "EXCLUDED"]
    counts = {}
    for name, members in (("ADMITTED", admitted), ("EXCLUDED", excluded)):
        counts[name] = {label: sum(1 for row in members if row["claude_label"] == label)
                        for label in ("PLAY", "NONPLAY", "UNKNOWN", "UNVISITED")}
    sheet = contact_sheet(rows, Path(args.cards), out / "renders" / "gate_audit_cards.jpg")
    grid = read_csv(out / "gate_outputs.csv")
    census = read_csv(out / "census.csv")
    receipts = read_csv(out / "source_receipts.csv")
    premise = json.loads((out / "premise.json").read_text(encoding="ascii"))
    summary = {
        "row": "G404", "prereg_commit": args.prereg_commit,
        "amendment_a1_commit": args.amendment_commit,
        "census_utc": premise["census_utc"],
        "retained_sections_censused": premise["retained_sections"],
        "retained_games_censused": premise["retained_games"],
        "old_identities": premise["old_identities"],
        "eligible_new_games": premise["eligible_games"],
        "required_new_games": premise["required_games"],
        "competitions": premise["competitions"],
        "supply_premise_detail": (
            "14 resolved exact-ID-disjoint candidates across 2 competitions vs 30 required; "
            "relation to older alternate uploads remains unresolved"),
        "supply_premise": premise["premise"],
        "sources_retained": sum(1 for row in receipts if row["match"] == "MATCH"),
        "sources_pruned_before_retention": sum(1 for row in receipts
                                               if row["match"] == "ABSENT"),
        "census_rows": len(census),
        "candidate_grid_rows": len(grid),
        "gate_admitted": sum(1 for row in grid if row["gate_admitted"] == "1"),
        "gate_excluded": sum(1 for row in grid if row["gate_admitted"] == "0"),
        "gate_audit_cards": len(rows),
        "single_reviewer_counts": counts,
        "gate_audit_joint_bar": "NOT EVALUABLE: two independent raters are required and "
                                "only one reviewer visited the cards",
        "sealed_admitted_bar": 27, "sealed_excluded_bar": 24,
        "admitted_joint_play_upper_bound": counts["ADMITTED"]["PLAY"],
        "excluded_joint_nonplay_upper_bound": counts["EXCLUDED"]["NONPLAY"],
        "admitted_bar_reachable": counts["ADMITTED"]["PLAY"] >= 27,
        "excluded_bar_reachable": counts["EXCLUDED"]["NONPLAY"] >= 24,
        "gate_audit_pass": gate_audit_pass(
            [(row["terra_label"], row["sol_label"]) for row in admitted],
            [(row["terra_label"], row["sol_label"]) for row in excluded]),
        "controls_administered": 0, "ratings_collected": 0, "planned_keys_drawn": 0,
        "boxes_530_preserved": True, "g400_116_candidates_untouched": True,
        "registry_writes": 0, "flag_changes": 0, "gpu_minutes": 0,
        "contact_sheet_sha256": sheet,
        "verdict": args.verdict}
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                                      encoding="ascii", newline="\n")
    print(json.dumps({key: summary[key] for key in
                      ("eligible_new_games", "required_new_games", "supply_premise",
                       "gate_admitted", "gate_excluded", "gate_audit_pass", "verdict")},
                     sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g404_finish")
    for flag in ("--out-dir", "--cards", "--claude-labels", "--prereg-commit",
                 "--amendment-commit", "--verdict"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--terra-labels")
    parser.add_argument("--sol-labels")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
