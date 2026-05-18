"""
predictions_tab.py -- Streamlit predictions dashboard tab.

Sections:
    1. Today's Games  — win prob bar, predicted spread, predicted total
    2. Player Props   — all 7 props with model prediction, edge %, confidence bar
    3. Breakout Alerts — top 10 players with highest breakout_score today

Can be imported and rendered by apps/dashboards/app.py via render_predictions_tab().
Can also be run standalone: streamlit run apps/dashboards/predictions_tab.py
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_SEASONS = ["2024-25", "2023-24", "2022-23"]


# ─────────────────────────────────────────────────────────────────────────────
# Section 0: Today's Edges (ranked by EV)
# ─────────────────────────────────────────────────────────────────────────────

def _render_today_edges(season: str) -> None:
    """Top betting edges for today ranked by expected value."""
    import streamlit as st
    st.markdown("### Today's Edges")

    col_refresh, col_min_ev = st.columns([1, 2])
    with col_min_ev:
        min_ev = st.slider("Min EV %", min_value=1, max_value=15, value=3, key="edges_min_ev") / 100.0
    with col_refresh:
        run_btn = st.button("Find Edges", key="edges_run", type="primary")

    if not run_btn:
        st.caption("Click **Find Edges** to fetch today's projections and detect +EV bets.")
        return

    with st.spinner("Running full prediction cascade + edge detection…"):
        edges = []
        error_msg = None
        try:
            from src.pipeline.prediction_orchestrator import PredictionOrchestrator
            orch = PredictionOrchestrator(season=season)
            edges = orch.get_today_edges(min_ev=min_ev)
        except Exception as e:
            error_msg = str(e)

    if error_msg:
        st.error(f"Edge detection failed: {error_msg}")
        return

    if not edges:
        st.info("No edges found above the minimum EV threshold. Try lowering the slider.")
        return

    # Summary metrics
    high = sum(1 for e in edges if e.confidence == "high")
    med  = sum(1 for e in edges if e.confidence == "medium")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Edges", len(edges))
    c2.metric("High Conf", high)
    c3.metric("Medium Conf", med)
    c4.metric("Top EV", f"{edges[0].ev:.1%}" if edges else "—")

    # Edge table
    import pandas as pd
    rows = []
    for e in edges[:25]:
        rows.append({
            "Player":     e.player_name,
            "Stat":       e.stat.upper(),
            "Dir":        e.direction.upper(),
            "Line":       e.line,
            "Proj":       f"{e.projection:.1f}",
            "EV":         f"{e.ev:.1%}",
            "Kelly":      f"{e.kelly_fraction:.1%}",
            "Conf":       e.confidence.upper(),
            "Agreement":  e.model_agreement,
        })

    df = pd.DataFrame(rows)
    # Color-code by confidence
    def _row_style(row):
        c = row["Conf"]
        if c == "HIGH":
            return ["background-color: #1a3a1a"] * len(row)
        if c == "MEDIUM":
            return ["background-color: #2a2a1a"] * len(row)
        return [""] * len(row)

    st.dataframe(
        df.style.apply(_row_style, axis=1),
        use_container_width=True, hide_index=True
    )

    # Model agreement breakdown
    with st.expander("Model agreement details", expanded=False):
        st.caption(
            "Agreement counts: 1 = projection alone, 2 = +matchup adj, 3 = +usage adj. "
            "Higher agreement → higher confidence edge."
        )
        for e in edges[:5]:
            st.markdown(
                f"**{e.player_name} {e.stat.upper()} {e.direction.upper()} {e.line}** — "
                f"Proj: {e.projection:.1f} | EV: {e.ev:.1%} | "
                f"Models: {e.model_agreement}/3 | {e.confidence.upper()}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Today's Games
# ─────────────────────────────────────────────────────────────────────────────

def _render_todays_games(season: str) -> None:
    """Display today's games with win probability bars, spread, total."""
    import streamlit as st
    st.markdown("### Today's Games")

    games = []
    try:
        from src.prediction.game_prediction import predict_today
        result = predict_today(season=season)
        if isinstance(result, list):
            games = result
        elif isinstance(result, dict):
            games = result.get("games", [])
    except Exception as e:
        st.caption(f"Game predictions unavailable: {e}")
        return

    if not games:
        st.caption("No games scheduled today or model not loaded.")
        return

    import pandas as pd

    rows = []
    for g in games:
        home = g.get("home_team", g.get("home_team_abbreviation", "—"))
        away = g.get("away_team", g.get("away_team_abbreviation", "—"))
        wp = float(g.get("home_win_prob", g.get("win_prob", 0.5)) or 0.5)
        spread = g.get("predicted_spread", g.get("spread", None))
        total = g.get("predicted_total", g.get("total", None))
        rows.append({
            "Matchup":        f"{away} @ {home}",
            "Home Win %":     f"{wp:.0%}",
            "Spread":         f"{spread:+.1f}" if spread is not None else "—",
            "Total":          f"{total:.1f}" if total is not None else "—",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Win probability bars for each game
    st.markdown("**Win Probability**")
    for g in games[:8]:
        home = g.get("home_team", g.get("home_team_abbreviation", "—"))
        away = g.get("away_team", g.get("away_team_abbreviation", "—"))
        wp = float(g.get("home_win_prob", g.get("win_prob", 0.5)) or 0.5)
        col_label, col_bar = st.columns([2, 5])
        with col_label:
            st.caption(f"{away} @ {home}")
        with col_bar:
            st.progress(wp, text=f"{home} {wp:.0%}")


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Player Props
# ─────────────────────────────────────────────────────────────────────────────

_PROP_LABELS = {
    "pts": "Points", "reb": "Rebounds", "ast": "Assists",
    "fg3m": "3-Pointers", "stl": "Steals", "blk": "Blocks", "tov": "Turnovers",
}


def _render_player_props(season: str) -> None:
    """Player props section with dropdown, predictions, DNP badge, injury risk."""
    import streamlit as st
    st.markdown("### Player Props")

    # Build player list from player_avgs cache
    player_names: list = []
    try:
        import json
        avgs_path = os.path.join(PROJECT_DIR, "data", "nba", f"player_avgs_{season}.json")
        if os.path.exists(avgs_path):
            avgs = json.load(open(avgs_path))
            player_names = sorted(
                name.title() for name, info in avgs.items()
                if isinstance(info, dict) and info.get("gp", 0) >= 10
            )
    except Exception:
        pass

    if not player_names:
        player_input = st.text_input("Player name", placeholder="LeBron James", key="props_player_input")
        selected_player = player_input.strip() if player_input else None
    else:
        selected_player = st.selectbox(
            "Select player", ["— Select a player —"] + player_names, key="props_player_sel"
        )
        if selected_player == "— Select a player —":
            selected_player = None

    opp_team = st.text_input("Opponent team (optional)", placeholder="BOS", key="props_opp")

    if not selected_player:
        st.caption("Select a player to see prop projections.")
        return

    with st.spinner(f"Loading props for {selected_player}..."):
        try:
            from src.prediction.player_props import predict_props
            preds = predict_props(
                player_name=selected_player.lower(),
                opp_team=opp_team.strip().upper() if opp_team.strip() else "LAL",
                season=season,
            )
        except Exception as e:
            st.error(f"Props prediction failed: {e}")
            return

    # DNP badge
    dnp_risk = float(preds.get("dnp_risk", 0.0) or 0.0)
    injury_status = preds.get("injury_status", "Active")
    col_name, col_dnp, col_inj = st.columns([3, 1, 2])
    with col_name:
        st.markdown(f"**{selected_player}**  vs  {opp_team.upper() or 'TBD'}")
    with col_dnp:
        dnp_color = "🔴" if dnp_risk >= 0.2 else "🟢"
        st.metric("DNP Risk", f"{dnp_color} {dnp_risk:.0%}")
    with col_inj:
        st.metric("Injury Status", injury_status or "Active")

    # Props table
    prop_stats = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
    import pandas as pd
    rows = []
    for stat in prop_stats:
        val = preds.get(stat)
        if val is not None:
            rows.append({
                "Stat":       _PROP_LABELS.get(stat, stat.upper()),
                "Projection": f"{float(val):.1f}",
                "Line":       "—",
                "Edge %":     "—",
            })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Confidence + minutes
    confidence = preds.get("confidence", "rolling")
    minutes = preds.get("minutes_proj")
    st.caption(
        f"Model: **{confidence}**"
        + (f"  |  Minutes projected: **{minutes:.0f}**" if minutes else "")
    )

    # Visual confidence bars per stat
    with st.expander("Projection confidence breakdown", expanded=False):
        feats = preds.get("features", {})
        for stat in ("pts", "reb", "ast"):
            season_val = feats.get(f"season_{stat}", 0.0)
            roll_val   = feats.get(f"{stat}_roll", 0.0)
            bayes_val  = feats.get(f"{stat}_bayes", 0.0)
            pred_val   = float(preds.get(stat, 0.0) or 0.0)
            if season_val > 0:
                rel = min(pred_val / season_val, 1.5)
                st.caption(f"{_PROP_LABELS[stat]}: season avg {season_val:.1f}  |  rolling {roll_val:.1f}  |  projected {pred_val:.1f}")
                st.progress(min(rel / 1.5, 1.0))


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Breakout Alerts
# ─────────────────────────────────────────────────────────────────────────────

def _render_breakout_alerts(season: str) -> None:
    """Top 10 breakout candidates for tonight."""
    import streamlit as st
    st.markdown("### Breakout Alerts")

    with st.spinner("Computing breakout scores..."):
        candidates = []
        try:
            from src.prediction.breakout_predictor import get_breakout_candidates
            candidates = get_breakout_candidates(season=season, top_n=10, min_score=0.15)
        except Exception as e:
            st.caption(f"Breakout data unavailable: {e}")
            return

    if not candidates:
        st.caption("No breakout candidates found. Player form data may be stale.")
        return

    import pandas as pd
    rows = []
    for c in candidates:
        player  = c.get("player", "—")
        opp     = c.get("opponent", "—") or "—"
        score   = float(c.get("breakout_score", 0.0))
        signals = c.get("signals", {})
        season_avgs = c.get("season_avgs", {})
        pts_avg = float(season_avgs.get("pts", 0.0))
        pts_boost = round(pts_avg * score * 0.15, 1)
        top_signal = list(signals.keys())[0].replace("_", " ") if signals else "—"
        rows.append({
            "Player":           player.title(),
            "Opponent":         opp,
            "Breakout Score":   f"{score:.2f}",
            "Pts Above Avg":    f"+{pts_boost:.1f}",
            "Key Signal":       top_signal,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Highlight top 3
    if candidates:
        top = candidates[0]
        st.success(
            f"**Top Breakout:** {top['player'].title()}  "
            f"(score {top['breakout_score']:.2f}) — "
            + ", ".join(list(top.get("signals", {}).keys())[:2]).replace("_", " ")
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main render function — called from app.py
# ─────────────────────────────────────────────────────────────────────────────

def render_predictions_tab(season: str = "2024-25") -> None:
    """
    Render the full predictions tab.  Call from within a `with tab_predictions:` block.
    """
    import streamlit as st
    season_sel = st.selectbox("Season", _SEASONS, index=0, key="pred_tab_season")

    st.divider()
    _render_today_edges(season_sel)

    st.divider()
    _render_todays_games(season_sel)

    st.divider()
    _render_player_props(season_sel)

    st.divider()
    _render_breakout_alerts(season_sel)


# ─────────────────────────────────────────────────────────────────────────────
# Standalone entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import streamlit as st
    st.set_page_config(page_title="NBA AI — Predictions", layout="wide", page_icon="📊")
    st.title("NBA AI — Predictions Dashboard")
    render_predictions_tab()
