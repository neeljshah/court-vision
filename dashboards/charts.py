"""Plotly figure factories for the NBA AI dashboard."""
import math
import plotly.graph_objects as go
import plotly.express as px


# NBA half-court dimensions in normalised pixel space (0-940 x 0-500)
COURT_W, COURT_H = 940, 500


def _draw_court(fig: go.Figure) -> go.Figure:
    """Add NBA half-court lines to a Plotly figure."""
    shapes = [
        # Outer boundary
        dict(type="rect", x0=0, y0=0, x1=COURT_W, y1=COURT_H,
             line=dict(color="white", width=2), fillcolor="rgba(0,0,0,0)"),
        # Paint (lane) – roughly 190px wide, 160px deep
        dict(type="rect", x0=375, y0=0, x1=565, y1=160,
             line=dict(color="white", width=2), fillcolor="rgba(0,0,0,0)"),
        # Free-throw circle
        dict(type="circle", x0=420, y0=110, x1=520, y1=210,
             line=dict(color="white", width=2), fillcolor="rgba(0,0,0,0)"),
        # Basket
        dict(type="circle", x0=455, y0=30, x1=485, y1=60,
             line=dict(color="orange", width=3), fillcolor="rgba(0,0,0,0)"),
        # Backboard
        dict(type="line", x0=440, y0=20, x1=500, y1=20,
             line=dict(color="white", width=3)),
        # Half-court line
        dict(type="line", x0=0, y0=COURT_H, x1=COURT_W, y1=COURT_H,
             line=dict(color="white", width=2)),
    ]
    # Three-point arc (approximate semicircle)
    theta = [math.radians(a) for a in range(0, 181)]
    arc_x = [470 + 220 * math.cos(t) for t in theta]
    arc_y = [45 + 220 * math.sin(t) for t in theta]
    fig.add_trace(go.Scatter(
        x=arc_x, y=arc_y, mode="lines",
        line=dict(color="white", width=2),
        showlegend=False, hoverinfo="skip",
    ))
    fig.update_layout(shapes=shapes)
    return fig


def shot_chart(shots: list[dict]) -> go.Figure:
    """
    Shot chart with court diagram.

    Each dict in `shots`: {x, y, made (bool), player_id, zone}
    """
    made = [s for s in shots if s.get("made")]
    missed = [s for s in shots if not s.get("made")]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[s["x"] for s in made], y=[s["y"] for s in made],
        mode="markers", name="Made",
        marker=dict(color="lime", size=10, symbol="circle",
                    line=dict(color="white", width=1)),
        hovertemplate="Made<br>(%{x}, %{y})<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[s["x"] for s in missed], y=[s["y"] for s in missed],
        mode="markers", name="Missed",
        marker=dict(color="red", size=10, symbol="x",
                    line=dict(color="white", width=1)),
        hovertemplate="Missed<br>(%{x}, %{y})<extra></extra>",
    ))
    fig = _draw_court(fig)
    fig.update_layout(
        title="Shot Chart",
        paper_bgcolor="#1a1a2e", plot_bgcolor="#2d5016",
        font=dict(color="white"),
        xaxis=dict(range=[0, COURT_W], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[0, COURT_H], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
        height=500,
    )
    return fig


def defensive_pressure_heatmap(frames: list[dict]) -> go.Figure:
    """
    Heatmap of defensive pressure across court.

    Each dict in `frames`: {x, y, pressure} where pressure is nearest-defender distance (lower = more pressure).
    """
    if not frames:
        fig = go.Figure()
        fig.update_layout(title="Defensive Pressure (no data)",
                          paper_bgcolor="#1a1a2e", font=dict(color="white"))
        return fig

    fig = go.Figure(go.Histogram2dContour(
        x=[f["x"] for f in frames],
        y=[f["y"] for f in frames],
        z=[1 / max(f.get("pressure", 1), 1) for f in frames],  # invert: low dist = high pressure
        colorscale="Hot",
        reversescale=True,
        showscale=True,
        contours=dict(showlabels=False),
        line=dict(width=0),
        hoverinfo="skip",
    ))
    fig = _draw_court(fig)
    fig.update_layout(
        title="Defensive Pressure Map",
        paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e",
        font=dict(color="white"),
        xaxis=dict(range=[0, COURT_W], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[0, COURT_H], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
        height=500,
    )
    return fig


def tracking_overlay(tracks: list[dict]) -> go.Figure:
    """
    Player movement paths overlaid on court.

    Each dict: {track_id, x, y, frame_number}
    """
    fig = go.Figure()
    if tracks:
        import pandas as pd
        df = pd.DataFrame(tracks).sort_values("frame_number")
        for tid, grp in df.groupby("track_id"):
            fig.add_trace(go.Scatter(
                x=grp["x"], y=grp["y"],
                mode="lines+markers",
                name=f"Player {tid}",
                line=dict(width=2),
                marker=dict(size=5),
                hovertemplate=f"Player {tid}<br>Frame %{{text}}<extra></extra>",
                text=grp["frame_number"].astype(str),
            ))
    fig = _draw_court(fig)
    fig.update_layout(
        title="Player Tracking Paths",
        paper_bgcolor="#1a1a2e", plot_bgcolor="#2d5016",
        font=dict(color="white"),
        xaxis=dict(range=[0, COURT_W], showgrid=False, zeroline=False, visible=False),
        yaxis=dict(range=[0, COURT_H], showgrid=False, zeroline=False, visible=False,
                   scaleanchor="x"),
        height=500,
    )
    return fig


def lineup_impact_chart(lineups: list[dict]) -> go.Figure:
    """
    Horizontal bar chart of lineup net rating and EPA.

    Each dict: {label (str), net_rating (float), epa (float)}
    """
    if not lineups:
        fig = go.Figure()
        fig.update_layout(title="Lineup Impact (no data)",
                          paper_bgcolor="#1a1a2e", font=dict(color="white"))
        return fig

    labels = [l["label"] for l in lineups]
    net_ratings = [l.get("net_rating", 0) for l in lineups]
    epas = [l.get("epa", 0) for l in lineups]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=net_ratings, orientation="h",
        name="Net Rating", marker_color="steelblue",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=epas, orientation="h",
        name="EPA", marker_color="darkorange",
    ))
    fig.update_layout(
        title="Lineup Impact: Net Rating vs EPA",
        barmode="group",
        paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e",
        font=dict(color="white"),
        xaxis=dict(gridcolor="#333"),
        yaxis=dict(gridcolor="#333"),
        height=max(300, len(lineups) * 60),
    )
    return fig
