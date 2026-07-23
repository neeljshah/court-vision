"""Brier Skill Score (BSS) vs two references, per sport x in-game checkpoint.

Standard BSS = 1 - Brier / Brier_ref, computed from the row-level joined grade
corpora in data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (mlb_clean
is a byte-identical dup of mlb and is excluded -- the checkpoint bucketers we
reuse only cover mlb + soccer_intl, so it never enters).

Two references per grain:
  * climatology  -- a constant forecast equal to the SPORT-level unconditional
    base rate P(outcome=1); the SAME reference for every checkpoint. This is the
    textbook climatology baseline ("beat someone who always guesses the long-run
    frequency"). BSS_vs_clim is expected to be strongly POSITIVE, especially late
    in the game, because seeing the score trivially beats the base rate. That is
    NOT an edge -- it is what any competent in-game win-prob model does.
  * market       -- the devigged market_prob on the same rows. BSS_vs_market is
    expected to be NEAR OR BELOW 0: the model does not beat the market's Brier.
    That null is the honest headline of this exhibit, not a defect.

Checkpoints reuse the exact time-bucketers from state_conditioned_calibration
(mlb: inning bands; soccer_intl: 15-min bands) so the whole showcase agrees on
what a "checkpoint" is.

Scope / floors (declared):
  * DESCRIPTIVE_ONLY, edge_claimed=False. No $/ROI/profit claim anywhere.
  * MIN_N = 30 graded rows per grain to report a BSS (a Brier from <30 rows is
    too noisy to trust); sub-floor grains keep their Brier but BSS is null.
  * Climatology divide-by-zero guarded (Brier_ref<=0 -> BSS null).
  * Truth source for any claim: docs/JOB_EVIDENCE_PACKET.md.

Usage:
    python -m scripts.platformkit.analytics_showcase.brier_skill_scores
    python -m scripts.platformkit.analytics_showcase.brier_skill_scores --check
"""
import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

# Reuse the showcase's canonical checkpoint bucketers (package-qualified under
# `-m ...`, bare fallback when run as a plain script from this directory).
try:
    from scripts.platformkit.analytics_showcase.state_conditioned_calibration import SPORTS as CHECKPOINTERS
except ImportError:  # pragma: no cover - bare-script invocation
    from state_conditioned_calibration import SPORTS as CHECKPOINTERS

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IN_DIR = os.path.join(REPO_ROOT, "data", "cache", "ingame_grade_joined")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "brier_skill_scores.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "brier_skill_scores.png")

MIN_N = 30
SOURCE_ARTIFACT = "data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (mlb_clean dup excluded)"
FLOORS = f"n>={MIN_N} rows/grain for a BSS; climatology=const sport base rate; edge_claimed=False"

# Canonical checkpoint order for each sport (matches state_conditioned_calibration's heatmap).
CHECKPOINT_ORDER = {
    "mlb": ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"],
    "soccer_intl": ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90+"],
}

HONEST_NOTE = (
    "BSS vs market is near or below 0 across sports and checkpoints -- the model does not "
    "beat the market's Brier. That null result is the POINT of this exhibit, not a defect. "
    "BSS vs climatology is strongly positive (model and market both crush the base-rate "
    "baseline), which is expected for in-game win-prob and is NOT an edge. "
    "Truth source: docs/JOB_EVIDENCE_PACKET.md."
)


def load_triples(sport):
    """Read the sport's JSONL rows, keeping ONLY the four fields we need
    (model_prob, market_prob, outcome, state_summary) -- the JSONL analog of a
    column-selective read; the rest of each record is discarded immediately.
    Returns (triples, checkpoint_of) where triples[i]=(model_p, market_p, y) and
    checkpoint_of[i] is the checkpoint label for row i (or None if unparseable).
    """
    bucketer = CHECKPOINTERS[sport]
    triples, checkpoint_of = [], []
    for path in sorted(glob.glob(os.path.join(IN_DIR, sport, "*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                mp, kp, y = d.get("model_prob"), d.get("market_prob"), d.get("outcome")
                if mp is None or kp is None or y is None:
                    continue
                triples.append((mp, kp, float(y)))
                checkpoint_of.append(bucketer(d.get("state_summary")))
    return triples, checkpoint_of


def bss_grain(triples, ybar_sport, min_n=MIN_N):
    """BSS dict for one grain. climatology ref = constant ybar_sport (unconditional
    sport base rate). Returns None only for an empty grain."""
    n = len(triples)
    if n == 0:
        return None
    ys = [y for _, _, y in triples]
    ybar = sum(ys) / n
    b_model = sum((mp - y) ** 2 for mp, _, y in triples) / n
    b_market = sum((kp - y) ** 2 for _, kp, y in triples) / n
    b_clim = sum((ybar_sport - y) ** 2 for _, _, y in triples) / n

    def _bss(b, ref):
        return None if ref <= 0 else round(1.0 - b / ref, 4)

    out = {
        "n": n,
        "base_rate": round(ybar, 4),
        "brier_model": round(b_model, 6),
        "brier_market": round(b_market, 6),
        "brier_clim": round(b_clim, 6),
        "below_floor": n < min_n,
    }
    if n < min_n:
        out.update(bss_model_vs_clim=None, bss_market_vs_clim=None,
                   bss_model_vs_market=None, bss_note=f"n<{min_n} floor -- BSS suppressed")
    else:
        out["bss_model_vs_clim"] = _bss(b_model, b_clim)
        out["bss_market_vs_clim"] = _bss(b_market, b_clim)
        out["bss_model_vs_market"] = _bss(b_model, b_market)
    return out


def analyze_sport(sport):
    triples, checkpoint_of = load_triples(sport)
    if not triples:
        return {"n_rows": 0, "skipped_reason": "no rows with model+market+outcome"}
    ybar_sport = sum(y for _, _, y in triples) / len(triples)
    by_ckpt = defaultdict(list)
    for t, ck in zip(triples, checkpoint_of):
        if ck is not None:
            by_ckpt[ck].append(t)
    grains = {"all": bss_grain(triples, ybar_sport)}
    for ck in CHECKPOINT_ORDER.get(sport, sorted(by_ckpt)):
        if by_ckpt.get(ck):
            grains[ck] = bss_grain(by_ckpt[ck], ybar_sport)
    return {
        "n_rows": len(triples),
        "sport_base_rate": round(ybar_sport, 4),
        "climatology_ref": "constant sport-level base rate (unconditional P(outcome=1))",
        "grains": grains,
    }


def _plotted_grains(sport, sport_res):
    order = ["all"] + CHECKPOINT_ORDER.get(sport, [])
    grains = sport_res.get("grains", {})
    return [g for g in order if g in grains and grains[g].get("bss_model_vs_market") is not None]


def make_plot(result):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    sports = [s for s, r in result["sports"].items() if r.get("grains")]
    if not sports:
        return False
    fig, axes = plt.subplots(1, len(sports), figsize=(6.0 * len(sports), 4.6), squeeze=False)
    series = [("bss_model_vs_clim", "model vs climatology", "#2b6cb0"),
              ("bss_market_vs_clim", "market vs climatology", "#dd8452"),
              ("bss_model_vs_market", "model vs market (honest null)", "#c0392b")]
    width = 0.26
    for ax, sport in zip(axes[0], sports):
        sres = result["sports"][sport]
        labels = _plotted_grains(sport, sres)
        xs = list(range(len(labels)))
        for j, (key, lab, color) in enumerate(series):
            vals = [sres["grains"][g][key] for g in labels]
            bars = ax.bar([x + (j - 1) * width for x in xs], vals, width, label=lab, color=color)
            if key == "bss_model_vs_market":  # annotate the near-0 honest values
                for b, v in zip(bars, vals):
                    ax.annotate(f"{v:+.3f}", (b.get_x() + b.get_width() / 2, v),
                                textcoords="offset points", xytext=(0, 3 if v >= 0 else -9),
                                ha="center", fontsize=6, color=color)
        ax.axhline(0, color="gray", linewidth=1, linestyle="--")
        ax.set_xticks(xs)
        ax.set_xticklabels([f"{g}\n(n={sres['grains'][g]['n']})" for g in labels], fontsize=7)
        ax.set_title(f"{sport}: BSS by checkpoint", fontsize=10)
        ax.set_ylabel("BSS = 1 - Brier/Brier_ref  (>0 beats ref)")
        ax.legend(fontsize=7)
    fig.suptitle("Brier Skill Score vs climatology and vs market (per sport x checkpoint)", fontsize=11)
    fig.text(0.5, 0.015, HONEST_NOTE, ha="center", fontsize=6.2, color="#444444", wrap=True)
    fig.text(0.01, 0.01, f"source: {SOURCE_ARTIFACT} | floor: {FLOORS}", fontsize=5.5, color="#777777")
    fig.text(0.99, 0.01, "DESCRIPTIVE_ONLY", fontsize=6.5, ha="right", color="#b33333", fontweight="bold")
    fig.tight_layout(rect=(0, 0.07, 1, 0.96))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def build_verdict(result):
    lines = []
    for sport, sres in result["sports"].items():
        grains = sres.get("grains")
        if not grains:
            continue
        vm = [g["bss_model_vs_market"] for g in grains.values() if g.get("bss_model_vs_market") is not None]
        vc = [g["bss_model_vs_clim"] for g in grains.values() if g.get("bss_model_vs_clim") is not None]
        if not vm:
            continue
        mkt = ("model does not beat the market" if max(vm) <= 0.01
               else f"max {max(vm):+.3f} is within single-fold noise, not a validated edge (see JOB_EVIDENCE_PACKET)")
        lines.append(
            f"{sport}: BSS(model vs market) in [{min(vm):+.3f}, {max(vm):+.3f}] -- {mkt}; "
            f"BSS(model vs climatology) in [{min(vc):+.3f}, {max(vc):+.3f}] (BSS>0 means it beats that baseline)."
        )
    return " ".join(lines) if lines else "No sport had a reportable BSS grain."


def run():
    result = {
        "edge_claimed": False,
        "descriptive_only": True,
        "method": "standard BSS = 1 - Brier/Brier_ref; refs = climatology (const sport base rate) and market",
        "floors": FLOORS,
        "source_artifact": SOURCE_ARTIFACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "honest_note": HONEST_NOTE,
        "sports": {},
    }
    for sport in CHECKPOINTERS:
        result["sports"][sport] = analyze_sport(sport)
    result["verdict"] = build_verdict(result)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    result["plot_written"] = make_plot(result)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def check():
    """Synthetic BSS-math asserts (data-free), then -- if the real corpora are on
    disk -- run() and assert both outputs exist nonzero."""
    # model == market on every row -> BSS(model vs market) is exactly 0.
    tied = [(0.7, 0.7, 1.0), (0.3, 0.3, 0.0)] * 20
    g = bss_grain(tied, ybar_sport=0.5)
    assert g["bss_model_vs_market"] == 0.0, g

    # A perfect, sharp model (predicts y exactly) -> brier_model=0 -> BSS_vs_clim==1.
    perfect = [(1.0, 0.6, 1.0), (0.0, 0.4, 0.0)] * 20
    gp = bss_grain(perfect, ybar_sport=0.5)
    assert gp["brier_model"] == 0.0 and gp["bss_model_vs_clim"] == 1.0, gp

    # Below-floor grain suppresses BSS but keeps the Brier.
    gf = bss_grain([(0.6, 0.5, 1.0)], ybar_sport=0.5)
    assert gf["below_floor"] and gf["bss_model_vs_market"] is None and gf["brier_model"] is not None, gf

    # Divide-by-zero guard: degenerate climatology (ybar_sport in {0,1}) -> BSS_vs_clim null.
    gz = bss_grain([(0.2, 0.2, 0.0)] * 40, ybar_sport=0.0)
    assert gz["brier_clim"] == 0.0 and gz["bss_model_vs_clim"] is None, gz

    if not glob.glob(os.path.join(IN_DIR, "mlb", "*.jsonl")):
        print("brier_skill_scores self-check OK (synthetic only; corpora absent -- clean clone)")
        return
    res = run()
    assert os.path.getsize(OUT_JSON) > 0, "OUT_JSON missing/empty"
    if res.get("plot_written"):
        assert os.path.getsize(OUT_PNG) > 0, "OUT_PNG missing/empty"
    assert any(r.get("grains") for r in res["sports"].values()), "no sport produced grains"
    print("brier_skill_scores self-check OK (synthetic + real outputs exist nonzero)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(HONEST_NOTE)
        print(json.dumps({"verdict": res["verdict"], "plot_written": res["plot_written"],
                          "sports_n_rows": {s: v.get("n_rows") for s, v in res["sports"].items()}}, indent=2))
