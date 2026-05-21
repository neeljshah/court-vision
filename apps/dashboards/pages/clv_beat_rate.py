"""CLV Beat Rate — segmented by book and stat."""
import os
import json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="CLV Beat Rate", layout="wide")
st.title("CLV Beat Rate")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CLV_TRAIN = os.path.join(PROJECT_DIR, "data", "output", "clv_training_data.csv")
CLV_LOG   = os.path.join(PROJECT_DIR, "data", "models", "clv_log.json")

@st.cache_data(ttl=60)
def _load_data() -> pd.DataFrame:
    # Try clv_training_data.csv first, fall back to clv_log.json
    if os.path.exists(CLV_TRAIN):
        try:
            df = pd.read_csv(CLV_TRAIN)
            if not df.empty:
                return df
        except Exception:
            pass
    if os.path.exists(CLV_LOG):
        try:
            data = json.loads(open(CLV_LOG, encoding="utf-8").read())
            if data:
                return pd.DataFrame(data)
        except Exception:
            pass
    return pd.DataFrame()


def _compute_beat_rate(df: pd.DataFrame, group_col: str | None = None) -> pd.DataFrame:
    """Compute CLV beat rate (pct with clv > 0) optionally grouped."""
    clv_col = "clv_label" if "clv_label" in df.columns else "clv"
    if clv_col not in df.columns:
        return pd.DataFrame()
    if group_col and group_col in df.columns:
        groups = []
        for name, grp in df.groupby(group_col):
            total = len(grp)
            beat = (grp[clv_col] > 0).sum()
            mean_clv = grp[clv_col].mean()
            groups.append({group_col: name, "n": total, "beat_rate": beat / total if total else 0, "mean_clv": mean_clv})
        return pd.DataFrame(groups).sort_values("beat_rate", ascending=False)
    else:
        total = len(df)
        beat = (df[clv_col] > 0).sum()
        return pd.DataFrame([{"n": total, "beat_rate": beat / total if total else 0, "mean_clv": df[clv_col].mean()}])


df = _load_data()

if df.empty:
    st.info("No CLV data yet. Run `record_slate_results.py` after bets settle to populate CLV log.")
else:
    st.subheader("Overall CLV Beat Rate")
    overall = _compute_beat_rate(df)
    if not overall.empty:
        col1, col2 = st.columns(2)
        col1.metric("Total Bets", int(overall["n"].iloc[0]))
        col2.metric("Beat Rate", f"{overall['beat_rate'].iloc[0]:.1%}")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("By Stat")
        if "stat" in df.columns:
            by_stat = _compute_beat_rate(df, "stat")
            st.dataframe(by_stat.style.format({"beat_rate": "{:.1%}", "mean_clv": "{:+.4f}"}), use_container_width=True)
        else:
            st.info("No 'stat' column in data.")

    with col_b:
        st.subheader("By Book")
        if "book" in df.columns:
            by_book = _compute_beat_rate(df, "book")
            st.dataframe(by_book.style.format({"beat_rate": "{:.1%}", "mean_clv": "{:+.4f}"}), use_container_width=True)
        else:
            st.info("No 'book' column in data.")
