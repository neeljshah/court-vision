"""Half-life of pregame information in NBA games -- SSAC27 paper, all numbers + figure 1.

One entry point reproduces every number in jobsearch/ssac/ABSTRACT_V2.md.

  python -m scripts.platformkit.ssac.halflife            # numbers
  python -m scripts.platformkit.ssac.halflife --figure   # + docs/img/ssac_halflife.png

V(t) = Brier(STATE) - Brier(STATE+PRIOR) is the value of pregame information at game
minute t. STATE sees only margin and time remaining. PRIOR is run from two independent
sources -- the market's opening price, and a walk-forward Elo built only from strictly
earlier games -- so the decay cannot be an artifact of either.

Calibration only. No edge, ROI, or dollar figure is produced anywhere. See
docs/JOB_EVIDENCE_PACKET.md for claim discipline.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from sklearn.linear_model import LogisticRegression

REPO = Path(__file__).resolve().parents[3]
PARQUET = REPO / "data" / "cache" / "inplay_odds" / "nba_checkpoints_full.parquet"
REG_SEC = 2880.0
SPLIT_DATE = "2025-08-01"
STATE_COLS = ["f_margin", "f_margin_raw", "f_trem"]
K_ELO, HFA = 20.0, 65.0
TEAM_ALIAS = {"pho": "phx", "wsh": "was"}  # feed emits both spellings


def load_clean() -> pd.DataFrame:
    """Live in-play ticks, one observation per (game, game-minute).

    Half the raw file is post-final settled price pinned at 0.0005/0.9995; scoring on it
    inflates every arm. See memory gotcha-inplay-parquet-half-settled-ticks.
    """
    df = pd.read_parquet(PARQUET)
    df = df[(df.period <= 4) & (df.game_clock_s > 0)]
    df = df[df.market_prob.between(0.002, 0.998)].sort_values("ts").copy()
    df["elapsed"] = (df.period - 1) * 720.0 + (720.0 - df.game_clock_s)
    df["t_rem"] = np.maximum(REG_SEC - df.elapsed, 0.0)
    srt = np.sqrt(df.t_rem + 1.0)
    df["f_margin"] = df.margin / srt
    df["f_margin_raw"] = df.margin / 10.0
    df["f_trem"] = srt / np.sqrt(REG_SEC)
    df["minute"] = (df.elapsed // 60).astype(int).clip(0, 47)
    df["season"] = np.where(df.game_date < SPLIT_DATE, "A", "B")
    return _add_priors(df).drop_duplicates(subset=["game_id", "minute"], keep="last")


def _logit(p, lo=0.02, hi=0.98):
    p = np.clip(p, lo, hi)
    return np.log(p / (1 - p))


def _add_priors(df: pd.DataFrame) -> pd.DataFrame:
    """Market-opening-price prior and a walk-forward Elo prior."""
    df["f_prior"] = _logit(df.game_id.map(df.groupby("game_id").market_prob.first()))
    df["f_prior_t"] = df.f_prior * df.f_trem

    tk = df.market_ticker.str.split("-", expand=True)
    # The ticker feed uses two alternate codes (one game each). Without this the Elo
    # treats them as expansion teams and hands them a fresh 1500 rating.
    df["away"], df["home"] = tk[1].replace(TEAM_ALIAS), tk[2].replace(TEAM_ALIAS)
    games = df.groupby("game_id").agg(
        game_date=("game_date", "first"), home=("home", "first"),
        away=("away", "first"), y=("outcome_home_win", "first")).reset_index()

    ratings: dict[str, float] = {}
    rows = []
    for g in games.sort_values("game_date").itertuples():
        rh, ra = ratings.get(g.home, 1500.0), ratings.get(g.away, 1500.0)
        exp_h = 1.0 / (1.0 + 10 ** (-(rh + HFA - ra) / 400.0))
        rows.append((g.game_id, exp_h))
        ratings[g.home] = rh + K_ELO * (g.y - exp_h)
        ratings[g.away] = ra + K_ELO * ((1 - g.y) - (1 - exp_h))
    elo = pd.DataFrame(rows, columns=["game_id", "elo_prob"])

    df = df.merge(elo, on="game_id", how="left")
    df["f_eprior"] = _logit(df.elo_prob)
    df["f_eprior_t"] = df.f_eprior * df.f_trem
    return df


def _expo(t, a, lam):
    return a * np.exp(-lam * t)


def curve(te: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Per-4-minute-bin V(t) and the bin midpoints."""
    te = te.assign(bin=te.minute // 4)
    y = te.outcome_home_win
    agg = te.assign(se_s=(te.ps - y) ** 2, se_p=(te.pp - y) ** 2) \
            .groupby("bin").agg(s=("se_s", "mean"), p=("se_p", "mean"))
    return agg.index.values * 4 + 2.0, (agg.s - agg.p).values


def fit(x, v) -> tuple[float, float, float]:
    """Returns (V0, half-life minutes, R-squared)."""
    (a, lam), _ = curve_fit(_expo, x, v, p0=[0.04, 0.05], maxfev=20000)
    r2 = 1 - np.sum((v - _expo(x, a, lam)) ** 2) / np.sum((v - v.mean()) ** 2)
    return a, float(np.log(2) / lam), r2


def score(tr: pd.DataFrame, te: pd.DataFrame, prior_cols: list[str]) -> pd.DataFrame:
    """Fit STATE and STATE+PRIOR on tr, predict on te."""
    cp = STATE_COLS + prior_cols
    te = te.copy()
    te["ps"] = LogisticRegression(max_iter=2000).fit(
        tr[STATE_COLS], tr.outcome_home_win).predict_proba(te[STATE_COLS])[:, 1]
    te["pp"] = LogisticRegression(max_iter=2000).fit(
        tr[cp], tr.outcome_home_win).predict_proba(te[cp])[:, 1]
    return te


def bootstrap_half_life(te: pd.DataFrame, n_boot=500, seed=7) -> tuple[float, float]:
    """Game-clustered bootstrap CI on the half-life."""
    rng = np.random.default_rng(seed)
    by_game = dict(list(te.groupby("game_id", sort=False)))
    ids = np.array(list(by_game))
    out = []
    for _ in range(n_boot):
        s = pd.concat([by_game[g] for g in rng.choice(ids, len(ids), replace=True)])
        x, v = curve(s)
        if len(v) < 12:
            continue
        try:
            _, hl, _ = fit(x, v)
            if 0 < hl < 200:
                out.append(hl)
        except (RuntimeError, ValueError):
            continue
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


PRIORS = {"market opening price": ["f_prior", "f_prior_t"],
          "walk-forward Elo": ["f_eprior", "f_eprior_t"]}


def run(make_figure: bool = False) -> dict:
    df = load_clean()
    a_df, b_df = df[df.season == "A"], df[df.season == "B"]
    print("observations %d  games %d  (one per game-minute, settled ticks removed)"
          % (len(df), df.game_id.nunique()))

    results = {}
    print("\nHALF-LIFE OF PREGAME INFORMATION")
    print("  prior source          split            V0       half-life   R2")
    for label, cols in PRIORS.items():
        for tag, tr, te in (("2024-25 -> 2025-26", a_df, b_df),
                            ("2025-26 -> 2024-25", b_df, a_df)):
            scored = score(tr, te, cols)
            x, v = curve(scored)
            v0, hl, r2 = fit(x, v)
            print("  %-20s  %-18s %.4f   %5.1f min   %.3f" % (label, tag, v0, hl, r2))
            results[(label, tag)] = (x, v, v0, hl, r2)

    key = ("market opening price", "2024-25 -> 2025-26")
    lo, hi = bootstrap_half_life(score(a_df, b_df, PRIORS["market opening price"]))
    print("\n  headline half-life %.1f min, game-clustered bootstrap 95%% CI [%.1f, %.1f]"
          % (results[key][3], lo, hi))

    if make_figure:
        _figure(results)
    return results


def _figure(results: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    colors = {"market opening price": "#1f4e79", "walk-forward Elo": "#c1622a"}
    for label in PRIORS:
        x, v, v0, hl, r2 = results[(label, "2024-25 -> 2025-26")]
        ax.plot(x, v, "o", color=colors[label], ms=5)
        tt = np.linspace(0, 48, 200)
        ax.plot(tt, _expo(tt, v0, np.log(2) / hl), "-", color=colors[label],
                label="%s (half-life %.1f min)" % (label, hl))
    ax.axhline(0, color="#999", lw=0.8)
    for q in (12, 24, 36):
        ax.axvline(q, color="#ddd", lw=0.8, zorder=0)
    ax.set_xlabel("game minute")
    ax.set_ylabel("value of pregame information\nBrier(STATE) - Brier(STATE+PRIOR)")
    ax.set_title("Pregame information decays at the same rate from either source")
    ax.set_xlim(0, 48)
    ax.legend(frameon=False)
    fig.tight_layout()
    out = REPO / "docs" / "img" / "ssac_halflife.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=170)
    print("\nfigure written: %s" % out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--figure", action="store_true")
    run(ap.parse_args().figure)
