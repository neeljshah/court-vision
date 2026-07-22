"""Completeness analytics over the per-player dossier corpus.

Source: data/cache/profiles/PLAYER_REPORTS.json (1,249 dossiers, 28 categories
each). Read-only. Writes out/dossier_completeness.json + docs/img PNG bar chart.

Honesty: this measures DATA COMPLETENESS (how many of the 28 dossier sections
are populated), not prediction accuracy or edge. No $/ROI content here.
"""
import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CORPUS_CANDIDATES = [
    REPO / "data" / "cache" / "profiles" / "PLAYER_REPORTS.json",
]
OUT_JSON = Path(__file__).resolve().parent / "out" / "dossier_completeness.json"
OUT_PNG = REPO / "docs" / "img" / "dossier_completeness.png"


def locate_corpus():
    for p in CORPUS_CANDIDATES:
        if p.exists():
            return p
    return None


def analyze(corpus_path: Path) -> dict:
    data = json.loads(corpus_path.read_text(encoding="utf-8"))

    n_players = len(data)
    category_missing_count = Counter()
    filled_per_player = Counter()  # sections_present histogram
    scores = []

    all_categories = set()
    for p in data.values():
        dc = p.get("data_completeness", {})
        for c in dc.get("low_or_missing_sections", []):
            all_categories.add(c)

    for p in data.values():
        dc = p.get("data_completeness", {})
        missing = set(dc.get("low_or_missing_sections", []))
        for c in all_categories:
            if c in missing:
                category_missing_count[c] += 1
        present = dc.get("sections_present")
        if present is not None:
            filled_per_player[present] += 1
        score = dc.get("score")
        if score is not None:
            scores.append(score)

    category_fill_rate = {
        c: round(1 - category_missing_count[c] / n_players, 4)
        for c in sorted(all_categories)
    }
    scores.sort()
    median_score = scores[len(scores) // 2] if scores else None

    return {
        "status": "ok",
        "corpus_path": str(corpus_path.relative_to(REPO)),
        "dossiers_count": n_players,
        "categories_total": len(all_categories),
        "median_completeness_score": median_score,
        "category_fill_rate": category_fill_rate,
        "categories_filled_distribution": dict(sorted(filled_per_player.items())),
    }


def plot(result: dict, out_png: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rates = result["category_fill_rate"]
    cats = sorted(rates, key=lambda c: rates[c])
    vals = [rates[c] * 100 for c in cats]

    fig, ax = plt.subplots(figsize=(9, 8))
    ax.barh(cats, vals, color="#4C78A8")
    ax.set_xlabel("Fill rate (pct) across {} dossiers".format(result["dossiers_count"]))
    ax.set_title("Dossier category fill-rate (28 categories, measured)")
    ax.set_xlim(0, 100)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=120)
    plt.close(fig)


def main():
    corpus_path = locate_corpus()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    if corpus_path is None:
        result = {
            "status": "not_found",
            "paths_tried": [str(p) for p in CORPUS_CANDIDATES],
        }
        OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return

    result = analyze(corpus_path)
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    plot(result, OUT_PNG)

    print("dossiers_count:", result["dossiers_count"])
    print("categories_total:", result["categories_total"])
    print("median_completeness_score:", result["median_completeness_score"])
    print("wrote", OUT_JSON)
    print("wrote", OUT_PNG)


def _check():
    """Smallest self-check: fake a 2-player corpus, verify fill-rate math."""
    fake = {
        "1": {"data_completeness": {"sections_present": 2, "sections_total": 2,
                                     "low_or_missing_sections": ["b"]}},
        "2": {"data_completeness": {"sections_present": 1, "sections_total": 2,
                                     "low_or_missing_sections": ["a", "b"]}},
    }
    tmp = Path(__file__).resolve().parent / "out" / "_check_corpus.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(fake), encoding="utf-8")
    r = analyze(tmp)
    assert r["dossiers_count"] == 2
    assert r["category_fill_rate"]["a"] == 0.5   # missing for player 2 only
    assert r["category_fill_rate"]["b"] == 0.0   # missing for both
    tmp.unlink()
    print("self-check OK")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        _check()
    else:
        main()
