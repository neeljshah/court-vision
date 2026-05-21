"""Champion/Challenger — shadow model R² vs champion R²."""
import os
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Champion/Challenger", layout="wide")
st.title("Champion / Challenger Tracker")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@st.cache_data(ttl=60)
def _load_summary() -> dict:
    try:
        import sys
        sys.path.insert(0, PROJECT_DIR)
        from src.prediction.champion_challenger import get_summary
        return get_summary()
    except Exception:
        return {}


summary = _load_summary()

if not summary:
    st.info("No champion/challenger data yet. Bets must be evaluated first.")
else:
    rows = []
    for stat, s in summary.items():
        rows.append({
            "stat": stat,
            "champion_r2": s.get("champion_r2"),
            "challenger_r2": s.get("challenger_r2"),
            "bets_evaluated": s.get("bets_evaluated", 0),
            "last_promotion": s.get("last_promotion", "—"),
        })
    df = pd.DataFrame(rows)

    def _style_row(row):
        c_r2 = row.get("champion_r2")
        ch_r2 = row.get("challenger_r2")
        if ch_r2 is not None and c_r2 is not None and ch_r2 > c_r2:
            return ["background-color: #14532d"] * len(row)  # challenger winning
        return [""] * len(row)

    st.dataframe(
        df.style.apply(_style_row, axis=1).format({
            "champion_r2": "{:.4f}", "challenger_r2": lambda x: f"{x:.4f}" if x else "—",
        }),
        use_container_width=True,
    )

    # Promotion status
    promoting = [r["stat"] for r in rows
                 if r.get("challenger_r2") and r.get("champion_r2")
                 and r["challenger_r2"] > r["champion_r2"]
                 and r["bets_evaluated"] >= 100]
    if promoting:
        st.success(f"Eligible for promotion (challenger beating champion with 100+ bets): {', '.join(promoting)}")
    else:
        st.info("No challengers currently beating champions with sufficient evaluations.")

    if st.button("Run Promotion Check"):
        from src.prediction.champion_challenger import check_and_promote
        promoted = []
        for stat in summary:
            if check_and_promote(stat):
                promoted.append(stat)
        if promoted:
            st.success(f"Promoted: {', '.join(promoted)}")
        else:
            st.info("No promotions triggered.")
        st.cache_data.clear()
