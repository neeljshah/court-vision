"""Chart factories for the NBA AI film analysis dashboard.

All court coordinates are in NBA feet (0-94 x 0-50).
Left basket: (4.75, 25). Right basket: (89.25, 25).
"""
import math
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

_DARK  = "#0f1117"
_CARD  = "#1c1f2e"
_COURT = "#c68642"       # wood floor
_LINE  = "rgba(255,255,255,0.85)"
_FONT  = dict(color="white", family="Inter, sans-serif")


# ── Court drawing ─────────────────────────────────────────────────────────────

def _full_court_shapes() -> list:
    """Return Plotly shape dicts for a full NBA court in feet."""
    W, H = 94, 50
    shapes = [
        # Outer boundary
        dict(type="rect", x0=0, y0=0, x1=W, y1=H,
             line=dict(color=_LINE, width=2), fillcolor="rgba(0,0,0,0)"),
        # Half-court line
        dict(type="line", x0=47, y0=0, x1=47, y1=H,
             line=dict(color=_LINE, width=2)),
        # Center circle
        dict(type="circle", x0=41, y0=19, x1=53, y1=31,
             line=dict(color=_LINE, width=2), fillcolor="rgba(0,0,0,0)"),
        # ── Left side ──
        # Paint
        dict(type="rect", x0=0, y0=17, x1=19, y1=33,
             line=dict(color=_LINE, width=2), fillcolor="rgba(0,0,0,0)"),
        # Free throw line
        dict(type="line", x0=19, y0=17, x1=19, y1=33,
             line=dict(color=_LINE, width=2)),
        # Restricted area arc (4ft radius)
        dict(type="circle", x0=0.75, y0=21, x1=8.75, y1=29,
             line=dict(color=_LINE, width=1), fillcolor="rgba(0,0,0,0)"),
        # Backboard
        dict(type="line", x0=4, y0=22, x1=4, y1=28,
             line=dict(color=_LINE, width=3)),
        # Basket
        dict(type="circle", x0=3.5, y0=24.25, x1=6, y1=25.75,
             line=dict(color="orange", width=3), fillcolor="rgba(0,0,0,0)"),
        # Corner 3-point lines (left side)
        dict(type="line", x0=0, y0=3, x1=14, y1=3,
             line=dict(color=_LINE, width=2)),
        dict(type="line", x0=0, y0=47, x1=14, y1=47,
             line=dict(color=_LINE, width=2)),
        # ── Right side ──
        dict(type="rect", x0=75, y0=17, x1=94, y1=33,
             line=dict(color=_LINE, width=2), fillcolor="rgba(0,0,0,0)"),
        dict(type="line", x0=75, y0=17, x1=75, y1=33,
             line=dict(color=_LINE, width=2)),
        dict(type="circle", x0=85.25, y0=21, x1=93.25, y1=29,
             line=dict(color=_LINE, width=1), fillcolor="rgba(0,0,0,0)"),
        dict(type="line", x0=90, y0=22, x1=90, y1=28,
             line=dict(color=_LINE, width=3)),
        dict(type="circle", x0=88, y0=24.25, x1=90.5, y1=25.75,
             line=dict(color="orange", width=3), fillcolor="rgba(0,0,0,0)"),
        dict(type="line", x0=80, y0=3, x1=94, y1=3,
             line=dict(color=_LINE, width=2)),
        dict(type="line", x0=80, y0=47, x1=94, y1=47,
             line=dict(color=_LINE, width=2)),
    ]
    return shapes


def _add_3pt_arcs(fig: go.Figure) -> go.Figure:
    """Add left and right 3-point arcs (radius 23.75ft from basket)."""
    r = 23.75
    # Left arc: angles from ~22° to ~158° to stay within court
    angles_l = [math.radians(a) for a in range(22, 159)]
    fig.add_trace(go.Scatter(
        x=[4.75 + r * math.cos(a) for a in angles_l],
        y=[25.0 + r * math.sin(a) for a in angles_l],
        mode="lines", line=dict(color=_LINE, width=2),
        showlegend=False, hoverinfo="skip",
    ))
    # Right arc
    angles_r = [math.radians(a) for a in range(22, 159)]
    fig.add_trace(go.Scatter(
        x=[89.25 - r * math.cos(a) for a in angles_r],
        y=[25.0 + r * math.sin(a) for a in angles_r],
        mode="lines", line=dict(color=_LINE, width=2),
        showlegend=False, hoverinfo="skip",
    ))
    # Free throw arcs
    angles_ft = [math.radians(a) for a in range(0, 181)]
    r_ft = 6.0
    fig.add_trace(go.Scatter(
        x=[19.0 + r_ft * math.cos(a) for a in angles_ft],
        y=[25.0 + r_ft * math.sin(a) for a in angles_ft],
        mode="lines", line=dict(color=_LINE, width=2),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[75.0 - r_ft * math.cos(a) for a in angles_ft],
        y=[25.0 + r_ft * math.sin(a) for a in angles_ft],
        mode="lines", line=dict(color=_LINE, width=2),
        showlegend=False, hoverinfo="skip",
    ))
    return fig


def _court_layout(fig: go.Figure, title: str = "", height: int = 520) -> go.Figure:
    shapes = _full_court_shapes()
    fig = _add_3pt_arcs(fig)
    fig.update_layout(
        title=dict(text=title, font=dict(size=16, color="white")),
        shapes=shapes,
        paper_bgcolor=_DARK, plot_bgcolor=_COURT,
        font=_FONT,
        xaxis=dict(range=[-1, 95], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[-1, 51], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
        margin=dict(l=10, r=10, t=40, b=10),
        height=height,
        legend=dict(bgcolor="rgba(0,0,0,0.5)", bordercolor="#555", borderwidth=1),
    )
    return fig


# ── Chart functions ───────────────────────────────────────────────────────────

def shot_chart(shots: list) -> go.Figure:
    """Shot chart on full NBA court (feet coordinates)."""
    made   = [s for s in shots if s.get("made")]
    missed = [s for s in shots if not s.get("made")]
    unk    = [s for s in shots if s.get("made") is None]

    fig = go.Figure()
    if made:
        fig.add_trace(go.Scatter(
            x=[s["x"] for s in made], y=[s["y"] for s in made],
            mode="markers", name="Made",
            marker=dict(color="lime", size=11, symbol="circle",
                        line=dict(color="white", width=1)),
            hovertemplate="<b>Made</b><br>%.1fft, %.1fft<br>%{customdata}<extra></extra>",
            customdata=[s.get("shot_type", "") for s in made],
        ))
    if missed:
        fig.add_trace(go.Scatter(
            x=[s["x"] for s in missed], y=[s["y"] for s in missed],
            mode="markers", name="Missed",
            marker=dict(color="#ff4444", size=11, symbol="x-thin",
                        line=dict(color="#ff4444", width=2)),
            hovertemplate="<b>Missed</b><br>%.1fft, %.1fft<br>%{customdata}<extra></extra>",
            customdata=[s.get("shot_type", "") for s in missed],
        ))
    if unk:
        fig.add_trace(go.Scatter(
            x=[s["x"] for s in unk], y=[s["y"] for s in unk],
            mode="markers", name="Shot",
            marker=dict(color="white", size=9, symbol="circle-open",
                        line=dict(color="white", width=1.5)),
        ))
    return _court_layout(fig, "Shot Chart")


def player_tracks(tracks: list, max_players: int = 15) -> go.Figure:
    """Player movement paths on full court (feet)."""
    fig = go.Figure()
    if not tracks:
        return _court_layout(fig, "Player Tracks")

    df = pd.DataFrame(tracks).sort_values("frame_number")
    colors = px.colors.qualitative.Plotly + px.colors.qualitative.Dark24

    shown = 0
    for i, (tid, grp) in enumerate(df.groupby("track_id")):
        if shown >= max_players:
            break
        obj_type = grp["object_type"].iloc[0] if "object_type" in grp.columns else "player"
        is_ball = obj_type == "ball"
        team = grp["team"].iloc[0] if "team" in grp.columns else ""

        color = "orange" if is_ball else colors[i % len(colors)]
        width = 3 if is_ball else 1.5
        name  = "Ball" if is_ball else f"Track {tid} ({team})"

        fig.add_trace(go.Scatter(
            x=grp["x"], y=grp["y"],
            mode="lines+markers",
            name=name,
            line=dict(color=color, width=width),
            marker=dict(size=4 if not is_ball else 6, color=color),
            hovertemplate=f"<b>{name}</b><br>Frame %{{text}}<br>(%{{x:.1f}}ft, %{{y:.1f}}ft)<extra></extra>",
            text=grp["frame_number"].astype(str),
        ))
        if not is_ball:
            shown += 1

    return _court_layout(fig, "Player & Ball Movement Paths")


def speed_heatmap(points: list) -> go.Figure:
    """Player speed density heatmap on court (ft/s)."""
    fig = go.Figure()
    if not points:
        return _court_layout(fig, "Speed Heatmap")

    df = pd.DataFrame(points)
    fig.add_trace(go.Histogram2dContour(
        x=df["x"], y=df["y"], z=df["speed"],
        colorscale="Inferno",
        histfunc="avg",
        nbinsx=47, nbinsy=25,
        showscale=True,
        colorbar=dict(title="ft/s", tickfont=dict(color="white")),
        hoverinfo="skip",
    ))
    return _court_layout(fig, "Player Speed Heatmap (ft/s)")


def drive_map(drives: list) -> go.Figure:
    """Drive start positions on court with outcome coloring."""
    fig = go.Figure()
    if not drives:
        return _court_layout(fig, "Drive Map")

    beaten = [d for d in drives if d.get("defender_beaten")]
    not_beaten = [d for d in drives if not d.get("defender_beaten")]

    if beaten:
        fig.add_trace(go.Scatter(
            x=[d["x"] for d in beaten], y=[d["y"] for d in beaten],
            mode="markers", name="Defender Beaten",
            marker=dict(color="lime", size=12, symbol="arrow-right",
                        line=dict(color="white", width=1)),
            hovertemplate="<b>Drive — Beaten</b><br>Penetration: %{customdata:.1f}ft<extra></extra>",
            customdata=[d.get("penetration_depth", 0) for d in beaten],
        ))
    if not_beaten:
        fig.add_trace(go.Scatter(
            x=[d["x"] for d in not_beaten], y=[d["y"] for d in not_beaten],
            mode="markers", name="Stopped",
            marker=dict(color="#ff9900", size=10, symbol="arrow-right",
                        line=dict(color="white", width=1)),
            hovertemplate="<b>Drive — Stopped</b><br>Penetration: %{customdata:.1f}ft<extra></extra>",
            customdata=[d.get("penetration_depth", 0) for d in not_beaten],
        ))
    return _court_layout(fig, "Drive Map")


def ball_speed_timeline(frames: list) -> go.Figure:
    """Ball speed over time with possession and shot event markers."""
    if not frames:
        fig = go.Figure()
        fig.update_layout(title="Ball Speed Timeline",
                          paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT, height=280)
        return fig

    df = pd.DataFrame(frames).sort_values("frame_number")
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["frame_number"], y=df["speed"],
        mode="lines", name="Ball Speed",
        line=dict(color="#00d4ff", width=1.5),
        fill="tozeroy", fillcolor="rgba(0,212,255,0.08)",
        hovertemplate="Frame %{x}<br>Speed: %{y:.1f} ft/s<extra></extra>",
    ))

    # Mark shots (high-speed events near basket)
    shots_df = df[df["speed"] > 8]
    if not shots_df.empty:
        fig.add_trace(go.Scatter(
            x=shots_df["frame_number"], y=shots_df["speed"],
            mode="markers", name="Shot/Pass",
            marker=dict(color="orange", size=8, symbol="star"),
        ))

    fig.update_layout(
        title=dict(text="Ball Speed Timeline (ft/s)", font=dict(size=15, color="white")),
        paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT,
        xaxis=dict(title="Frame", gridcolor="#333", color="white"),
        yaxis=dict(title="ft/s", gridcolor="#333", color="white"),
        height=280, margin=dict(l=50, r=20, t=40, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0.5)"),
    )
    return fig


def spacing_timeline(rows: list) -> go.Figure:
    """Average inter-player spacing and convex hull area over time."""
    if not rows:
        fig = go.Figure()
        fig.update_layout(title="Team Spacing",
                          paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT, height=260)
        return fig

    df = pd.DataFrame(rows).sort_values("frame_number")
    fig = go.Figure()

    if "avg_inter_player_dist" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["frame_number"], y=df["avg_inter_player_dist"],
            mode="lines", name="Avg Spacing (ft)",
            line=dict(color="#a78bfa", width=2),
            hovertemplate="Frame %{x}<br>Spacing: %{y:.1f}ft<extra></extra>",
        ))
    if "convex_hull_area" in df.columns:
        # Normalize hull area for overlay
        hull = df["convex_hull_area"]
        if hull.max() > 0:
            hull_norm = hull / hull.max() * df["avg_inter_player_dist"].max()
            fig.add_trace(go.Scatter(
                x=df["frame_number"], y=hull_norm,
                mode="lines", name="Hull Area (normalized)",
                line=dict(color="#34d399", width=1.5, dash="dot"),
            ))

    fig.update_layout(
        title=dict(text="Team Spacing Over Time", font=dict(size=15, color="white")),
        paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT,
        xaxis=dict(title="Frame", gridcolor="#333", color="white"),
        yaxis=dict(title="Feet", gridcolor="#333", color="white"),
        height=260, margin=dict(l=50, r=20, t=40, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0.5)"),
    )
    return fig


def play_type_chart(plays: list) -> go.Figure:
    """Bar chart of detected play types by frequency."""
    if not plays:
        fig = go.Figure()
        fig.update_layout(title="Play Type Breakdown",
                          paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT, height=320)
        return fig

    df = pd.DataFrame(plays)
    counts = df["play_type"].value_counts().reset_index()
    counts.columns = ["play_type", "count"]
    counts = counts.sort_values("count", ascending=True)

    fig = go.Figure(go.Bar(
        x=counts["count"], y=counts["play_type"],
        orientation="h",
        marker=dict(
            color=counts["count"],
            colorscale="Teal",
            showscale=False,
        ),
        hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Play Type Breakdown", font=dict(size=15, color="white")),
        paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT,
        xaxis=dict(title="Count", gridcolor="#333", color="white"),
        yaxis=dict(color="white"),
        height=max(280, len(counts) * 35 + 80),
        margin=dict(l=140, r=20, t=40, b=40),
    )
    return fig


def defensive_scheme_chart(schemes: list) -> go.Figure:
    """Pie chart of defensive scheme distribution."""
    if not schemes:
        fig = go.Figure()
        fig.update_layout(title="Defensive Schemes",
                          paper_bgcolor=_DARK, font=_FONT, height=300)
        return fig

    df = pd.DataFrame(schemes)
    counts = df["scheme_label"].value_counts()

    fig = go.Figure(go.Pie(
        labels=counts.index.tolist(),
        values=counts.values.tolist(),
        hole=0.4,
        marker=dict(colors=["#3b82f6", "#f59e0b", "#10b981", "#ef4444"]),
        textfont=dict(color="white"),
        hovertemplate="<b>%{label}</b><br>%{value} possessions (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text="Defensive Scheme Distribution", font=dict(size=15, color="white")),
        paper_bgcolor=_DARK, font=_FONT,
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="white")),
        height=300, margin=dict(l=20, r=20, t=40, b=20),
    )
    return fig


def momentum_chart(flow: list) -> go.Figure:
    """Momentum index and scoring run probability over time."""
    if not flow:
        fig = go.Figure()
        fig.update_layout(title="Game Momentum",
                          paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT, height=260)
        return fig

    df = pd.DataFrame(flow).sort_values("frame_number")
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["frame_number"], y=df["momentum_index"],
        mode="lines", name="Momentum",
        line=dict(color="#f59e0b", width=2),
        fill="tozeroy", fillcolor="rgba(245,158,11,0.1)",
        hovertemplate="Frame %{x}<br>Momentum: %{y:.3f}<extra></extra>",
    ))
    if "scoring_run_probability" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["frame_number"], y=df["scoring_run_probability"],
            mode="lines", name="Scoring Run %",
            line=dict(color="#ef4444", width=1.5, dash="dash"),
            hovertemplate="Frame %{x}<br>Scoring Run: %{y:.1%}<extra></extra>",
        ))

    fig.update_layout(
        title=dict(text="Game Momentum", font=dict(size=15, color="white")),
        paper_bgcolor=_DARK, plot_bgcolor=_CARD, font=_FONT,
        xaxis=dict(title="Frame", gridcolor="#333", color="white"),
        yaxis=dict(title="Index", gridcolor="#333", color="white"),
        height=260, margin=dict(l=50, r=20, t=40, b=40),
        legend=dict(bgcolor="rgba(0,0,0,0.5)"),
    )
    return fig


def pressure_heatmap(points: list) -> go.Figure:
    """Defensive pressure heatmap (inverse nearest-defender distance)."""
    if not points:
        fig = go.Figure()
        return _court_layout(fig, "Defensive Pressure Map")

    df = pd.DataFrame(points)
    # Pressure = 1 / distance (closer defender = higher pressure)
    df["pressure"] = 1.0 / df["nearest_defender_dist"].clip(lower=0.5)

    fig = go.Figure(go.Histogram2dContour(
        x=df["x"], y=df["y"], z=df["pressure"],
        colorscale="Hot", histfunc="avg",
        nbinsx=47, nbinsy=25,
        showscale=True,
        colorbar=dict(title="Pressure", tickfont=dict(color="white")),
        hoverinfo="skip",
    ))
    return _court_layout(fig, "Defensive Pressure Map")
