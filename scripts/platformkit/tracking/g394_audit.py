"""G394 negative audit: adjudicate the two blind NO_BALL ratings into the manifest.

The acceptance rule is fixed by the sealed preregistration and by this module BEFORE
any rating is read: a crop is accepted only when BOTH independent raters return
NO_BALL_VISIBLE without HIGH uncertainty. A ball call, an uncertain call, a HIGH
uncertainty or a missing rating disqualifies that crop, and nothing replaces it.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

RATERS = ("terra", "sol")
ACCEPT_STATE = "NO_BALL_VISIBLE"
DISQUALIFYING_UNCERTAINTY = "HIGH"
MIN_ACCEPTED = 30
MIN_GAMES = 5
AGREEMENT_FIELDS = ("packet_id", "frame_key", "game", "terra_state", "terra_uncertainty",
                    "sol_state", "sol_uncertainty", "accepted", "exclusion_reason")
ACCEPTED_FIELDS = ("packet_id", "frame_key", "game", "section", "frame_index",
                   "call_cx", "call_cy", "crop_sha256")


def rows(path: Path) -> list[dict[str, str]]:
    """Read one bounded CSV input."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: tuple[str, ...], records: list[dict]) -> None:
    """Write one ASCII CSV checkpoint with fixed field order."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="ascii", newline="\n") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def verdict(first: dict[str, str] | None, second: dict[str, str] | None) -> tuple[int, str]:
    """Apply the fixed two-rater acceptance rule to one selected crop."""
    reasons = []
    for name, rating in zip(RATERS, (first, second)):
        if rating is None:
            reasons.append(name + "_MISSING_RATING")
            continue
        if rating["ball_state"] != ACCEPT_STATE:
            reasons.append(name + "_" + rating["ball_state"])
        elif rating["uncertainty"] == DISQUALIFYING_UNCERTAINTY:
            reasons.append(name + "_UNCERTAINTY_HIGH")
    return (0, "|".join(reasons)) if reasons else (1, "")


def adjudicate(manifest: list[dict[str, str]], ratings: list[dict[str, str]]) -> tuple[
        list[dict], list[dict], dict[str, object]]:
    """Return the agreement table, the accepted manifest and the audit counts."""
    by_rater = {name: {row["packet_id"]: row for row in ratings if row["rater"] == name}
                for name in RATERS}
    agreement, accepted = [], []
    for row in manifest:
        packet = row["packet_id"]
        first, second = by_rater[RATERS[0]].get(packet), by_rater[RATERS[1]].get(packet)
        ok, reason = verdict(first, second)
        agreement.append({
            "packet_id": packet, "frame_key": row["frame_key"], "game": row["game"],
            "terra_state": first["ball_state"] if first else "",
            "terra_uncertainty": first["uncertainty"] if first else "",
            "sol_state": second["ball_state"] if second else "",
            "sol_uncertainty": second["uncertainty"] if second else "",
            "accepted": ok, "exclusion_reason": reason})
        if ok:
            accepted.append({name: row[name] for name in ACCEPTED_FIELDS})
    states = {name: {} for name in RATERS}
    for name in RATERS:
        for rating in by_rater[name].values():
            states[name][rating["ball_state"]] = states[name].get(rating["ball_state"], 0) + 1
    both = [row for row in agreement if row["terra_state"] and row["sol_state"]]
    agreed = sum(1 for row in both if row["terra_state"] == row["sol_state"])
    counts = {
        "selected": len(manifest), "rated_by_terra": len(by_rater[RATERS[0]]),
        "rated_by_sol": len(by_rater[RATERS[1]]), "rated_by_both": len(both),
        "raw_state_agreement": round(agreed / len(both), 6) if both else None,
        "accepted": len(accepted),
        "accepted_games": len({row["game"] for row in accepted}),
        "accepted_unique_frames": len({row["frame_key"] for row in accepted}),
        "excluded": len(manifest) - len(accepted),
        "exclusion_reasons": _tally(agreement), "rater_states": states,
        "meets_supply_bar": (len(accepted) >= MIN_ACCEPTED
                             and len({row["game"] for row in accepted}) >= MIN_GAMES
                             and len({row["frame_key"] for row in accepted}) == len(accepted)),
        "min_accepted": MIN_ACCEPTED, "min_games": MIN_GAMES}
    return agreement, accepted, counts


def _tally(agreement: list[dict]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for row in agreement:
        if row["exclusion_reason"]:
            tally[row["exclusion_reason"]] = tally.get(row["exclusion_reason"], 0) + 1
    return tally


def eye_check(agreement: list[dict], cards_dir: Path, out: Path, count: int = 30) -> list[dict]:
    """Copy 30 evenly spaced context/crop cards, exclusions included, with an index."""
    import shutil

    ordered = sorted(agreement, key=lambda row: row["packet_id"])
    picked = [ordered[round(i * (len(ordered) - 1) / (count - 1))] for i in range(count)]
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for position, row in enumerate(picked):
        name = row["packet_id"] + ".jpg"
        shutil.copyfile(cards_dir / name, out / name)
        index.append({"position": position, "packet_id": row["packet_id"],
                      "accepted": row["accepted"], "exclusion_reason": row["exclusion_reason"],
                      "card": name})
    write_csv(out / "cards_index.csv",
              ("position", "packet_id", "accepted", "exclusion_reason", "card"), index)
    return index


def main(argv: list[str] | None = None) -> int:
    """Adjudicate the sealed selection and emit the audit artifacts."""
    parser = argparse.ArgumentParser(prog="g394_audit")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--ratings", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--cards-dir")
    args = parser.parse_args(argv)
    out = Path(args.out_dir)
    manifest = rows(Path(args.manifest))
    ratings = rows(Path(args.ratings))
    agreement, accepted, counts = adjudicate(manifest, ratings)
    write_csv(out / "audit_agreement.csv", AGREEMENT_FIELDS, agreement)
    write_csv(out / "accepted_negatives.csv", ACCEPTED_FIELDS, accepted)
    if args.cards_dir:
        counts["eye_check_cards"] = len(
            eye_check(agreement, Path(args.cards_dir), out / "cards"))
    (out / "audit_counts.json").write_text(
        json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="ascii", newline="\n")
    print("G394 AUDIT COMPLETE " + json.dumps(counts, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
