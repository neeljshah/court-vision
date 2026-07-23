"""Calibration atlas: small-multiple reliability cards from the ingame_grade_joined
row-level corpora (data/cache/ingame_grade_joined/{mlb,soccer_intl}; mlb_clean is a
verified byte-identical dup of mlb -- skipped, see state_conditioned_calibration.py).

Two card families, one flat manifest, both DESCRIPTIVE_ONLY / edge_claimed=False:
  A. time-checkpoint -- one per (sport x time-bucket): MLB innings 1-9 + a 10+
     bucket (10 cards), soccer 15-min buckets (6 cards) = 16 cards. Reliability
     curve, model vs market, plus n + ECE.
  B. prob-band -- one per (model-prob band x sport), reusing the canonical 5-band
     scheme from state_conditioned_calibration.py (5 bands x 2 sports = 10 cards).
     Outcome rate for that ONE band across the same sport's time-buckets from
     family A -- is "0.6-.8" the same 0.6-.8 in inning 1 as inning 9?

26 cards total -> docs/img/atlas/calibration/ ("calibration" used as atlas_factory's
"sport" slot, one flat dir, per this task's explicit target). Manifest:
out/atlas_calibration_manifest.json. Declared floor: >=MIN_N rows/card (see
FLOOR_LABEL; nothing in today's corpus falls below it).

Usage:
    python -m scripts.platformkit.analytics_showcase.calibration_atlas          # full build (ONE process)
    python -m scripts.platformkit.analytics_showcase.calibration_atlas --check  # manifest count == disk PNG count
"""
import glob
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.platformkit.analytics_showcase.atlas_factory import (
        card_figure, write_manifest, slugify, card_path, resolve_card_path, REPO_ROOT, OUT_DIR)
    from scripts.platformkit.analytics_showcase.state_conditioned_calibration import (
        PROB_BINS, PROB_LABELS, prob_bucket)
except ImportError:
    from atlas_factory import card_figure, write_manifest, slugify, card_path, resolve_card_path, REPO_ROOT, OUT_DIR
    from state_conditioned_calibration import PROB_BINS, PROB_LABELS, prob_bucket

ATLAS_BUCKET = "calibration"  # atlas_factory "sport" slot -> flat docs/img/atlas/calibration/
CARD_DIR = REPO_ROOT / "docs" / "img" / "atlas" / ATLAS_BUCKET
CORPUS_DIR = REPO_ROOT / "data" / "cache" / "ingame_grade_joined"
SPORTS = ["mlb", "soccer_intl"]  # mlb_clean skipped: byte-identical dup of mlb

INNING_RE = re.compile(r"inning=(\d+)")
MINUTE_RE = re.compile(r"minute=(\d+)")
MINUTE_BUCKETS = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 75), (75, 91)]  # soccer_calibration_pack parity

N_BINS = 5   # reliability-curve/ECE bin count -- kept small so the thinnest checkpoint (mlb 10+, n~112) isn't mostly empty bins
MIN_N = 30   # declared floor: a checkpoint/band card needs >=30 rows to render (never tuned to output)
FLOOR_LABEL = f"n>={MIN_N} rows required for a checkpoint/band card to render (declared floor, not tuned to today's data)"

MLB_BUCKET_ORDER = [str(i) for i in range(1, 10)] + ["10+"]
SOCCER_BUCKET_ORDER = [f"{lo}-{hi}" for lo, hi in MINUTE_BUCKETS]


def _mlb_bucket(state_summary):
    m = INNING_RE.search(state_summary or "")
    if not m:
        return None
    inning = int(m.group(1))
    return str(inning) if inning <= 9 else "10+"


def _soccer_bucket(state_summary):
    m = MINUTE_RE.search(state_summary or "")
    if not m:
        return None
    minute = int(m.group(1))
    for lo, hi in MINUTE_BUCKETS:
        if lo <= minute < hi:
            return f"{lo}-{hi}"
    return None


BUCKET_SCHEME = {
    "mlb": (_mlb_bucket, MLB_BUCKET_ORDER, "inning"),
    "soccer_intl": (_soccer_bucket, SOCCER_BUCKET_ORDER, "minute"),
}


def load_rows(sport):
    # ponytail: mirrors the inline loader every sibling module in this dir carries (calibration_over_time.py, murphy_decomposition.py, ...) -- same 3-field filter.
    rows = []
    for path in sorted(glob.glob(str(CORPUS_DIR / sport / "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("model_prob") is None or d.get("market_prob") is None or d.get("outcome") is None:
                    continue
                rows.append(d)
    return rows


def _reliability_curve(pairs, n_bins=N_BINS):
    """pairs: [(p, y), ...]. Returns (xs, ys, ece) from n_bins equal-width prob bins --
    same weighted-|mean_p-mean_y| ECE math as calibration_over_time.ece(), in one pass."""
    n = len(pairs)
    if n == 0:
        return [], [], None
    bins = [[] for _ in range(n_bins)]
    for p, y in pairs:
        idx = min(int(p * n_bins), n_bins - 1)
        bins[idx].append((p, y))
    xs, ys, ece_total = [], [], 0.0
    for b in bins:
        if not b:
            continue
        mean_p = sum(p for p, _ in b) / len(b)
        mean_y = sum(y for _, y in b) / len(b)
        xs.append(mean_p)
        ys.append(mean_y)
        ece_total += (len(b) / n) * abs(mean_p - mean_y)
    return xs, ys, round(ece_total, 4)


def _checkpoint_card(sport, label, rows, as_of):
    """Family A: one (sport x time-checkpoint) card -- reliability curve, model vs market, plus n + ECE."""
    n = len(rows)
    if n < MIN_N:
        return None
    mx, my, m_ece = _reliability_curve([(r["model_prob"], r["outcome"]) for r in rows])
    kx, ky, k_ece = _reliability_curve([(r["market_prob"], r["outcome"]) for r in rows])

    def panel_curve(ax):
        ax.plot(mx, my, marker="o", ms=3, lw=1, label="model")
        ax.plot(kx, ky, marker="s", ms=3, lw=1, label="market")
        ax.plot([0, 1], [0, 1], ls="--", lw=0.8, color="gray")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.legend(fontsize=5, loc="best")

    def panel_ece(ax):
        vals = [m_ece, k_ece]
        bars = ax.bar(["model", "market"], vals, color=["#1f77b4", "#d9a021"])
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.3f}", ha="center", va="bottom", fontsize=5)
        ax.set_ylabel("ECE", fontsize=6)

    unit = BUCKET_SCHEME[sport][2]
    entity = f"{sport} {unit} {label}"
    result = card_figure(
        title=f"{sport}: {unit} {label} reliability (n={n})",
        panels=[("reliability curve", panel_curve), ("ECE", panel_ece)],
        source_artifact=f"data/cache/ingame_grade_joined/{sport}",
        floors=FLOOR_LABEL,
        as_of=as_of,
        out_path=card_path(ATLAS_BUCKET, entity),
    )
    return {
        "entity": entity,
        "card_path": result["path"],
        "key_numbers": {"n": n, "model_ece": m_ece, "market_ece": k_ece},
        "floors": FLOOR_LABEL,
        "as_of": as_of,
        "card_type": "time_checkpoint",
        "sport": sport,
    }


def _band_card(sport, label, band_lo, band_hi, rows_all, as_of):
    """Family B: one (model-prob band x sport) card -- outcome rate across this sport's time-buckets, for rows whose model_prob falls in this ONE band."""
    bucket_fn, order, unit = BUCKET_SCHEME[sport]
    by_bucket = defaultdict(list)
    for r in rows_all:
        if prob_bucket(r["model_prob"]) != label:
            continue
        b = bucket_fn(r.get("state_summary"))
        if b is not None:
            by_bucket[b].append(r["outcome"])

    n_total = sum(len(v) for v in by_bucket.values())
    if n_total < MIN_N:
        return None
    xs_present = [b for b in order if by_bucket.get(b)]
    rates = [sum(by_bucket[b]) / len(by_bucket[b]) for b in xs_present]
    counts = [len(by_bucket[b]) for b in xs_present]
    ref = (band_lo + min(band_hi, 1.0)) / 2

    def panel_rate(ax):
        ax.plot(range(len(xs_present)), rates, marker="o", ms=3, lw=1, color="#1f77b4")
        ax.axhline(ref, ls="--", lw=0.8, color="gray")
        ax.set_xticks(range(len(xs_present))); ax.set_xticklabels(xs_present, fontsize=5, rotation=45)
        ax.set_ylim(0, 1); ax.set_ylabel("outcome rate", fontsize=6)

    def panel_n(ax):
        ax.bar(range(len(xs_present)), counts, color="#888888")
        ax.set_xticks(range(len(xs_present))); ax.set_xticklabels(xs_present, fontsize=5, rotation=45)
        ax.set_ylabel("n", fontsize=6)

    entity = f"{sport} band {label}"
    mean_y_overall = sum(sum(v) for v in by_bucket.values()) / n_total
    result = card_figure(
        title=f"{sport}: prob band {label} -- outcome rate by {unit} (n={n_total})",
        panels=[(f"outcome rate vs {unit}", panel_rate), (f"n vs {unit}", panel_n)],
        source_artifact=f"data/cache/ingame_grade_joined/{sport}",
        floors=FLOOR_LABEL,
        as_of=as_of,
        out_path=card_path(ATLAS_BUCKET, entity),
    )
    return {
        "entity": entity,
        "card_path": result["path"],
        "key_numbers": {
            "n": n_total,
            "mean_y_overall": round(mean_y_overall, 4),
            "band_reference": round(ref, 4),
            "n_time_buckets_with_data": len(xs_present),
            "by_time_bucket": [{"bucket": b, "n": len(by_bucket[b]),
                                 "mean_y": round(sum(by_bucket[b]) / len(by_bucket[b]), 4)} for b in xs_present],
        },
        "floors": FLOOR_LABEL,
        "as_of": as_of,
        "card_type": "prob_band",
        "sport": sport,
    }


def build_all():
    as_of = datetime.now(timezone.utc).isoformat()
    entries, skipped = [], []
    for sport in SPORTS:
        rows = load_rows(sport)
        if not rows:
            skipped.append({"sport": sport, "reason": "no rows found"})
            continue
        bucket_fn, order, _unit = BUCKET_SCHEME[sport]
        by_bucket = defaultdict(list)
        for r in rows:
            b = bucket_fn(r.get("state_summary"))
            if b is not None:
                by_bucket[b].append(r)
        for label in order:
            entry = _checkpoint_card(sport, label, by_bucket.get(label, []), as_of)
            if entry:
                entries.append(entry)
            else:
                skipped.append({"sport": sport, "checkpoint": label, "reason": "below MIN_N floor"})

        for lo, hi, label in zip(PROB_BINS[:-1], PROB_BINS[1:], PROB_LABELS):
            entry = _band_card(sport, label, lo, hi, rows, as_of)
            if entry:
                entries.append(entry)
            else:
                skipped.append({"sport": sport, "band": label, "reason": "below MIN_N floor"})

    return entries, skipped, as_of


def main() -> dict:
    entries, skipped, _as_of = build_all()
    manifest_path = write_manifest(ATLAS_BUCKET, entries)
    disk_pngs = list(CARD_DIR.glob("*.png"))
    total_bytes = sum(p.stat().st_size for p in disk_pngs)
    return {
        "manifest_entries": len(entries),
        "disk_pngs": len(disk_pngs),
        "floor": FLOOR_LABEL,
        "card_dir_bytes": total_bytes,
        "manifest_path": str(manifest_path),
        "example_entities": [e["entity"] for e in entries[:3]],
        "skipped": skipped,
    }


def _check():
    # pure-function sanity (hand-worked, no I/O)
    assert prob_bucket(0.15) == "0-.2"
    assert prob_bucket(0.65) == ".6-.8"
    assert prob_bucket(1.0) == ".8-1"
    assert _mlb_bucket("inning=3 half=top") == "3"
    assert _mlb_bucket("inning=11 half=bot") == "10+"
    assert _mlb_bucket("live") is None
    assert _soccer_bucket("minute=42") == "30-45"
    assert _soccer_bucket("minute=90") == "75-91"
    assert _soccer_bucket("home_score=0.0") is None
    xs, ys, ece = _reliability_curve([(0.5, 1.0)] * 10 + [(0.5, 0.0)] * 10, n_bins=5)
    assert abs(ece) < 1e-9, ece  # perfectly-calibrated single bin: mean_p==mean_y==0.5
    manifest_path = OUT_DIR / f"atlas_{ATLAS_BUCKET}_manifest.json"
    assert manifest_path.exists(), f"{manifest_path} missing -- run `python -m scripts.platformkit.analytics_showcase.calibration_atlas` first"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    disk_pngs = list(CARD_DIR.glob("*.png"))
    assert manifest["n_entries"] == len(disk_pngs), f"manifest says {manifest['n_entries']} entries but {len(disk_pngs)} PNGs on disk in {CARD_DIR}"
    for entry in manifest["entries"][:2]:
        p = resolve_card_path(entry["card_path"])
        assert p.exists() and p.stat().st_size > 0, f"card missing/empty: {p}"
    print(f"check ok: {manifest['n_entries']} manifest entries == {len(disk_pngs)} PNGs on disk")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        print(json.dumps(main(), indent=2))
