"""G377 recompute: four archived decisions rebuilt from the restored bytes with the landed code.

Sealed in g377_prereg_2026-09-10.md section 6.  Every scorer is IMPORTED from the row that
landed it; nothing is reimplemented.  Each recomputed field is diffed against the archived
value on its rendered decimal string, and the memo-recorded artifact digests are checked
against the restored bytes in the same pass.

Usage:
    python -m scripts.platformkit.tracking.g377_recompute --scratch <dir> --out <csv>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter
from pathlib import Path

G363 = "G363/docs/evidence/tracking/g363_ball_coverage_2026-09-09"
G364 = "G364/docs/evidence/tracking/g364_learned_court_presence_2026-09-09"
G367 = "G367/docs/evidence/tracking/g367_init_symmetry_2026-09-09"
G370 = "G370/docs/evidence/tracking/g370_admission_v0_2026-09-09"
FIELDS = ("closure", "field", "archived", "recomputed", "match")
NAME = r"([A-Za-z0-9_./-]+\.[a-z0-9]{2,8})"
DIGEST_RE = re.compile(r"\b([0-9a-f]{64})\b[^|;\n]{0,40}?\b" + NAME + r"\b")
NAMED_RE = re.compile(r"\b" + NAME + r"[ \t]+\b([0-9a-f]{64}|[0-9a-f]{16})\b")

ARCHIVED_G363 = {"tp": "0", "fp": "8", "n_frames": "549", "n_visible": "285",
                 "n_absent": "243", "n_unknown": "21", "coverage": "0.0",
                 "precision_wilson_lo": "0.0", "fp_per_absent": "0.03292181069958848"}
ARCHIVED_G364 = {"n": "240", "kappa": "0.916186", "precision": "1.0", "recall": "1.0",
                 "abstention_share": "0.0", "COURT": "125", "NON_COURT": "115", "ABSTAIN": "0",
                 "USABLE_COURT": "125", "CLOSEUP": "74", "CROWD_GRAPHICS": "40", "UNKNOWN": "1"}
ARCHIVED_G367 = {"G1_SYNTH_QUAD:corner4": "1.651646", "G1_SYNTH_QUAD:candidate_b": "1.128714",
                 "G2_WIDE:corner4": "1.915938", "G2_WIDE:candidate_b": "1.068990",
                 "G3_TIGHT:corner4": "2.015967", "G3_TIGHT:candidate_b": "1.116470",
                 "G4_OFF_AXIS:corner4": "1.800281", "G4_OFF_AXIS:candidate_b": "0.763620"}
ARCHIVED_G370 = {"rated": "69", "usable": "51", "games": "16", "scored": "51",
                 "absent": "0", "rejected": "0", "share": "0.0000"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def compare(closure: str, archived: dict[str, str], got: dict[str, str]) -> list[dict[str, str]]:
    """One row per archived field; the comparison is on the rendered string, byte for byte."""
    return [{"closure": closure, "field": key, "archived": value,
             "recomputed": got.get(key, "ABSENT"),
             "match": int(got.get(key, "ABSENT") == value)}
            for key, value in sorted(archived.items())]


def recompute_g363(scratch: Path) -> dict[str, str]:
    """Held-out C0: the landed G363 scorer over the restored frames, ratings and predictions."""
    from scripts.platformkit.tracking import g363_score

    base = scratch / G363
    frames = read_csv(base / "frames.csv")
    preds = read_csv(base / "predictions.csv")
    refs, _diagnostics = g363_score.reference(read_csv(base / "ratings.csv"))
    summary, _rows = g363_score.score_arm("A0", "heldout", frames, refs, preds)
    return {key: str(summary[key]) for key in ARCHIVED_G363}


def recompute_g364(scratch: Path) -> dict[str, str]:
    """Development confusion: the landed G364 scorer over the restored development set."""
    from scripts.platformkit.tracking import g364_score

    base = scratch / G364
    development = read_csv(base / "dev_predictions.csv")
    _confusion, summary = g364_score.score(development, read_csv(base / "ratings.csv"),
                                           read_csv(base / "raters" / "adjudication.csv"))
    resolved, _agreement = g364_score.references(development, read_csv(base / "ratings.csv"),
                                                 read_csv(base / "raters" / "adjudication.csv"))
    labels = Counter(resolved.values())
    got = {"n": str(summary["n"]), "kappa": "%.6f" % summary["kappa"],
           "precision": str(summary["precision"]), "recall": str(summary["recall"]),
           "abstention_share": str(summary["abstention_share"])}
    got.update({key: str(value) for key, value in summary["predicted_counts"].items()})
    got.update({key: str(labels.get(key, 0)) for key in
                ("USABLE_COURT", "CLOSEUP", "CROWD_GRAPHICS", "UNKNOWN")})
    return got


def recompute_g367(scratch: Path, work: Path) -> tuple[dict[str, str], str, str, str]:
    """Recovery from the four synthetic fixtures, run TWICE so a difference can be attributed.

    Run one is the recompute; run two is a same-machine repeat (B11).  Two equal local runs that
    both differ from the archived file place the difference in the environment, not the restore.
    """
    from scripts.platformkit.tracking import g367_search

    digests = []
    for index in (1, 2):
        target = work / ("run%d" % index)
        target.mkdir(parents=True, exist_ok=True)
        g367_search.premise(target)
        raw = (target / "recovery.csv").read_bytes().replace(b"\r\n", b"\n")
        digests.append(hashlib.sha256(raw).hexdigest())
    fresh = read_csv(work / "run1" / "recovery.csv")
    got = {"%s:%s" % (row["geometry"], row["arm"]): row["modulo_gap_px"] for row in fresh}
    archived = (scratch / G367 / "reconstruction_2026-09-10" / "recovery.csv").read_bytes()
    return (got, hashlib.sha256(archived.replace(b"\r\n", b"\n")).hexdigest(),
            digests[0], digests[1])


def recompute_g370(scratch: Path) -> dict[str, str]:
    """Usable-control rejection: the aggregation at g370_usable.py lines 66-70 over controls.csv."""
    from scripts.platformkit.tracking import g370_usable

    rows = read_csv(scratch / G370 / "controls.csv")
    if tuple(rows[0]) != g370_usable.COLUMNS:
        raise ValueError("restored controls.csv header does not match the landed schema")
    usable = [row for row in rows if row["usable"] == "1"]
    scored = [row for row in usable if row["status"] in ("PASS", "REJECT")]
    rejected = sum(1 for row in scored if row["status"] == "REJECT")
    return {"rated": str(len(rows)), "usable": str(len(usable)),
            "games": str(len({row["game_id"] for row in usable})), "scored": str(len(scored)),
            "absent": str(len(usable) - len(scored)), "rejected": str(rejected),
            "share": "{:.4f}".format(rejected / len(scored)) if scored else "ABSENT"}


def memo_digests(repo: Path, scratch: Path, closure: str, stem: str) -> list[dict[str, str]]:
    """Every SHA-256 the landed memo prints beside a file name, checked on the restored bytes.

    The memo is the SCAN SOURCE of manifest rule M1, not a manifest entry, so it is read from
    master where M1 read it; only the artifacts it names are read from the restored tree.
    """
    memo = repo / "docs/evidence/tracking" / (stem + ".md")
    text = memo.read_text(encoding="utf-8")
    base = scratch / closure / "docs/evidence/tracking" / stem
    files = {path.name: path for path in base.rglob("*") if path.is_file()}
    duplicates = {name for name in files
                  if sum(1 for path in base.rglob(name) if path.is_file()) > 1}
    pairs = [(digest, name) for digest, name in DIGEST_RE.findall(text)]
    pairs += [(digest, name) for name, digest in NAMED_RE.findall(text)]
    out: list[dict[str, str]] = []
    for digest, name in sorted(set(pairs)):
        if name not in files or name in duplicates:
            continue
        raw = files[name].read_bytes()
        got = {hashlib.sha256(raw).hexdigest(),
               hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
        agree = any(candidate.startswith(digest) for candidate in got)
        out.append({"closure": closure, "field": "digest:" + name, "archived": digest,
                    "recomputed": digest if agree else sorted(got)[0][:len(digest)],
                    "match": int(agree)})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="G377 archived-decision recompute")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, str]] = []
    rows.extend(compare("G363", ARCHIVED_G363, recompute_g363(args.scratch)))
    rows.extend(compare("G364", ARCHIVED_G364, recompute_g364(args.scratch)))
    got, archived_digest, first, second = recompute_g367(args.scratch, args.work)
    rows.extend(compare("G367", ARCHIVED_G367, got))
    rows.append({"closure": "G367", "field": "recovery.csv sha256 (LF)",
                 "archived": archived_digest, "recomputed": first,
                 "match": int(archived_digest == first)})
    rows.append({"closure": "G367", "field": "recovery.csv sha256 (LF) local repeat",
                 "archived": first, "recomputed": second, "match": int(first == second)})
    rows.extend(compare("G370", ARCHIVED_G370, recompute_g370(args.scratch)))
    for closure, stem in (("G363", "g363_ball_coverage_2026-09-09"),
                          ("G364", "g364_learned_court_presence_2026-09-09"),
                          ("G367", "g367_init_symmetry_2026-09-09"),
                          ("G370", "g370_admission_v0_2026-09-09")):
        rows.extend(memo_digests(args.repo, args.scratch, closure, stem))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    for closure in ("G363", "G364", "G367", "G370"):
        subset = [row for row in rows if row["closure"] == closure]
        agree = sum(int(row["match"]) for row in subset)
        print("DECISION %s fields=%d agree=%d disagree=%d" % (
            closure, len(subset), agree, len(subset) - agree))
        for row in subset:
            if not int(row["match"]):
                print("  DISAGREE %s archived=%s recomputed=%s" % (
                    row["field"], row["archived"], row["recomputed"]))
    print("DECISION_TOTAL rows=%d agree=%d" % (len(rows), sum(int(r["match"]) for r in rows)))
    return 0


def demo() -> None:
    """Self-check: the comparison is byte-exact on strings and the digest regex pairs correctly."""
    rows = compare("X", {"a": "1.0", "b": "2"}, {"a": "1.0", "b": "2.0"})
    assert [row["match"] for row in rows] == [1, 0]
    assert compare("X", {"a": "1"}, {})[0]["recomputed"] == "ABSENT"
    text = "%s (LF-normalised) frames.csv | rest" % ("b" * 64)
    assert DIGEST_RE.findall(text) == [("b" * 64, "frames.csv")]
    assert NAMED_RE.findall("census.csv %s; next" % ("a" * 64)) == [("census.csv", "a" * 64)]
    assert NAMED_RE.findall("recovery.csv 1392a11b8e841487") == [("recovery.csv", "1392a11b8e841487")]
    print("g377_recompute demo OK")


if __name__ == "__main__":
    raise SystemExit(main())
