"""Alert Log — shows pipeline alerts from vault/alerts.log."""
import os
import streamlit as st

st.set_page_config(page_title="Alert Log", layout="wide")
st.title("Alert Log")

PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ALERTS_LOG = os.path.join(PROJECT_DIR, "vault", "alerts.log")
ALERTS_DIR = os.path.join(PROJECT_DIR, "data", "output", "alerts")


def load_alerts(alerts_log: str = ALERTS_LOG, alerts_dir: str = ALERTS_DIR) -> list:
    """Load alerts from vault/alerts.log (one line per alert, ISO timestamp prefix).

    Also scans data/output/alerts/ for ALERT_*.txt files.

    Args:
        alerts_log: Path to the main alerts log file.
        alerts_dir: Path to directory of individual alert txt files.

    Returns:
        List of alert dicts with 'timestamp' and 'message' keys, most recent first.
    """
    alerts = []
    if os.path.exists(alerts_log):
        try:
            with open(alerts_log, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    # Format: "2026-05-21T16:00:00Z ALERT message"
                    parts = line.split(" ", 1)
                    ts = parts[0] if len(parts) > 1 else ""
                    msg = parts[1] if len(parts) > 1 else line
                    alerts.append({"timestamp": ts, "message": msg})
        except Exception:
            pass
    # Also scan alerts/ dir for ALERT_*.txt files
    if os.path.exists(alerts_dir):
        try:
            for fname in sorted(os.listdir(alerts_dir)):
                if fname.startswith("ALERT_") and fname.endswith(".txt"):
                    fpath = os.path.join(alerts_dir, fname)
                    try:
                        msg = open(fpath, encoding="utf-8").read().strip()
                        date_str = fname.replace("ALERT_", "").replace(".txt", "")
                        alerts.append({"timestamp": date_str, "message": msg, "source": "file"})
                    except Exception:
                        pass
        except Exception:
            pass
    return list(reversed(alerts))  # Most recent first


@st.cache_data(ttl=30)
def _load_alerts() -> list:
    return load_alerts()


alerts = _load_alerts()

if not alerts:
    st.success("No alerts recorded. System running clean.")
else:
    st.warning(f"{len(alerts)} alert(s) found.")
    import pandas as pd
    df = pd.DataFrame(alerts)
    st.dataframe(df, use_container_width=True)

    # Most recent alert highlighted
    st.subheader("Most Recent Alert")
    st.error(f"**{alerts[0]['timestamp']}** — {alerts[0]['message']}")

# Refresh button
if st.button("Refresh"):
    st.cache_data.clear()
    st.rerun()
