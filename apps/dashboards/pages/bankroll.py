"""Bankroll — cumulative P&L, HWM, and drawdown chart."""
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Bankroll", layout="wide")
st.title("Bankroll Chart")

LEDGER = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "output", "bet_ledger.csv")
STARTING_BANKROLL = 1000.0  # default starting bankroll


def compute_bankroll_series(ledger_path: str, starting_bankroll: float = STARTING_BANKROLL) -> pd.DataFrame:
    """Load settled bets and compute cumulative bankroll, HWM, and drawdown.

    Args:
        ledger_path: Absolute path to bet_ledger.csv.
        starting_bankroll: Initial bankroll value in dollars.

    Returns:
        DataFrame with columns: cumulative_pnl, bankroll, hwm, drawdown.
        Empty DataFrame if no data or pnl column missing.
    """
    if not os.path.exists(ledger_path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(ledger_path)
        if "pnl" not in df.columns:
            return pd.DataFrame()
        df = df[df["pnl"].notna()].copy()
        if df.empty:
            return pd.DataFrame()
        # Sort by date if available
        if "date" in df.columns:
            df = df.sort_values("date")
        df["cumulative_pnl"] = df["pnl"].cumsum()
        df["bankroll"] = starting_bankroll + df["cumulative_pnl"]
        df["hwm"] = df["bankroll"].cummax()
        df["drawdown"] = (df["bankroll"] - df["hwm"]) / df["hwm"] * 100
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def _load_bankroll() -> pd.DataFrame:
    return compute_bankroll_series(LEDGER)


df = _load_bankroll()

if df.empty:
    st.info("No settled bets found in the ledger. P&L will appear here after bets are recorded.")
else:
    import plotly.graph_objects as go

    x = list(range(len(df))) if "date" not in df.columns else df["date"].tolist()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=df["bankroll"].tolist(), name="Bankroll",
        line=dict(color="#60a5fa", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=x, y=df["hwm"].tolist(), name="HWM",
        line=dict(color="#34d399", width=1, dash="dot"),
    ))
    fig.update_layout(
        template="plotly_dark",
        title="Bankroll vs High Water Mark",
        yaxis_title="Bankroll ($)",
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Drawdown chart
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=x, y=df["drawdown"].tolist(), name="Drawdown %",
        marker_color="#f87171",
    ))
    fig2.update_layout(
        template="plotly_dark",
        title="Drawdown (%)",
        yaxis_title="Drawdown (%)",
    )
    st.plotly_chart(fig2, use_container_width=True)

    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Bankroll", f"${df['bankroll'].iloc[-1]:.2f}")
    col2.metric("Total P&L", f"${df['cumulative_pnl'].iloc[-1]:.2f}")
    col3.metric("Max Drawdown", f"{df['drawdown'].min():.1f}%")
    col4.metric("Settled Bets", len(df))
