"""NBA AI System — Film Analysis Dashboard."""
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from src.data.db import get_connection
from dashboards.charts import (
    shot_chart, player_tracks, speed_heatmap, drive_map,
    ball_speed_timeline, spacing_timeline, play_type_chart,
    defensive_scheme_chart, momentum_chart, pressure_heatmap,
)

st.set_page_config(page_title="NBA AI", layout="wide", page_icon="🏀",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
  html, body, [data-testid="stAppViewContainer"] { background: #0f1117; color: white; }
  [data-testid="stSidebar"] { background: #1c1f2e; }
  .metric-card {
    background: #1c1f2e; border-radius: 10px; padding: 16px 20px;
    border: 1px solid #2d3147; text-align: center;
  }
  .metric-val { font-size: 2rem; font-weight: 700; color: #60a5fa; }
  .metric-lbl { font-size: 0.8rem; color: #9ca3af; margin-top: 2px; }
  div[data-testid="stTabs"] button { color: #9ca3af !important; }
  div[data-testid="stTabs"] button[aria-selected="true"] { color: white !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def _load_games():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, home_team, away_team, game_date, season
                    FROM games ORDER BY game_date DESC LIMIT 100
                """)
                rows = cur.fetchall()
        if rows:
            return {f"{r[1]} vs {r[2]}  ({r[3]})": str(r[0]) for r in rows}
    except Exception:
        pass
    return {}


def _run_pipeline(video_path: str, game_id: str) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pipelines.run_pipeline",
         "--video", video_path, "--game-id", game_id, "--skip", "2"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    return r.returncode == 0, r.stderr[-2000:] if r.returncode != 0 else r.stdout[-500:]


def _run_features(game_id: str) -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-m", "features.feature_pipeline", "--game-id", game_id],
        capture_output=True, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    return r.returncode == 0, r.stderr[-2000:] if r.returncode != 0 else r.stdout[-500:]


# ── Sidebar: game selector ────────────────────────────────────────────────────

games = _load_games()
st.sidebar.title("🏀 NBA AI")
st.sidebar.markdown("---")

if games:
    labels = list(games.keys())
    default = 0
    if "selected_game_id" in st.session_state:
        for i, gid in enumerate(games.values()):
            if gid == st.session_state.get("selected_game_id"):
                default = i
                break
    selected_label = st.sidebar.selectbox("Game", labels, index=default)
    game_id = games[selected_label]
else:
    st.sidebar.info("No games processed yet.")
    game_id = None

st.sidebar.markdown("---")
st.sidebar.caption("Upload a new game in the **Upload** tab.")


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_upload, tab_film, tab_movement, tab_plays, tab_defense, tab_predictions, tab_monitoring = st.tabs([
    "Upload", "Film Review", "Movement", "Play Analysis", "Defense", "Predictions", "Monitoring"
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 0 — Upload
# ═══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    st.subheader("Process a Game Video")
    st.caption("Upload an MP4/MOV and run the full tracking + analytics pipeline.")

    with st.expander("Game Details (optional)"):
        c1, c2 = st.columns(2)
        home_team  = c1.text_input("Home Team", placeholder="e.g. Boston Celtics")
        away_team  = c2.text_input("Away Team", placeholder="e.g. Golden State Warriors")
        game_date  = st.date_input("Game Date")
        season     = st.text_input("Season", placeholder="e.g. 2024-25")

    home_team = home_team or "Home"
    away_team = away_team or "Away"
    season    = season    or "2024-25"

    uploaded = st.file_uploader("Video file", type=["mp4", "avi", "mov", "mkv"])

    if uploaded and st.button("▶ Run Pipeline", type="primary"):
        suffix  = Path(uploaded.name).suffix
        tmp     = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(uploaded.read())
        tmp.close()

        new_game_id = str(uuid.uuid4())
        bar = st.progress(0, text="Creating game record…")

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO games (id, home_team, away_team, game_date, season)
                        VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
                    """, (new_game_id, home_team, away_team, str(game_date), season))
                conn.commit()
        except Exception as e:
            st.error(f"DB error: {e}")
            st.stop()

        bar.progress(10, text="Running tracking pipeline… (this takes a while)")
        ok, msg = _run_pipeline(tmp.name, new_game_id)
        os.unlink(tmp.name)

        if not ok:
            bar.empty()
            st.error("Tracking pipeline failed:")
            st.code(msg)
            st.stop()

        bar.progress(75, text="Running analytics pipeline…")
        ok2, msg2 = _run_features(new_game_id)
        bar.progress(100, text="Done!")

        st.session_state["selected_game_id"] = new_game_id
        _load_games.clear()

        if ok2:
            st.success(f"Game processed successfully! Switch to Film Review tab.")
        else:
            st.warning(f"Tracking complete but analytics had warnings.")
            st.code(msg2)

        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Film Review
# ═══════════════════════════════════════════════════════════════════════════════
with tab_film:
    if not game_id:
        st.info("Select or upload a game to begin.")
        st.stop()

    # ── Summary metrics ───────────────────────────────────────────────────────
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM tracking_coordinates WHERE game_id=%s", (game_id,))
                n_tracks = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(DISTINCT frame_number) FROM tracking_coordinates WHERE game_id=%s", (game_id,))
                n_frames = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM shot_logs WHERE game_id=%s", (game_id,))
                n_shots = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM possessions WHERE game_id=%s", (game_id,))
                n_poss = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(*) FROM drive_events WHERE game_id=%s", (game_id,))
                n_drives = cur.fetchone()[0] or 0
                cur.execute("SELECT COUNT(DISTINCT play_type) FROM play_detections WHERE game_id=%s", (game_id,))
                n_play_types = cur.fetchone()[0] or 0
    except Exception:
        n_tracks = n_frames = n_shots = n_poss = n_drives = n_play_types = 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    for col, val, lbl in [
        (c1, f"{n_frames:,}", "Frames"),
        (c2, f"{n_tracks:,}", "Detections"),
        (c3, str(n_shots), "Shots"),
        (c4, str(n_poss), "Possessions"),
        (c5, str(n_drives), "Drives"),
        (c6, str(n_play_types), "Play Types"),
    ]:
        col.markdown(f'<div class="metric-card"><div class="metric-val">{val}</div>'
                     f'<div class="metric-lbl">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Shot chart ─────────────────────────────────────────────────────────────
    left_col, right_col = st.columns([3, 2])

    with left_col:
        shots = []
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COALESCE(x_ft, x), COALESCE(y_ft, y), made, shot_type
                        FROM shot_logs WHERE game_id=%s
                    """, (game_id,))
                    shots = [{"x": r[0], "y": r[1], "made": r[2], "shot_type": r[3]}
                             for r in cur.fetchall()]
        except Exception:
            pass

        if not shots:
            # Demo data on real court coordinates
            import random; random.seed(42)
            _corners  = [(5,25),(10,10),(10,40),(20,8),(20,42),(25,25),(30,15),(30,35)]
            shots = [{"x": x + random.uniform(-1,1), "y": y + random.uniform(-1,1),
                      "made": random.random()>0.55, "shot_type": "2pt" if x<22 else "3pt"}
                     for x, y in _corners * 4]
            st.caption("⚠ Demo data — run pipeline on a real game to populate.")

        made_n   = sum(1 for s in shots if s.get("made"))
        total_n  = len(shots)
        fg_pct   = made_n / total_n if total_n else 0
        three_pt = [s for s in shots if s.get("shot_type") == "3pt"]
        three_made = sum(1 for s in three_pt if s.get("made"))

        st.plotly_chart(shot_chart(shots), use_container_width=True)

    with right_col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Shots", total_n)
        m2.metric("FG%", f"{fg_pct:.1%}")
        m3.metric("3PT%", f"{three_made/len(three_pt):.1%}" if three_pt else "—")

        # Ball speed timeline
        ball_speeds = []
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT frame_number, speed
                        FROM tracking_coordinates
                        WHERE game_id=%s AND object_type='ball'
                        ORDER BY frame_number
                    """, (game_id,))
                    ball_speeds = [{"frame_number": r[0], "speed": r[1] or 0}
                                   for r in cur.fetchall()]
        except Exception:
            pass

        st.plotly_chart(ball_speed_timeline(ball_speeds), use_container_width=True)

    # ── Spacing timeline ───────────────────────────────────────────────────────
    spacing_rows = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT frame_number, avg_inter_player_dist, convex_hull_area
                    FROM feature_vectors WHERE game_id=%s
                    ORDER BY frame_number
                """, (game_id,))
                spacing_rows = [{"frame_number": r[0],
                                 "avg_inter_player_dist": r[1] or 0,
                                 "convex_hull_area": r[2] or 0}
                                for r in cur.fetchall()]
    except Exception:
        pass

    if spacing_rows:
        st.plotly_chart(spacing_timeline(spacing_rows), use_container_width=True)

    # ── Momentum ───────────────────────────────────────────────────────────────
    flow_rows = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT frame_number, momentum_index, scoring_run_probability
                    FROM game_flow WHERE game_id=%s ORDER BY frame_number
                """, (game_id,))
                flow_rows = [{"frame_number": r[0], "momentum_index": r[1] or 0,
                              "scoring_run_probability": r[2] or 0}
                             for r in cur.fetchall()]
    except Exception:
        pass

    if flow_rows:
        st.plotly_chart(momentum_chart(flow_rows), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Movement
# ═══════════════════════════════════════════════════════════════════════════════
with tab_movement:
    if not game_id:
        st.info("Select a game.")
        st.stop()

    # Frame range slider
    frame_range = (0, 1)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT MIN(frame_number), MAX(frame_number)
                    FROM tracking_coordinates WHERE game_id=%s
                """, (game_id,))
                row = cur.fetchone()
                if row and row[0] is not None:
                    frame_range = (int(row[0]), int(row[1]))
    except Exception:
        pass

    f_min, f_max = frame_range
    c1, c2 = st.columns([3, 1])
    sel = c1.slider("Frame range", f_min, max(f_max, f_min+1),
                    (f_min, min(f_min + 300, f_max)), step=10, key="mv_slider")
    track_filter = c2.text_input("Track IDs (comma-sep, blank=all)", key="mv_tracks")

    sel_ids = [int(x.strip()) for x in track_filter.split(",") if x.strip().isdigit()]

    tracks_data = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                id_clause = f"AND track_id = ANY(ARRAY{sel_ids})" if sel_ids else ""
                cur.execute(f"""
                    SELECT track_id, COALESCE(x_ft,x), COALESCE(y_ft,y),
                           frame_number, object_type, team
                    FROM tracking_coordinates
                    WHERE game_id=%s
                      AND frame_number BETWEEN %s AND %s
                      {id_clause}
                    ORDER BY frame_number
                    LIMIT 5000
                """, (game_id, sel[0], sel[1]))
                tracks_data = [{"track_id": r[0], "x": r[1], "y": r[2],
                                "frame_number": r[3], "object_type": r[4], "team": r[5]}
                               for r in cur.fetchall()]
    except Exception as e:
        st.warning(f"Could not load tracks: {e}")

    st.plotly_chart(player_tracks(tracks_data), use_container_width=True)

    # Speed heatmap
    speed_pts = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(x_ft,x), COALESCE(y_ft,y), speed
                    FROM tracking_coordinates
                    WHERE game_id=%s AND object_type='player' AND speed IS NOT NULL
                    LIMIT 8000
                """, (game_id,))
                speed_pts = [{"x": r[0], "y": r[1], "speed": r[2] or 0}
                             for r in cur.fetchall()]
    except Exception:
        pass

    if speed_pts:
        st.plotly_chart(speed_heatmap(speed_pts), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Play Analysis
# ═══════════════════════════════════════════════════════════════════════════════
with tab_plays:
    if not game_id:
        st.info("Select a game.")
        st.stop()

    c1, c2 = st.columns(2)

    with c1:
        plays = []
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT play_type, play_start_frame, play_end_frame, confidence
                        FROM play_detections WHERE game_id=%s
                    """, (game_id,))
                    plays = [{"play_type": r[0], "start": r[1], "end": r[2], "conf": r[3]}
                             for r in cur.fetchall()]
        except Exception:
            pass
        st.plotly_chart(play_type_chart(plays), use_container_width=True)

    with c2:
        # Drive map — need start position for each drive
        drive_rows = []
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT de.track_id, de.start_frame, de.defender_beaten,
                               de.penetration_depth,
                               tc.x_ft, tc.y_ft
                        FROM drive_events de
                        JOIN tracking_coordinates tc
                          ON tc.game_id = de.game_id
                         AND tc.frame_number = de.start_frame
                         AND tc.track_id = de.track_id
                        WHERE de.game_id=%s
                        LIMIT 300
                    """, (game_id,))
                    drive_rows = [{"x": r[4] or 47, "y": r[5] or 25,
                                   "defender_beaten": r[2],
                                   "penetration_depth": r[3] or 0}
                                  for r in cur.fetchall()]
        except Exception:
            pass
        st.plotly_chart(drive_map(drive_rows), use_container_width=True)

    # Play detection table
    if plays:
        st.markdown("#### Recent Detections")
        df_plays = pd.DataFrame(plays).head(50)
        df_plays["confidence"] = df_plays["conf"].apply(
            lambda x: f"{x:.0%}" if x else "—"
        )
        st.dataframe(
            df_plays[["play_type", "start", "end", "confidence"]].rename(columns={
                "play_type": "Play", "start": "Start Frame",
                "end": "End Frame", "confidence": "Confidence"
            }),
            use_container_width=True, hide_index=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Defense
# ═══════════════════════════════════════════════════════════════════════════════
with tab_defense:
    if not game_id:
        st.info("Select a game.")
        st.stop()

    c1, c2 = st.columns(2)

    with c1:
        schemes = []
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT scheme_label, switch_frequency, help_frequency,
                               paint_collapse_frequency, cohesion_score
                        FROM defensive_schemes WHERE game_id=%s
                    """, (game_id,))
                    schemes = [{"scheme_label": r[0], "switch_freq": r[1],
                                "help_freq": r[2], "collapse_freq": r[3],
                                "cohesion": r[4]}
                               for r in cur.fetchall()]
        except Exception:
            pass
        st.plotly_chart(defensive_scheme_chart(schemes), use_container_width=True)

        # Scheme averages table
        if schemes:
            df_s = pd.DataFrame(schemes)
            avg = df_s.groupby("scheme_label")[
                ["switch_freq","help_freq","collapse_freq","cohesion"]
            ].mean().round(3)
            avg.columns = ["Switch %", "Help %", "Paint Collapse %", "Cohesion"]
            st.dataframe(avg, use_container_width=True)

    with c2:
        # Pressure heatmap using feature_vectors
        pressure_pts = []
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT tc.x_ft, tc.y_ft, fv.nearest_defender_dist
                        FROM feature_vectors fv
                        JOIN tracking_coordinates tc
                          ON tc.game_id = fv.game_id
                         AND tc.frame_number = fv.frame_number
                         AND tc.object_type = 'ball'
                        WHERE fv.game_id=%s
                          AND fv.nearest_defender_dist IS NOT NULL
                          AND fv.nearest_defender_dist > 0
                        LIMIT 3000
                    """, (game_id,))
                    pressure_pts = [{"x": r[0] or 47, "y": r[1] or 25,
                                     "nearest_defender_dist": r[2]}
                                    for r in cur.fetchall()]
        except Exception:
            pass
        st.plotly_chart(pressure_heatmap(pressure_pts), use_container_width=True)

    # Micro timing table
    st.markdown("#### Decision Timing")
    timing_rows = []
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT track_id, frame_number, event_type,
                           catch_to_shot_time, catch_to_drive_time,
                           catch_to_pass_time, decision_latency
                    FROM micro_timing_events WHERE game_id=%s
                    ORDER BY frame_number LIMIT 100
                """, (game_id,))
                timing_rows = cur.fetchall()
    except Exception:
        pass

    if timing_rows:
        df_t = pd.DataFrame(timing_rows, columns=[
            "Track ID", "Frame", "Event", "→Shot (s)", "→Drive (s)",
            "→Pass (s)", "Decision Latency"
        ])
        for col in ["→Shot (s)", "→Drive (s)", "→Pass (s)", "Decision Latency"]:
            df_t[col] = df_t[col].apply(lambda x: f"{x:.2f}" if x else "—")
        st.dataframe(df_t, use_container_width=True, hide_index=True)
    else:
        st.caption("No micro-timing data yet.")


# =============================================================================
# TAB 5 — Predictions
# =============================================================================
with tab_predictions:
    # ── Phase E5: Full predictions dashboard ──────────────────────────────────
    try:
        from dashboards.predictions_tab import _render_todays_games
        _render_todays_games(season="2024-25")
        st.divider()
    except Exception:
        pass  # today's games section optional

    st.subheader("Player Prop Predictions")

    season_sel = st.sidebar.text_input("Season", value="2024-25", key="pred_season")
    player_sel = st.text_input("Player name", placeholder="e.g. LeBron James", key="pred_player")
    opp_sel    = st.text_input("Opponent team (optional)", placeholder="e.g. BOS", key="pred_opp")

    col_prop, col_dnp, col_edge = st.columns(3)

    # ── Prop projections ──────────────────────────────────────────────────────
    with col_prop:
        st.markdown("#### Prop Projections")
        if player_sel:
            try:
                from src.prediction.player_props import predict_props
                preds = predict_props(player_name=player_sel, opponent_team=opp_sel or None,
                                      season=season_sel)
                props = preds.get("props", preds)
                dnp_risk = preds.get("dnp_risk", None)

                rows = []
                for stat, val in props.items():
                    if isinstance(val, dict):
                        pred_val = val.get("prediction", val.get("value", "—"))
                    else:
                        pred_val = val
                    rows.append({"Stat": stat.upper(), "Projection": round(float(pred_val), 1) if pred_val else "—"})

                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                else:
                    st.caption("No projections available.")

                if dnp_risk is not None:
                    color = "red" if dnp_risk >= 0.4 else ("orange" if dnp_risk >= 0.2 else "green")
                    st.markdown(f"**DNP Risk:** :{color}[{dnp_risk:.0%}]")
            except Exception as e:
                st.warning(f"Prediction error: {e}")
        else:
            st.caption("Enter a player name above.")

    # ── DNP board ─────────────────────────────────────────────────────────────
    with col_dnp:
        st.markdown("#### DNP Board")
        try:
            from src.prediction.load_management import predict_load_management
            from src.data.nba_stats import get_active_players
            active = get_active_players(season_sel)[:30]
            at_risk = []
            for p in active:
                r = predict_load_management(p, season_sel)
                if r["load_mgmt_prob"] >= 0.15:
                    at_risk.append({"Player": p, "Load Mgmt %": f"{r['load_mgmt_prob']:.0%}",
                                    "Signal": r["recommendation"]})
            if at_risk:
                at_risk.sort(key=lambda x: -float(x["Load Mgmt %"].strip("%")) / 100)
                st.dataframe(pd.DataFrame(at_risk[:10]), use_container_width=True, hide_index=True)
            else:
                st.caption("No load management risk detected today.")
        except Exception:
            st.caption("Load management model not yet available.")

    # ── Edge scanner ──────────────────────────────────────────────────────────
    with col_edge:
        st.markdown("#### Model Health")
        try:
            from src.pipeline.outcome_recorder import get_calibration_report
            report = get_calibration_report(n_games=20)
            rows = []
            for stat, m in report.items():
                mae = m.get("mae")
                r2  = m.get("r2")
                rows.append({
                    "Stat": stat.upper(),
                    "MAE":  f"{mae:.3f}" if mae is not None else "—",
                    "R2":   f"{r2:.3f}"  if r2  is not None else "—",
                    "N":    m.get("n", 0),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        except Exception:
            st.caption("No outcome data yet (run games first).")

    st.divider()

    # ── Breakout candidates ───────────────────────────────────────────────────
    st.markdown("#### Breakout Candidates")
    if st.button("Scan for breakout candidates"):
        try:
            from src.prediction.breakout_predictor import get_breakout_candidates
            candidates = get_breakout_candidates(season_sel, top_n=10)
            if candidates:
                rows = [{"Player": c["player"],
                         "Score": f"{c['breakout_score']:.2f}",
                         "Signals": ", ".join(c["signals"].keys())} for c in candidates]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No breakout candidates found.")
        except Exception as e:
            st.warning(f"Error: {e}")

    # ── CLV dashboard ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### CLV Dashboard (Closing Line Value)")
    try:
        from src.analytics.clv_tracker import get_clv_summary
        summary = get_clv_summary()
        c1, c2, c3, c4 = st.columns(4)
        metrics = [
            ("Spread 7d", summary["spread_7d"]),
            ("Spread 30d", summary["spread_30d"]),
            ("Total 7d",  summary["total_7d"]),
            ("Total 30d", summary["total_30d"]),
        ]
        for col, (label, val) in zip([c1, c2, c3, c4], metrics):
            with col:
                st.markdown(f"""
                <div class="metric-card">
                  <div class="metric-val">{val['mean_clv']:+.2f}</div>
                  <div class="metric-lbl">{label} CLV  (n={val['n_games']})</div>
                </div>""", unsafe_allow_html=True)
    except Exception:
        st.caption("CLV data not yet available (run games first).")

    # ── Model version history ─────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Model Versions")
    try:
        from src.pipeline.model_version_manager import list_active_versions
        active_vers = list_active_versions()
        if active_vers:
            rows = [{"Model": k, "Version": v} for k, v in sorted(active_vers.items())]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.caption("No model versions registered yet.")
    except Exception:
        st.caption("Model version manager not available.")


# =============================================================================
# TAB 6 — Monitoring
# =============================================================================
with tab_monitoring:
    import json
    import os as _os

    st.subheader("Model Health & Drift Monitoring")

    # ── Feature drift log ─────────────────────────────────────────────────────
    st.markdown("#### Feature Drift Log")
    drift_log_path = "data/models/feature_drift_log.json"
    if _os.path.exists(drift_log_path):
        with open(drift_log_path, encoding="utf-8") as _f:
            drift_data = json.load(_f)
        st.write(f"**Models tracked:** {len(drift_data)}")
        for model_id, history in drift_data.items():
            if history:
                last = history[-1]
                ts = last.get("timestamp", "unknown")
                st.write(f"- `{model_id}`: {len(history)} snapshots, last `{ts}`")
    else:
        st.info("No drift log yet. Run daily_pipeline.py to populate.")

    st.divider()

    # ── Model metrics history ─────────────────────────────────────────────────
    st.markdown("#### Model Metrics History")
    metrics_path = "data/models/model_metrics_history.json"
    if _os.path.exists(metrics_path):
        with open(metrics_path, encoding="utf-8") as _f:
            metrics = json.load(_f)
        rows = []
        for stat, hist in metrics.items():
            if hist:
                last = hist[-1]
                rows.append({
                    "stat": stat,
                    "r2": last.get("r2"),
                    "mae": last.get("mae"),
                    "trained_at": last.get("trained_at"),
                })
        if rows:
            st.dataframe(
                pd.DataFrame(rows).set_index("stat"),
                use_container_width=True,
            )
        else:
            st.caption("Metrics history file exists but contains no entries.")
    else:
        st.info("No model metrics history yet.")

    st.divider()

    # ── Alert log from daily pipeline ─────────────────────────────────────────
    st.markdown("#### Alert Log")
    alert_log_path = "data/models/alert_log.json"
    if _os.path.exists(alert_log_path):
        with open(alert_log_path, encoding="utf-8") as _f:
            alerts = json.load(_f)
        if alerts:
            st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
        else:
            st.caption("Alert log is empty — no alerts triggered.")
    else:
        st.info("No alert log yet. Alerts are written by compare_models.py during CI.")
