"""Cross-sport calibration-transfer table: composes the Murphy reliability/
resolution decomposition (murphy_decomposition.py / soccer_calibration_pack.py)
alongside the nba/mlb/tennis benchmark + gate artifacts into ONE row per
sport-market. Reads only -- computes nothing new, every number already exists
in a source artifact.

Reliability is only "transferable" (plotted on one axis) where two forecasts
score the SAME kind of object: a probability of a binary outcome, scored by
Brier -- true for mlb-moneyline and soccer_intl-moneyline only. CRPS
(mlb totals/margin, run-scale) is a different unit and is never forced onto
that axis, nor is nba (no bin-level decomposition computed locally) or tennis
(no market side, so reliability is undefined). Those rows carry a verdict +
an explicit "why not comparable" reason instead of a fabricated number.

edge_claimed is always False. Verdicts are copied/summarized verbatim from
source, never recomputed.

Usage:
    python -m scripts.platformkit.analytics_showcase.kernel_transfer [--check]
"""
import json
import textwrap
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHOWCASE_DIR = Path(__file__).resolve().parent
CRPS_DIR = ROOT / "scripts" / "platformkit" / "benchmarks" / "crps_market"
OUT_JSON = SHOWCASE_DIR / "out" / "kernel_transfer.json"
OUT_PNG = ROOT / "docs" / "img" / "kernel_transfer.png"

MURPHY_JSON = SHOWCASE_DIR / "out" / "murphy_decomposition.json"
SOCCER_PACK_JSON = SHOWCASE_DIR / "out" / "soccer_calibration_pack.json"
TENNIS_JSON = SHOWCASE_DIR / "out" / "tennis_showcase.json"
NBA_JSON = CRPS_DIR / "last_run_ingame_nba_winprob_ALLGAMES_v3.json"
MLB_PREGAME_JSON = CRPS_DIR / "last_run_mlb.json"
MLB_INGAME_JSON = CRPS_DIR / "last_run_ingame_mlb.json"

# This task's research context covered two OTHER analytics in this repo
# (market info-arrival curve; market over/underreaction spectrum) -- neither
# is this file, so nothing from those checks is borrowed here.
NOVELTY = {
    "analytic": ("kernel_transfer: cross-sport calibration-transfer table -- Murphy "
                 "reliability/resolution composed across nba/mlb/soccer/tennis, "
                 "comparability-gated so CRPS never shares an axis with Brier"),
    "verdict": "ALREADY_DONE_ON_CORE_METHOD (composition/gate not independently researched)",
    "note": ("The decomposition (Brier = reliability - resolution + uncertainty) is the "
             "classical Murphy (1973) forecast-verification partition -- textbook standard, "
             "already implemented verbatim by murphy_decomposition.py in this repo. This "
             "file adds no new decomposition math, only a cross-sport composition with an "
             "explicit comparability gate. No external prior-art search was run specifically "
             "for that composition/gate -- do not read this as 'first ever'; it is simply "
             "unverified against literature, so nothing beyond internal composition is claimed."),
    "closest_known_prior_work": ("Murphy, A.H. (1973), 'A New Vector Partition of the "
                                  "Probability Score', Journal of Applied Meteorology 12(4):"
                                  "595-600 -- the reliability/resolution/uncertainty split "
                                  "this repo's murphy_decomposition.py already implements."),
}

COMPARABILITY_REASON = ("both sides are Brier scores of a probability against a binary "
                         "win/loss outcome -- the reliability component (mean squared "
                         "calibration error, weighted by bin mass) is on the same 0-1 "
                         "probability scale in both sports, the one honest cross-sport axis here.")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(path):
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _split_mlb_soccer_verdict(full_verdict):
    """murphy_decomposition.json's verdict is one string, mlb sentence then
    soccer_intl sentence -- split on the known boundary, verbatim both sides."""
    if "soccer_intl:" in full_verdict:
        mlb_clause, rest = full_verdict.split("soccer_intl:", 1)
        return mlb_clause.strip(), ("soccer_intl:" + rest).strip()
    return full_verdict, full_verdict


def build_rows():
    murphy = _load(MURPHY_JSON)
    soccer_pack = _load(SOCCER_PACK_JSON)
    tennis = _load(TENNIS_JSON)
    nba = _load(NBA_JSON)
    mlb_pregame = _load(MLB_PREGAME_JSON)
    mlb_ingame = _load(MLB_INGAME_JSON)
    mlb_clause, soccer_clause = _split_mlb_soccer_verdict(murphy["verdict"])
    rows = []

    mm, mk = murphy["sports"]["mlb"]["model_prob"], murphy["sports"]["mlb"]["market_prob"]
    rows.append({
        "sport": "mlb", "market": "moneyline_ingame (murphy reliability decomposition)",
        "reliability_model": mm["reliability"], "reliability_market": mk["reliability"],
        "reliability_gap": round(mm["reliability"] - mk["reliability"], 6),
        "reliability_unit": "brier_reliability_component (probability scale, 0-1)",
        "reliability_comparable": True, "comparability_reason": COMPARABILITY_REASON,
        "n": mm["n"], "verdict": mlb_clause, "sources": [_rel(MURPHY_JSON)],
    })

    ing_cps = mlb_ingame["checkpoints"]
    ing_counts = Counter(v["verdict"] for v in ing_cps.values())
    ing_summary = ", ".join(f"{v}: {n}" for v, n in sorted(ing_counts.items()))
    rows.append({
        "sport": "mlb", "market": "totals_margin (CRPS distributional, pregame+ingame)",
        "reliability_model": None, "reliability_market": None, "reliability_gap": None,
        "reliability_unit": None, "reliability_comparable": False,
        "comparability_reason": ("CRPS scores a full run-count distribution, not a binary "
                                  "outcome probability -- Murphy reliability/resolution is "
                                  "undefined for it here; never forced onto the Brier axis above."),
        "n": mlb_pregame["n_scored"] + sum(v["n"] for v in ing_cps.values()),
        "verdict": (f"pregame total_runs: {mlb_pregame['verdict']} (n={mlb_pregame['n_scored']}). "
                    f"ingame ({len(ing_cps)} checkpoints, home_margin+total_runs): {ing_summary}."),
        "sources": [_rel(MLB_PREGAME_JSON), _rel(MLB_INGAME_JSON)],
    })

    sm, sk = soccer_pack["murphy"]["model_prob"], soccer_pack["murphy"]["market_prob"]
    rows.append({
        "sport": "soccer_intl", "market": "moneyline_ingame (murphy reliability decomposition)",
        "reliability_model": sm["reliability"], "reliability_market": sk["reliability"],
        "reliability_gap": round(sm["reliability"] - sk["reliability"], 6),
        "reliability_unit": "brier_reliability_component (probability scale, 0-1)",
        "reliability_comparable": True, "comparability_reason": COMPARABILITY_REASON,
        "n": sm["n"], "verdict": soccer_clause + " " + soccer_pack["honest_note"],
        "sources": [_rel(SOCCER_PACK_JSON), _rel(MURPHY_JSON)],
    })

    nba_cps = nba["checkpoints"]
    rows.append({
        "sport": "nba", "market": "winprob_ingame (Brier, no reliability decomposition)",
        "reliability_model": None, "reliability_market": None, "reliability_gap": None,
        "reliability_unit": None, "reliability_comparable": False,
        "comparability_reason": ("nba's benchmark stores per-checkpoint Brier MEANS only -- "
                                  "no 10-bin Murphy reliability/resolution split has been "
                                  "computed locally for nba win-prob, honest gap not an estimate."),
        "n": nba["n_checkpoints_scored"],
        "verdict": "; ".join(f"{k}: {v['verdict']}" for k, v in nba_cps.items()),
        "sources": [_rel(NBA_JSON)],
    })

    pre, surf = tennis["pregame_prior_cross_corpus"], tennis["ingame_surface_context"]
    d1 = pre["directions"]["atp_train_wta_test"]["prior_beats_base"]
    d2 = pre["directions"]["wta_train_atp_test"]["prior_beats_base"]
    rows.append({
        "sport": "tennis", "market": "pregame_prior + ingame_surface_gate (no market side)",
        "reliability_model": None, "reliability_market": None, "reliability_gap": None,
        "reliability_unit": None, "reliability_comparable": False,
        "comparability_reason": ("both tennis gate receipts are model-vs-model checks (prior vs "
                                  "base; surface-specific vs surface-blind) -- no market_prob to "
                                  "decompose against, reliability undefined by construction."),
        "n": pre["coverage"]["a_states"] + pre["coverage"]["b_states"],
        "verdict": (f"pregame_prior_cross_corpus: {pre['verdict']} (prior beats base out-of-corpus "
                    f"both directions: atp_train_wta_test={d1}, wta_train_atp_test={d2}). "
                    f"ingame_surface_context: {surf['verdict']} ({surf['reason']})"),
        "sources": [_rel(TENNIS_JSON)],
    })
    return rows


def _transfer_summary(rows):
    comparable = [r for r in rows if r["reliability_comparable"]]
    if len(comparable) < 2:
        return "Fewer than 2 sports have a comparable reliability component -- no cross-sport read possible."
    gaps = [r["reliability_gap"] for r in comparable]
    sports = [r["sport"] for r in comparable]
    same_sign = len({g > 0 for g in gaps}) == 1
    ratio = max(abs(g) for g in gaps) / max(min(abs(g) for g in gaps), 1e-9)
    return (f"Only {len(comparable)} of {len({r['sport'] for r in rows})} sports have a Murphy "
            f"reliability component measured against market ({', '.join(sports)}). Sign agrees "
            f"(model less reliable than market in both): {same_sign}. Magnitude differs by "
            f"~{ratio:.1f}x ({dict(zip(sports, gaps))}). n=2 sports is not enough to call this a "
            f"general cross-sport pattern -- a same-direction coincidence worth re-checking if a "
            f"3rd sport gets a market-side Murphy decomposition, not a claim.")


def build():
    rows = build_rows()
    payload = {
        "edge_claimed": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": ("composition only -- reliability/resolution numbers copied verbatim from "
                   "murphy_decomposition.py / soccer_calibration_pack.py output; verdicts "
                   "copied/summarized verbatim from each source artifact, nothing recomputed"),
        "n_rows": len(rows),
        "rows": rows,
        "comparable_groups": {
            "brier_reliability_prob_scale": [f"{r['sport']}/{r['market']}" for r in rows if r["reliability_comparable"]],
            "not_comparable_reasons": {f"{r['sport']}/{r['market']}": r["comparability_reason"] for r in rows if not r["reliability_comparable"]},
        },
        "reliability_transfer_summary": _transfer_summary(rows),
        "novelty": NOVELTY,
        "honest_note": ("This table's only cross-sport-comparable number is the Murphy reliability "
                         "component, for 2 of 4 sports where a market-side probability decomposition "
                         "exists (mlb moneyline, soccer_intl moneyline). CRPS (mlb totals/margin), "
                         "Brier-without-decomposition (nba), and no-market gates (tennis) are verdict "
                         "text only, never coerced onto the reliability axis."),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def plot(payload):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    sports = ["nba", "mlb", "soccer_intl", "tennis"]
    fig, axes = plt.subplots(1, len(sports), figsize=(16, 5.5))
    for ax, sport in zip(axes, sports):
        sport_rows = [r for r in payload["rows"] if r["sport"] == sport]
        ax.set_title(sport, fontsize=12, fontweight="bold")
        rel_row = next((r for r in sport_rows if r["reliability_comparable"]), None)
        if rel_row:
            vals = [rel_row["reliability_model"], rel_row["reliability_market"]]
            bars = ax.bar(["model", "market"], vals, color=["#4a6fa5", "#c0392b"], width=0.5)
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.4f}", ha="center", va="bottom", fontsize=8)
            ax.set_ylabel("Murphy reliability\n(Brier scale, comparable)", fontsize=8)
            ax.set_ylim(0, max(vals) * 1.5)
        else:
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            ax.text(0.5, 0.55, "no reliability\ndecomposition\navailable", ha="center", va="center",
                     fontsize=9, color="#888888", transform=ax.transAxes)
        caption = "\n\n".join(
            f"{r['market'].split(' (')[0]}:\n" + textwrap.fill(r["verdict"], 40) for r in sport_rows
        )
        ax.text(0.5, -0.08, caption, ha="center", va="top", fontsize=6.2, transform=ax.transAxes)

    fig.suptitle("Cross-sport calibration transfer -- Murphy reliability where comparable "
                  "(Brier prob-scale, 2/4 sports); verdict-only elsewhere\n"
                  "edge_claimed=False -- composition only, CRPS and Brier never share an axis",
                  fontsize=10)
    fig.subplots_adjust(bottom=0.45, top=0.82, wspace=0.5)
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_PNG, dpi=150)
    plt.close(fig)


def check():
    assert OUT_JSON.exists(), "kernel_transfer JSON missing"
    d = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert d["edge_claimed"] is False
    assert d["n_rows"] == len(d["rows"]) > 0
    comparable = [r for r in d["rows"] if r["reliability_comparable"]]
    assert len(comparable) == 2, f"expected exactly 2 comparable rows, got {len(comparable)}"
    for r in comparable:
        assert isinstance(r["reliability_model"], float) and isinstance(r["reliability_market"], float)
    for r in d["rows"]:
        assert r["verdict"]
    assert d["novelty"]["verdict"], "novelty block missing a verdict"
    assert OUT_PNG.exists(), "kernel_transfer PNG missing"
    print(f"OK: {d['n_rows']} rows, {len(comparable)} reliability-comparable, image at {OUT_PNG}")


if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        check()
    else:
        payload = build()
        plot(payload)
        check()
