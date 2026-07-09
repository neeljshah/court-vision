"""NBA in-game GRU win-probability sequence model (GOAL 5) -- PREREGISTRATION.

Goal: a CALIBRATED per-step P(home win) predictor over pbp event sequences, judged
LEAK-FREE vs (a) the margin+time logistic ladder rung and (b) the live Kalshi market
on the 53 playoff checkpoint games. Beat both under a game-clustered Diebold-Mariano
test AND calibration (ECE), or be catalogued as an honest NULL. Both are successes.
THIS IS NOT A $/EDGE PRODUCT. Declared BEFORE training (K=1, no hyperparam search):
  Split (STRICT by game date; see nba_gru_dataset.py): train = 2024-25 + 2025-26 pre
    2026-03-01; val = 2025-26 on/after (early-stop only); test = 53 checkpoint games.
    All 53 checkpoint ids removed from train/val (44 overlap the 25-26 states corpus).
  Features (as-of, leak-free, SAME info set as the ladder): margin, frac_elapsed,
    period, margin_run_180. No pregame identity/strength.
  Model: 1-layer GRU(hidden=48) + sigmoid head, per-step masked BCE, Adam lr=1e-3,
    <=20 epochs, early-stop val log-loss (patience 3), seed=0. Small (RTX 4060 8GB).
  Baselines on SAME train rows: (1) logistic ladder [margin, margin*sqrt(time_frac),
    frac_elapsed]; (2) Kalshi market_prob on the test rows.
  Metrics: per-step Brier/log-loss pooled + phase (P1-2/P3/P4+); game-clustered DM vs
    (1); ECE(10-bin); GRU-vs-market Brier. Verdict SEQ_BEATS_LADDER / NULL / BLOCKED.
  torch absent -> BLOCKED honestly (no pip install while the fleet runs).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")  # do not starve the fleet
import numpy as np

import nba_gru_dataset as ds  # noqa: E402  (same dir; run via -m or with sys.path)

WEIGHTS = "data/cache/seqmodel/nba_gru_v1.pt"
REPORT = "data/frontend/ops/nba_seqmodel_v1.json"
SEED = 0
HIDDEN = 48
LR = 1e-3
MAX_EPOCHS = 20
PATIENCE = 3
BATCH = 64

def _try_torch():
    try:
        import torch  # noqa: F401
        return __import__("torch")
    except Exception:  # pragma: no cover
        return None

# ---------- metrics (numpy; shared by GRU / logistic / market) ----------
def brier(p, y):
    return float(np.mean((p - y) ** 2))

def logloss(p, y, eps=1e-7):
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

def ece(p, y, bins=10):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            tot += (m.mean()) * abs(y[m].mean() - p[m].mean())
    return float(tot)

def phase_bucket(period):
    period = np.asarray(period)
    return np.where(period <= 2, "P1-2", np.where(period == 3, "P3", "P4+"))

def by_phase(p, y, period):
    ph = phase_bucket(period)
    res = {}
    for b in ["P1-2", "P3", "P4+"]:
        m = ph == b
        if m.any():
            res[b] = {"n": int(m.sum()), "brier": brier(p[m], y[m]), "logloss": logloss(p[m], y[m])}
    return res

def dm_gameclustered(loss_a, loss_b, game_ids):
    """Diebold-Mariano, game-clustered. d = loss_a - loss_b; cluster mean per game,
    t = mean(d_g)/(std(d_g)/sqrt(G)). Negative t => model A lower loss (better)."""
    d = loss_a - loss_b
    gids = np.asarray(game_ids)
    dg = np.array([d[gids == g].mean() for g in np.unique(gids)])
    G = len(dg)
    sd = dg.std(ddof=1)
    if sd == 0:
        return 0.0, 1.0, G
    t = dg.mean() / (sd / np.sqrt(G))
    # two-sided p via normal approx (G ~ 53 is adequate)
    from math import erf, sqrt
    p = 2 * (1 - 0.5 * (1 + erf(abs(t) / sqrt(2))))
    return float(t), float(p), G

# ---------- logistic ladder baseline ----------
def ladder_features(df):
    fe = df["frac_elapsed"].to_numpy(dtype=float)
    trem = np.clip(1.0 - fe, 0.0, 1.0)
    margin = df["margin"].to_numpy(dtype=float)
    return np.column_stack([margin, margin * np.sqrt(trem), fe])

def fit_ladder(train_df):
    from sklearn.linear_model import LogisticRegression
    X = ladder_features(train_df)
    y = train_df["home_win"].to_numpy(dtype=int)
    clf = LogisticRegression(max_iter=1000)
    clf.fit(X, y)
    return clf

# ---------- GRU ----------
def build_model(torch):
    import torch.nn as nn

    class GRUWinProb(nn.Module):
        def __init__(self, in_dim=len(ds.FEATURES), hidden=HIDDEN):
            super().__init__()
            self.gru = nn.GRU(in_dim, hidden, num_layers=1, batch_first=True)
            self.head = nn.Linear(hidden, 1)

        def forward(self, x):  # x: [B, T, F] -> [B, T]
            h, _ = self.gru(x)
            return self.head(h).squeeze(-1)  # logits per step

    return GRUWinProb()

def pad_batch(seqs, torch):
    """seqs: list of (feat[T,F], label). -> padded x[B,Tmax,F], y[B,Tmax], mask[B,Tmax]."""
    B = len(seqs)
    Tmax = max(f.shape[0] for f, _ in seqs)
    F = seqs[0][0].shape[1]
    x = np.zeros((B, Tmax, F), dtype=np.float32)
    y = np.zeros((B, Tmax), dtype=np.float32)
    mask = np.zeros((B, Tmax), dtype=np.float32)
    for i, (f, lab) in enumerate(seqs):
        T = f.shape[0]
        x[i, :T] = f
        y[i, :T] = lab
        mask[i, :T] = 1.0
    return (torch.from_numpy(x), torch.from_numpy(y), torch.from_numpy(mask))

def train_gru(torch, train_seqs, val_seqs, device):
    import torch.nn as nn
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    model = build_model(torch).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    bce = nn.BCEWithLogitsLoss(reduction="none")
    train_pairs = [(f, lab) for _, f, lab, _ in train_seqs]
    val_pairs = [(f, lab) for _, f, lab, _ in val_seqs]

    def masked_loss(pairs):
        model.eval()
        tot, n = 0.0, 0.0
        with torch.no_grad():
            for i in range(0, len(pairs), BATCH):
                x, y, m = pad_batch(pairs[i:i + BATCH], torch)
                x, y, m = x.to(device), y.to(device), m.to(device)
                logits = model(x)
                p = torch.clamp(torch.sigmoid(logits), 1e-7, 1 - 1e-7)
                ll = -(y * torch.log(p) + (1 - y) * torch.log(1 - p)) * m
                tot += ll.sum().item()
                n += m.sum().item()
        return tot / max(n, 1)

    best, best_state, bad = float("inf"), None, 0
    rng = np.random.default_rng(SEED)
    for ep in range(MAX_EPOCHS):
        model.train()
        order = rng.permutation(len(train_pairs))
        for i in range(0, len(order), BATCH):
            idx = order[i:i + BATCH]
            x, y, m = pad_batch([train_pairs[j] for j in idx], torch)
            x, y, m = x.to(device), y.to(device), m.to(device)
            opt.zero_grad()
            logits = model(x)
            loss = (bce(logits, y) * m).sum() / m.sum().clamp(min=1)
            loss.backward()
            opt.step()
        vl = masked_loss(val_pairs)
        print(f"epoch {ep:02d} val_logloss={vl:.4f}")
        if vl < best - 1e-4:
            best, best_state, bad = vl, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}, 0
        else:
            bad += 1
            if bad >= PATIENCE:
                print(f"early stop @ epoch {ep}")
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best

def gru_predict(torch, model, seqs, device):
    """Per-game forward -> flat per-row prob arrays aligned to concatenated meta."""
    model.eval()
    probs, ys, periods, gids = [], [], [], []
    with torch.no_grad():
        for gid, f, lab, meta in seqs:
            x = torch.from_numpy(f[None, :, :]).to(device)
            p = torch.sigmoid(model(x)).squeeze(0).cpu().numpy()
            probs.append(p)
            ys.append(meta["home_win"].to_numpy(dtype=float))
            periods.append(meta["period"].to_numpy())
            gids.append(np.full(len(p), gid))
    return (np.concatenate(probs), np.concatenate(ys),
            np.concatenate(periods), np.concatenate(gids))

def main():
    Path("data/cache/seqmodel").mkdir(parents=True, exist_ok=True)
    Path("data/frontend/ops").mkdir(parents=True, exist_ok=True)
    torch = _try_torch()
    if torch is None:
        rep = {"edge_claimed": False, "verdict": "BLOCKED",
               "reason": "torch not importable; pip install disallowed while fleet runs"}
        Path(REPORT).write_text(json.dumps(rep, indent=2))
        print("BLOCKED: torch missing"); return

    torch.manual_seed(SEED); np.random.seed(SEED)
    try:
        torch.use_deterministic_algorithms(True, warn_only=True)
    except Exception:
        pass
    device = "cuda" if torch.cuda.is_available() else "cpu"

    ck_ids = ds.checkpoint_ids()
    states = ds.load_states()
    train_df, val_df = ds.split_states(states, ck_ids)
    test_df = ds.load_checkpoints()

    train_seqs = ds.to_sequences(train_df)
    val_seqs = ds.to_sequences(val_df)
    test_seqs = ds.to_sequences(test_df)

    model, best_val = train_gru(torch, train_seqs, val_seqs, device)
    torch.save({"state_dict": model.state_dict(), "features": ds.FEATURES,
                "norm": ds.NORM.tolist(), "hidden": HIDDEN, "seed": SEED}, WEIGHTS)

    # ---- predictions on test (checkpoints) ----
    gp, gy, gper, ggid = gru_predict(torch, model, test_seqs, device)
    ladder = fit_ladder(train_df)
    lp = ladder.predict_proba(ladder_features(test_df))[:, 1]
    # align ladder/market to the same row order as gru (test_df groupby order == to_sequences order)
    mkt = test_df["market_prob"].to_numpy(dtype=float)
    ly = test_df["home_win"].to_numpy(dtype=float)
    assert np.allclose(gy, ly), "row alignment mismatch GRU vs test_df"

    m = {
        "gru": {"brier": brier(gp, gy), "logloss": logloss(gp, gy), "ece": ece(gp, gy),
                "by_phase": by_phase(gp, gy, gper)},
        "ladder_logistic": {"brier": brier(lp, ly), "logloss": logloss(lp, ly), "ece": ece(lp, ly),
                            "by_phase": by_phase(lp, ly, gper)},
        "market_kalshi": {"brier": brier(mkt, ly), "logloss": logloss(mkt, ly), "ece": ece(mkt, ly),
                          "by_phase": by_phase(mkt, ly, gper)},
    }
    # DM game-clustered: GRU vs ladder, and GRU vs market (Brier per-row loss)
    t_gl, p_gl, G = dm_gameclustered((gp - gy) ** 2, (lp - ly) ** 2, ggid)
    t_gm, p_gm, _ = dm_gameclustered((gp - gy) ** 2, (mkt - ly) ** 2, ggid)

    beats_ladder = (m["gru"]["brier"] < m["ladder_logistic"]["brier"]) and (t_gl < 0) and (p_gl < 0.05)
    verdict = "SEQ_BEATS_LADDER" if beats_ladder else "NULL"

    rep = {
        "edge_claimed": False,
        "product": "calibrated in-game win-prob sequence model (NOT a $/edge product)",
        "verdict": verdict,
        "split": {
            "train_games": int(train_df.game_id.nunique()),
            "val_games": int(val_df.game_id.nunique()),
            "test_games": int(test_df.game_id.nunique()),
            "cutoff": ds.CUTOFF,
            "train_dates": [str(train_df.date.min().date()), str(train_df.date.max().date())],
            "val_dates": [str(val_df.date.min().date()), str(val_df.date.max().date())],
            "test_dates": [str(test_df.date.min().date()), str(test_df.date.max().date())],
            "checkpoint_ids_dropped_from_train_val": len(ck_ids),
        },
        "config": {"hidden": HIDDEN, "lr": LR, "max_epochs": MAX_EPOCHS, "patience": PATIENCE,
                   "seed": SEED, "features": ds.FEATURES, "best_val_logloss": best_val},
        "test_n_rows": int(len(gy)),
        "metrics": m,
        "dm_gru_vs_ladder": {"t_stat": t_gl, "p_value": p_gl, "n_games": G,
                             "interpretation": "t<0 => GRU lower Brier (better)"},
        "dm_gru_vs_market": {"t_stat": t_gm, "p_value": p_gm, "n_games": G},
        "honesty_notes": [
            "Leak guard: all 53 checkpoint game_ids removed from train/val (44 physically",
            "overlapped the 25-26 states corpus). STRICT date split, no game shuffled.",
            "Same information set (score+time) given to GRU and the ladder logistic;",
            "GRU's only extra is sequence memory + the margin_run_180 feature.",
            "n_plays_seen and score-total-as-of/possession EXCLUDED: not computable in the",
            "checkpoint corpus (train/inference parity). No pregame identity/strength used.",
            "market_prob is the live Kalshi P(home win); freshness the model cannot see is a",
            "structural disadvantage, not evidence of a betting edge. No $ claim is made.",
        ],
    }
    Path(REPORT).write_text(json.dumps(rep, indent=2))
    print(json.dumps({k: rep[k] for k in ("verdict", "metrics", "dm_gru_vs_ladder", "dm_gru_vs_market")}, indent=2))
    print(f"weights -> {WEIGHTS}\nreport  -> {REPORT}")

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
