"""NBA AI System — Streamlit Dashboard."""
import os
import streamlit as st
import pandas as pd

from tracking.database import get_connection
from dashboards.charts import shot_chart, defensive_pressure_heatmap, tracking_overlay, lineup_impact_chart

st.set_page_config(page_title="NBA AI System", layout="wide", page_icon="🏀")

st.markdown("""
<style>
body { background-color: #1a1a2e; color: white; }
.stSelectbox label, .stSlider label { color: white; }
</style>
""", unsafe_allow_html=True)

st.title("🏀 NBA AI System")


# ── Sidebar: game selector ────────────────────────────────────────────────────
def load_games():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, home_team, away_team, game_date FROM games ORDER BY game_date DESC LIMIT 50")
                rows = cur.fetchall()
        return {f"{r[1]} vs {r[2]} ({r[3]})": str(r[0]) for r in rows}
    except Exception:
        return {"Demo Mode (no DB)": None}


games = load_games()
selected_label = st.sidebar.selectbox("Select Game", list(games.keys()))
game_id = games[selected_label]

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Shot Chart", "Defensive Pressure", "Tracking", "Lineup Impact", "Chat"
])


# ── Tab 1: Shot Chart ─────────────────────────────────────────────────────────
with tab1:
    shots = []
    if game_id:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT x_coord, y_coord, made, player_id
                        FROM shot_logs WHERE game_id = %s
                    """, (game_id,))
                    for row in cur.fetchall():
                        shots.append({"x": row[0], "y": row[1], "made": row[2], "player_id": str(row[3])})
        except Exception as e:
            st.warning(f"Could not load shots: {e}")

    if not shots:
        # Demo data
        import random
        random.seed(42)
        shots = [
            {"x": random.randint(200, 740), "y": random.randint(20, 350),
             "made": random.random() > 0.55, "player_id": str(random.randint(1, 5))}
            for _ in range(60)
        ]
        st.info("Showing demo data — run the pipeline on a real game to populate.")

    st.plotly_chart(shot_chart(shots), use_container_width=True)
    st.metric("Total Shots", len(shots))
    st.metric("FG%", f"{sum(1 for s in shots if s['made']) / len(shots):.1%}")


# ── Tab 2: Defensive Pressure ─────────────────────────────────────────────────
with tab2:
    frames = []
    if game_id:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT x_coord, y_coord, speed
                        FROM tracking_coordinates
                        WHERE game_id = %s
                        LIMIT 2000
                    """, (game_id,))
                    for row in cur.fetchall():
                        frames.append({"x": row[0], "y": row[1], "pressure": max(row[2] or 1, 1)})
        except Exception as e:
            st.warning(f"Could not load tracking data: {e}")

    if not frames:
        import random
        random.seed(7)
        frames = [
            {"x": random.randint(100, 840), "y": random.randint(20, 450),
             "pressure": random.uniform(10, 200)}
            for _ in range(500)
        ]
        st.info("Showing demo data.")

    st.plotly_chart(defensive_pressure_heatmap(frames), use_container_width=True)


# ── Tab 3: Tracking Overlay ───────────────────────────────────────────────────
with tab3:
    tracks = []
    if game_id:
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT track_id, x_coord, y_coord, frame_number
                        FROM tracking_coordinates
                        WHERE game_id = %s
                        ORDER BY frame_number
                        LIMIT 3000
                    """, (game_id,))
                    for row in cur.fetchall():
                        tracks.append({"track_id": row[0], "x": row[1], "y": row[2], "frame_number": row[3]})
        except Exception as e:
            st.warning(f"Could not load tracking: {e}")

    if not tracks:
        import random, math
        random.seed(3)
        for pid in range(1, 6):
            x, y = random.randint(200, 700), random.randint(100, 400)
            for f in range(0, 300, 10):
                x += random.randint(-15, 15)
                y += random.randint(-15, 15)
                tracks.append({"track_id": pid, "x": max(0, min(940, x)),
                                "y": max(0, min(500, y)), "frame_number": f})
        st.info("Showing demo data.")

    st.plotly_chart(tracking_overlay(tracks), use_container_width=True)


# ── Tab 4: Lineup Impact ──────────────────────────────────────────────────────
with tab4:
    lineups = []
    if game_id:
        try:
            from models.lineup_optimizer import LineupOptimizer
            model = LineupOptimizer.load("lineup_optimizer")
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT DISTINCT player_id FROM tracking_coordinates
                        WHERE game_id = %s AND player_id IS NOT NULL LIMIT 20
                    """, (game_id,))
                    player_ids = [str(r[0]) for r in cur.fetchall()]
            if len(player_ids) >= 5:
                from itertools import combinations
                for combo in list(combinations(player_ids, 5))[:10]:
                    score = model.predict({"lineup": list(combo)})
                    lineups.append({
                        "label": ", ".join(str(p)[:6] for p in combo),
                        "net_rating": score.get("net_rating", 0),
                        "epa": score.get("epa", 0),
                    })
        except Exception as e:
            st.warning(f"Could not score lineups: {e}")

    if not lineups:
        lineups = [
            {"label": f"Lineup {i+1}", "net_rating": round((5 - i) * 1.8, 1), "epa": round((5 - i) * 0.9, 1)}
            for i in range(6)
        ]
        st.info("Showing demo data.")

    st.plotly_chart(lineup_impact_chart(lineups), use_container_width=True)


# ── Tab 5: Conversational AI ──────────────────────────────────────────────────
with tab5:
    st.subheader("Ask the AI")
    st.caption("Ask anything about the game, players, or predictions.")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("e.g. What was the win probability in Q4?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    from analytics.chat import answer
                    response = answer(prompt, game_id=game_id)
                except Exception as e:
                    response = f"Error: {e}"
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
