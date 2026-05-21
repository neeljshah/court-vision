"""Today's Bets — shows prop bet table for current date."""
import os
from datetime import date
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Today's Bets", layout="wide")
st.title("Today's Bets")

LEDGER = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "output", "bet_ledger.csv")


def load_bets_for_date(ledger_path: str, today: str) -> pd.DataFrame:
    """Load bets for a specific date from the ledger CSV.

    Args:
        ledger_path: Absolute path to bet_ledger.csv.
        today: Date string in YYYY-MM-DD format to filter on.

    Returns:
        DataFrame of bets for the given date, or empty DataFrame on any error.
    """
    if not os.path.exists(ledger_path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(ledger_path)
        if "date" in df.columns:
            df = df[df["date"] == today]
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def _load_bets(today: str) -> pd.DataFrame:
    return load_bets_for_date(LEDGER, today)


today = str(date.today())
df = _load_bets(today)

if df.empty:
    st.info(f"No bets found for {today}. Run `run_daily_slate.py` to generate today's slate.")
else:
    # Display key columns if present, otherwise show all
    preferred_cols = ["player", "stat", "direction", "predicted", "line", "edge_pct", "status", "pnl"]
    cols = [c for c in preferred_cols if c in df.columns] or list(df.columns)
    st.dataframe(df[cols], use_container_width=True)

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Bets", len(df))
    if "pnl" in df.columns:
        settled = df[df["pnl"].notna()]
        with col2:
            st.metric("Settled", len(settled))
        with col3:
            st.metric("P&L", f"${settled['pnl'].sum():.2f}" if len(settled) > 0 else "$0.00")
