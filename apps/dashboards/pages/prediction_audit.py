"""Prediction Audit — per-game rationale and ensemble spread."""
import os
import json
import glob
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Prediction Audit", layout="wide")
st.title("Prediction Audit")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PREDICTIONS_DIR = os.path.join(PROJECT_DIR, "data", "output", "daily_predictions")


def list_prediction_files(predictions_dir: str = PREDICTIONS_DIR) -> list:
    """Return sorted list of prediction JSON file paths (most recent first).

    Args:
        predictions_dir: Directory containing daily prediction JSON files.

    Returns:
        List of absolute file paths, sorted newest first.
    """
    if not os.path.exists(predictions_dir):
        return []
    files = sorted(glob.glob(os.path.join(predictions_dir, "*.json")), reverse=True)
    return files


def load_predictions(path: str) -> list:
    """Load prediction records from a JSON file.

    Handles both list format and dict-keyed format.

    Args:
        path: Absolute path to a predictions JSON file.

    Returns:
        List of prediction dicts, or empty list on failure.
    """
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Might be {game_id: [...predictions...]}
            rows = []
            for game_id, preds in data.items():
                if isinstance(preds, list):
                    for p in preds:
                        p["game_id"] = game_id
                        rows.append(p)
            return rows
    except Exception:
        pass
    return []


@st.cache_data(ttl=60)
def _list_prediction_files() -> list:
    return list_prediction_files()


@st.cache_data(ttl=60)
def _load_predictions(path: str) -> list:
    return load_predictions(path)


files = _list_prediction_files()

if not files:
    st.info(
        "No prediction files found in `data/output/daily_predictions/`. "
        "Run `run_daily_slate.py` to generate predictions."
    )
else:
    # File picker
    file_labels = [os.path.basename(f) for f in files]
    selected_label = st.selectbox("Select prediction file", file_labels)
    selected_path = files[file_labels.index(selected_label)]

    predictions = _load_predictions(selected_path)

    if not predictions:
        st.warning("No predictions found in this file.")
    else:
        df = pd.DataFrame(predictions)
        st.write(f"**{len(df)} predictions** in `{selected_label}`")

        # Ensemble spread (std across base learner columns if available)
        spread_cols = [
            c for c in df.columns
            if c.startswith("pred_") or c in ("xgb_pred", "lgb_pred", "cat_pred")
        ]
        if len(spread_cols) >= 2:
            df["ensemble_spread"] = df[spread_cols].std(axis=1)
            st.subheader("Ensemble Spread (prediction disagreement)")
            import plotly.express as px
            fig = px.histogram(
                df,
                x="ensemble_spread",
                nbins=30,
                title="Distribution of Ensemble Spread",
                template="plotly_dark",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Full table
        st.subheader("All Predictions")
        st.dataframe(df, use_container_width=True)
