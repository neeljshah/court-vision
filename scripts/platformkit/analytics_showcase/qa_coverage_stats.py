"""QA coverage stats: the answer-engine's own quality record, read straight
off two existing fail-closed producers -- no re-run, no new measurement:

  - data/cache/analytics_verify/qa_bank_report.json      (regression bank:
    PASS/FAIL of resolver_registry.resolve() against graded expectations --
    a correct no_data/not_supported/ambiguous is a PASS, not a failure)
  - data/cache/analytics_verify/coverage_stress_report.json (the honest
    coverage rate: n_expects_answer_true_ok / n_expects_answer_true, plus
    the full ok/no_data/not_supported/ambiguous/refused/error split by
    sport and category)

Story: a fail-closed answer engine measured on its own question bank --
~38% honest coverage with refusals BY DESIGN, not a bug.

Usage:
    python -m scripts.platformkit.analytics_showcase.qa_coverage_stats
    python -m scripts.platformkit.analytics_showcase.qa_coverage_stats --check
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_JSON = OUT_DIR / "qa_coverage_stats.json"
IMG_PATH = ROOT / "docs" / "img" / "qa_coverage_stats.png"

QA_BANK_PATH = ROOT / "data" / "cache" / "analytics_verify" / "qa_bank_report.json"
COVERAGE_STRESS_PATH = ROOT / "data" / "cache" / "analytics_verify" / "coverage_stress_report.json"

STATUS_ORDER = ["ok", "no_data", "not_supported", "ambiguous", "refused", "error"]


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build() -> dict:
    inputs_tried = [str(QA_BANK_PATH.relative_to(ROOT)), str(COVERAGE_STRESS_PATH.relative_to(ROOT))]
    qa_bank = _load(QA_BANK_PATH)
    stress = _load(COVERAGE_STRESS_PATH)

    if qa_bank is None or stress is None:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "no_data",
            "edge_claimed": False,
            "inputs_tried": inputs_tried,
            "reason": "one or both source artifacts missing -- run qa_runner / coverage_stress "
                      "producer first, or check paths above",
        }

    # status totals summed across the coverage_stress per-category breakdown
    status_totals = {k: 0 for k in STATUS_ORDER}
    for cat in stress["per_category"].values():
        for k in STATUS_ORDER:
            status_totals[k] += cat.get(k, 0)

    per_sport = stress["per_sport"]
    per_category_refusal = sorted(
        (
            {
                "category": name,
                "n": c["n"],
                "ok": c["ok"],
                "refusal": c["n"] - c["ok"],
                "ok_rate": round(c["ok"] / c["n"], 4) if c["n"] else None,
            }
            for name, c in stress["per_category"].items()
        ),
        key=lambda r: r["n"],
        reverse=True,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "edge_claimed": False,
        "inputs_tried": inputs_tried,
        "qa_regression_bank": {
            "source": str(QA_BANK_PATH.relative_to(ROOT)),
            "as_of": qa_bank["as_of"],
            "tier": qa_bank["tier"],
            "n_entries": qa_bank["n_entries"],
            "n_pass": qa_bank["n_pass"],
            "n_fail": qa_bank["n_fail"],
            "honest_note": qa_bank["honest_note"],
        },
        "coverage_stress": {
            "source": str(COVERAGE_STRESS_PATH.relative_to(ROOT)),
            "as_of": stress["as_of"],
            "n_rows": stress["n_rows"],
            "n_expects_answer_true": stress["n_expects_answer_true"],
            "n_expects_answer_true_ok": stress["n_expects_answer_true_ok"],
            "coverage_rate": stress["coverage_rate"],
            "coverage_rate_note": stress["coverage_rate_note"],
            "status_totals_all_rows": status_totals,
            "per_sport": per_sport,
            "per_category_by_volume": per_category_refusal,
        },
        "headline": (
            f"answer engine: {qa_bank['n_pass']}/{qa_bank['n_entries']} regression-bank checks pass "
            f"(fail-closed statuses graded as PASS); honest coverage "
            f"{stress['coverage_rate']:.1%} of answerable questions -- refusals "
            f"(no_data/not_supported/ambiguous/refused) are the fail-closed design, not a defect"
        ),
    }


def _plot(data: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax_bank, ax_split, ax_sport) = plt.subplots(1, 3, figsize=(15, 5.5))

    bank = data["qa_regression_bank"]
    ax_bank.bar(["pass", "fail"], [bank["n_pass"], bank["n_fail"]], color=["#2ca02c", "#d62728"])
    for i, v in enumerate([bank["n_pass"], bank["n_fail"]]):
        ax_bank.text(i, v + max(bank["n_pass"], 1) * 0.02, str(v), ha="center", fontsize=10)
    ax_bank.set_title(f"QA regression bank ({bank['n_entries']} graded questions)")
    ax_bank.set_ylabel("count")

    st = data["coverage_stress"]["status_totals_all_rows"]
    colors = {
        "ok": "#2ca02c", "no_data": "#7f7f7f", "not_supported": "#bcbd22",
        "ambiguous": "#ff7f0e", "refused": "#9467bd", "error": "#d62728",
    }
    labels = [k for k in STATUS_ORDER if st.get(k, 0) > 0]
    vals = [st[k] for k in labels]
    ax_split.bar(labels, vals, color=[colors[k] for k in labels])
    ax_split.set_title(f"Status split, all {data['coverage_stress']['n_rows']} stress rows")
    ax_split.tick_params(axis="x", rotation=30)
    ax_split.set_ylabel("count")

    sports = data["coverage_stress"]["per_sport"]
    names = list(sports.keys())
    ok_rate = [sports[s]["ok"] / sports[s]["n"] if sports[s]["n"] else 0 for s in names]
    ax_sport.bar(names, ok_rate, color="#1f77b4")
    for i, v in enumerate(ok_rate):
        ax_sport.text(i, v + 0.01, f"{v:.0%}", ha="center", fontsize=9)
    ax_sport.set_title("ok-rate by sport (coverage_stress bank)")
    ax_sport.set_ylabel("ok rate")
    ax_sport.set_ylim(0, 1)

    fig.suptitle(data["headline"], fontsize=9, y=1.02, wrap=True)
    fig.tight_layout()
    IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(IMG_PATH, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main(check: bool = False):
    data = build()
    if check:
        assert data["status"] in ("ok", "no_data"), "unexpected status"
        if data["status"] == "ok":
            assert data["qa_regression_bank"]["n_entries"] > 0, "empty qa bank"
            assert 0 <= data["coverage_stress"]["coverage_rate"] <= 1, "bad coverage_rate"
        print("check ok:", data["status"])
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"wrote {OUT_JSON}")
    if data["status"] == "ok":
        _plot(data)
        print(f"wrote {IMG_PATH}")
        print(data["headline"])
    else:
        print(f"no_data: {data['reason']}")


if __name__ == "__main__":
    import sys
    main(check="--check" in sys.argv)
