"""Visual evidence pack: charts built ONLY from existing result-artifact JSONs.

No model runs, no data/ loads, no network. Reads 4 known artifacts and
renders 4 PNGs to docs/img/. ASCII-only stdout.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_DIR = os.path.join(ROOT, "docs", "img")
os.makedirs(OUT_DIR, exist_ok=True)

ACCENT = "#2563eb"
GRAY = "#9ca3af"

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#374151",
    "axes.grid": True,
    "grid.color": "#e5e7eb",
    "grid.linewidth": 0.8,
    "font.size": 12,
    "axes.titlesize": 13,
    "axes.labelsize": 12,
})


def load(rel_path):
    with open(os.path.join(ROOT, rel_path)) as f:
        return json.load(f)


def savefig(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    size = os.path.getsize(path)
    print(f"wrote {path} ({size} bytes)")


def chart_nba_ingame():
    src = "scripts/platformkit/benchmarks/crps_market/last_run_ingame_nba_winprob_ALLGAMES_v3.json"
    d = load(src)
    order = ["end_q1", "halftime", "end_q3", "q4_under5"]
    cps = d["checkpoints"]
    labels = [c for c in order if c in cps]
    model = [cps[c]["model_brier_mean"] for c in labels]
    market = [cps[c]["market_brier_mean"] for c in labels]
    ns = [cps[c]["n"] for c in labels]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = range(len(labels))
    w = 0.35
    ax.bar([i - w / 2 for i in x], model, width=w, color=ACCENT, label="model")
    ax.bar([i + w / 2 for i in x], market, width=w, color=GRAY, label="market")
    for i, (m, mk, n) in enumerate(zip(model, market, ns)):
        ax.annotate(f"n={n}", (i, max(m, mk) + 0.006), ha="center", fontsize=9, color="#374151")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Brier score (lower = sharper)")
    ax.set_title(f"NBA in-game win-prob Brier: model vs market (n=1593, market sharper at end_q1)")
    ax.legend(frameon=False)
    fig.text(0.01, 0.01, f"source: {src}", fontsize=8, color="#6b7280")
    savefig(fig, "nba_ingame_brier_vs_market.png")


def chart_mlb_ingame():
    src = "scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json"
    d = load(src)
    cps = d["checkpoints"]

    def inning_num(k):
        return int(k.rsplit("_", 1)[-1])

    markets = ["home_margin", "total_runs"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharey=True)
    for ax, market_name in zip(axes, markets):
        keys = sorted((k for k in cps if k.startswith(market_name + "|")), key=inning_num)
        innings = [inning_num(k) for k in keys]
        model = [cps[k]["model_crps_mean"] for k in keys]
        mkt = [cps[k]["market_crps_mean"] for k in keys]
        verdicts = [cps[k]["verdict"] for k in keys]
        xlabels = [f"inning {n}" for n in innings]

        ax.plot(xlabels, model, marker="o", color=ACCENT, label="model CRPS")
        ax.plot(xlabels, mkt, marker="o", color=GRAY, label="market CRPS")
        for i, v in enumerate(verdicts):
            ax.annotate(v, (i, max(model[i], mkt[i]) + 0.08), ha="center", fontsize=7.5,
                        color="#374151")
        ax.set_title(market_name)
        ax.set_ylabel("CRPS (lower = sharper)")
        ax.legend(frameon=False)

    fig.suptitle("MLB in-game CRPS by inning checkpoint: home_margin vs total_runs")
    fig.text(0.01, 0.01, f"source: {src}", fontsize=8, color="#6b7280")
    savefig(fig, "mlb_ingame_crps_by_inning.png")


def chart_winprob_walkforward():
    src = "results/winprob_walk_forward_results.json"
    d = load(src)
    folds = d["folds"]
    labels = [f"fold {f['fold']}" for f in folds]
    briers = [f["brier"] for f in folds]
    mean_brier = d["brier_mean"]

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(labels, briers, color=ACCENT, width=0.5)
    ax.axhline(mean_brier, color="#374151", linestyle="--", linewidth=1.2,
               label=f"mean = {mean_brier:.3f}")
    ax.set_ylabel("Brier score")
    ax.set_title(f"Pregame win-prob walk-forward Brier by fold (n_folds={d['n_folds']})")
    ax.legend(frameon=False)
    fig.text(0.01, 0.01, f"source: {src}", fontsize=8, color="#6b7280")
    savefig(fig, "winprob_walkforward_folds.png")


def chart_funnel():
    stages = ["DATA", "SIGNALS", "MODELS", "ENGINES", "PREDICTIONS", "INTELLIGENCE"]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.set_xlim(0, len(stages))
    ax.set_ylim(0, 2)
    ax.axis("off")

    box_w, box_h = 0.82, 0.9
    for i, name in enumerate(stages):
        cx = i + 0.5
        cy = 1.1
        rect = plt.Rectangle((cx - box_w / 2, cy - box_h / 2), box_w, box_h,
                              facecolor=ACCENT if i in (2, 4) else "white",
                              edgecolor="#374151", linewidth=1.4, zorder=2)
        ax.add_patch(rect)
        color = "white" if i in (2, 4) else "#111827"
        ax.text(cx, cy, name, ha="center", va="center", fontsize=11,
                fontweight="bold", color=color, zorder=3)
        if i < len(stages) - 1:
            ax.annotate("", xy=(cx + box_w / 2 + 0.16, cy), xytext=(cx + box_w / 2, cy),
                        arrowprops=dict(arrowstyle="-|>", color="#374151", linewidth=1.4))

    # re-validating loop arrow from INTELLIGENCE back to SIGNALS
    y_loop = 0.25
    x_start = len(stages) - 0.5
    x_end = 1.5
    ax.annotate("", xy=(x_end, y_loop), xytext=(x_start, y_loop),
                arrowprops=dict(arrowstyle="-|>", color=GRAY, linewidth=1.4,
                                 connectionstyle="arc3,rad=-0.25"))
    ax.text((x_start + x_end) / 2, y_loop - 0.35, "agentic loop re-validates every stage",
            ha="center", fontsize=9.5, color="#6b7280", style="italic")

    ax.set_title("CourtVision funnel: DATA -> SIGNALS -> MODELS -> ENGINES -> PREDICTIONS -> INTELLIGENCE")
    fig.text(0.01, 0.01, "source: docs/PLATFORM.md funnel narrative (static diagram, no artifact data)",
              fontsize=8, color="#6b7280")
    savefig(fig, "funnel_diagram.png")


if __name__ == "__main__":
    chart_nba_ingame()
    chart_mlb_ingame()
    chart_winprob_walkforward()
    chart_funnel()
    print("done")
