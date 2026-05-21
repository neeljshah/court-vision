"""Drift Monitor — rolling MAE per stat with auto-quarantine display."""
import os
import json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Drift Monitor", layout="wide")
st.title("Model Drift Monitor")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RESIDUALS_PATH = os.path.join(PROJECT_DIR, "data", "models", "prop_residuals.json")
QUARANTINE_PATH = os.path.join(PROJECT_DIR, "data", "models", "quarantine_state.json")
STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
WINDOW = 30
MAE_THRESHOLD_MULTIPLIER = 1.5


@st.cache_data(ttl=60)
def _load_residuals() -> list[dict]:
    if not os.path.exists(RESIDUALS_PATH):
        return []
    try:
        return json.loads(open(RESIDUALS_PATH, encoding="utf-8").read())
    except Exception:
        return []


def _load_quarantine() -> set:
    if not os.path.exists(QUARANTINE_PATH):
        return set()
    try:
        return set(json.loads(open(QUARANTINE_PATH, encoding="utf-8").read()).get("quarantined", []))
    except Exception:
        return set()


def compute_rolling_mae(residuals: list[dict], stat: str, window: int = 30) -> dict:
    """Compute baseline and rolling window MAE for a stat.

    Returns: {"baseline_mae": float, "window_mae": float, "n": int, "drift": bool}
    """
    rows = [r for r in residuals
            if r.get("stat") == stat
            and r.get("predicted") is not None
            and r.get("actual") is not None]
    if not rows:
        return {"baseline_mae": None, "window_mae": None, "n": 0, "drift": False}

    all_mae = sum(abs(r["predicted"] - r["actual"]) for r in rows) / len(rows)
    recent = rows[-window:] if len(rows) > window else rows
    window_mae = sum(abs(r["predicted"] - r["actual"]) for r in recent) / len(recent)
    drift = window_mae > all_mae * MAE_THRESHOLD_MULTIPLIER

    return {
        "baseline_mae": round(all_mae, 4),
        "window_mae": round(window_mae, 4),
        "n": len(rows),
        "drift": drift,
    }


residuals = _load_residuals()
quarantined = _load_quarantine()

if not residuals:
    st.info("No prediction residuals found. Run `record_slate_results.py` to populate.")
else:
    rows = []
    for stat in STATS:
        m = compute_rolling_mae(residuals, stat, WINDOW)
        m["stat"] = stat
        m["quarantined"] = stat in quarantined
        rows.append(m)

    df = pd.DataFrame(rows)

    # Color-code drift
    def _style_drift(row):
        if row.get("drift"):
            return ["background-color: #7f1d1d"] * len(row)
        return [""] * len(row)

    st.subheader(f"Rolling {WINDOW}-Bet MAE vs Baseline")
    st.dataframe(
        df[["stat", "baseline_mae", "window_mae", "n", "drift", "quarantined"]].style.apply(_style_drift, axis=1),
        use_container_width=True,
    )

    drifting = [r["stat"] for r in rows if r["drift"]]
    if drifting:
        st.warning(f"Drifting stats (MAE > {MAE_THRESHOLD_MULTIPLIER}x baseline): {', '.join(drifting)}")
    else:
        st.success("No drift detected.")

    if quarantined:
        st.error(f"Quarantined stats (skipped in predictions): {', '.join(sorted(quarantined))}")
