"""Model ROI — per-stat/model ROI from the bet ledger."""
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Model ROI", layout="wide")
st.title("Model ROI by Stat")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LEDGER = os.path.join(PROJECT_DIR, "data", "output", "bet_ledger.csv")
METRICS_DIR = os.path.join(PROJECT_DIR, "data", "models")


@st.cache_data(ttl=60)
def _load_ledger() -> pd.DataFrame:
    if not os.path.exists(LEDGER):
        return pd.DataFrame()
    try:
        return pd.read_csv(LEDGER)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def _load_model_metrics() -> dict:
    """Load per-stat R² from props_metrics.json."""
    import json
    for fname in ["props_metrics.json", "props_lgb_metrics.json"]:
        path = os.path.join(METRICS_DIR, fname)
        if os.path.exists(path):
            try:
                return json.load(open(path, encoding="utf-8"))
            except Exception:
                pass
    return {}


def _compute_roi(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-stat ROI from settled bets."""
    if "stat" not in df.columns or "pnl" not in df.columns:
        return pd.DataFrame()
    settled = df[df["pnl"].notna()].copy()
    if settled.empty:
        return pd.DataFrame()
    rows = []
    for stat, grp in settled.groupby("stat"):
        n = len(grp)
        total_pnl = grp["pnl"].sum()
        # ROI = P&L / (n * 100) assuming $100/bet
        roi = total_pnl / (n * 100) * 100 if n > 0 else 0.0
        win_rate = (grp["pnl"] > 0).mean()
        rows.append({"stat": stat, "n_bets": n, "total_pnl": total_pnl, "roi_pct": roi, "win_rate": win_rate})
    return pd.DataFrame(rows).sort_values("roi_pct", ascending=False)


df = _load_ledger()
metrics = _load_model_metrics()

if df.empty:
    st.info("No bet ledger found. P&L and ROI will appear here after bets are recorded.")
else:
    roi_df = _compute_roi(df)
    if roi_df.empty:
        st.info("No settled bets yet in the ledger.")
    else:
        st.dataframe(
            roi_df.style.format({"total_pnl": "${:.2f}", "roi_pct": "{:.1f}%", "win_rate": "{:.1%}"}),
            use_container_width=True
        )
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Bets", int(roi_df["n_bets"].sum()))
        col2.metric("Total P&L", f"${roi_df['total_pnl'].sum():.2f}")
        col3.metric("Overall ROI", f"{roi_df['total_pnl'].sum() / (roi_df['n_bets'].sum() * 100) * 100:.1f}%")

if metrics:
    st.subheader("Model R² by Stat")
    _m = metrics.get("stats", metrics)  # handle {stats: {stat: {r2: ...}}} or flat {stat: r2}
    r2_rows = [{"stat": s, "R²": float(v.get("r2", 0)) if isinstance(v, dict) else float(v or 0)}
               for s, v in _m.items() if isinstance(s, str) and s not in ("model", "trained_at")]
    st.dataframe(pd.DataFrame(r2_rows).sort_values("R²", ascending=False), use_container_width=True)
