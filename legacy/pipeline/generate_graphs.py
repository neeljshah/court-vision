"""
Layer 3 — Static Graph Generation.

Reads from data/{game_id}/*.parquet and writes PNGs to outputs/graphs/{game_id}/.

Graphs generated:
  game_summary.png       — key metric card
  shot_chart.png         — made/missed on court
  player_heatmap.png     — position density
  ball_trajectory.png    — ball path colored by frame
  drive_map.png          — drive start positions
  spacing_timeline.png   — avg spacing + hull area over time
  momentum_timeline.png  — momentum index + scoring run %
  defensive_scheme.png   — scheme distribution pie
  player_distance.png    — distance covered per player

All graphs cached — skips existing files unless --force is passed.

Usage:
  python -m pipeline.generate_graphs --game-id <uuid>
  python -m pipeline.generate_graphs --game-id <uuid> --force
"""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATA_DIR   = Path(__file__).parent.parent / "data"
GRAPHS_DIR = Path(__file__).parent.parent / "outputs" / "graphs"

_BG     = "#0f1117"
_CARD   = "#1c1f2e"
_COURT  = "#c68642"
_WHITE  = "white"
_GRAY   = "#9ca3af"
_W, _H  = 94, 50


# ── Court drawing ──────────────────────────────────────────────────────────────

def _draw_court(ax: plt.Axes) -> None:
    ax.set_facecolor(_COURT)
    lc, lw = _WHITE, 1.5

    def line(x0, y0, x1, y1):
        ax.plot([x0, x1], [y0, y1], color=lc, lw=lw)

    def rect(x, y, w, h):
        ax.add_patch(mpatches.Rectangle((x, y), w, h, fill=False, ec=lc, lw=lw))

    def circle(cx, cy, r, **kw):
        ax.add_patch(mpatches.Circle((cx, cy), r, fill=False, ec=lc, lw=lw, **kw))

    rect(0, 0, _W, _H)
    line(47, 0, 47, _H)
    circle(47, 25, 6)

    for bx, sign in [(4.75, 1), (89.25, -1)]:
        # Paint
        px = 0 if sign == 1 else 75
        rect(px, 17, 19, 16)
        line(px + 19 * (1 if sign == 1 else -1) + (0 if sign == 1 else 94 - 75 - 19), 17,
             px + 19 * (1 if sign == 1 else -1) + (0 if sign == 1 else 94 - 75 - 19), 33)
        circle(bx + sign * 14.25, 25, 6)  # FT arc center
        # Corner 3
        c3x0 = 0 if sign == 1 else 80
        c3x1 = 14 if sign == 1 else 94
        line(c3x0, 3, c3x1, 3)
        line(c3x0, 47, c3x1, 47)
        # Basket
        circle(bx, 25, 0.75, ec="orange")
        # 3pt arc
        theta = np.linspace(np.radians(22), np.radians(158), 120)
        ax.plot(bx + sign * 23.75 * np.cos(theta),
                25 + 23.75 * np.sin(theta), color=lc, lw=lw)

    ax.set_xlim(-1, _W + 1)
    ax.set_ylim(-1, _H + 1)
    ax.set_aspect("equal")
    ax.axis("off")


def _fig(w=10, h=6) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(w, h), facecolor=_BG)
    return fig, ax


def _save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path, dpi=120, bbox_inches="tight", facecolor=_BG)
    plt.close(fig)


# ── Graph generators ──────────────────────────────────────────────────────────

def game_summary(summary: dict, out: Path) -> None:
    fig, ax = _fig(9, 4)
    ax.set_facecolor(_BG)
    ax.axis("off")

    home = summary.get("home_team", "Home")
    away = summary.get("away_team", "Away")
    ax.text(0.5, 0.93, f"{home}  vs  {away}",
            transform=ax.transAxes, ha="center",
            color=_WHITE, fontsize=20, fontweight="bold")
    ax.text(0.5, 0.80, f"{summary.get('game_date','')}  ·  {summary.get('season','')}",
            transform=ax.transAxes, ha="center", color=_GRAY, fontsize=11)

    metrics = [
        ("Frames",       summary.get("total_frames", 0)),
        ("Detections",   summary.get("total_detections", 0)),
        ("Shots",        summary.get("total_shots", 0)),
        ("Possessions",  summary.get("total_possessions", 0)),
        ("Drives",       summary.get("total_drives", 0)),
        ("FG%",          f"{summary.get('fg_pct', 0):.1%}"),
    ]
    for i, (label, val) in enumerate(metrics):
        x = 0.10 + (i % 3) * 0.30
        y = 0.52 if i < 3 else 0.20
        ax.text(x, y + 0.12, str(val), transform=ax.transAxes,
                color="#60a5fa", fontsize=22, fontweight="bold", ha="center")
        ax.text(x, y,         label,    transform=ax.transAxes,
                color=_GRAY, fontsize=9, ha="center")

    _save(fig, out / "game_summary.png")


def shot_chart(events: pd.DataFrame, out: Path) -> None:
    shots = events[events["event_category"] == "shot"].dropna(subset=["x", "y"])
    fig, ax = _fig()
    _draw_court(ax)

    made   = shots[shots["made"] == True]
    missed = shots[shots["made"] == False]
    unk    = shots[~shots["made"].isin([True, False])]

    if not made.empty:
        ax.scatter(made["x"], made["y"], c="lime",    s=80, marker="o",
                   edgecolors=_WHITE, lw=0.5, label="Made",    zorder=3)
    if not missed.empty:
        ax.scatter(missed["x"], missed["y"], c="#ff4444", s=80, marker="x",
                   linewidths=2, label="Missed",  zorder=3)
    if not unk.empty:
        ax.scatter(unk["x"], unk["y"], c=_WHITE, s=60, marker="o",
                   facecolors="none", lw=1.5, label="Unknown", zorder=3)

    ax.legend(loc="upper right", facecolor=_CARD, labelcolor=_WHITE,
              framealpha=0.9, fontsize=9)
    ax.set_title("Shot Chart", color=_WHITE, fontsize=14, pad=10)
    _save(fig, out / "shot_chart.png")


def player_heatmap(frames: pd.DataFrame, out: Path) -> None:
    players = frames[(frames["object_type"] == "player") &
                     frames["x"].notna() & frames["y"].notna()]
    fig, ax = _fig()
    _draw_court(ax)
    if not players.empty:
        ax.hexbin(players["x"], players["y"], gridsize=30, cmap="hot",
                  alpha=0.65, mincnt=1, extent=(0, _W, 0, _H))
    ax.set_title("Player Position Heatmap", color=_WHITE, fontsize=14, pad=10)
    _save(fig, out / "player_heatmap.png")


def ball_trajectory(frames: pd.DataFrame, out: Path) -> None:
    ball = frames[frames["object_type"] == "ball"].sort_values("frame_number")
    fig, ax = _fig()
    _draw_court(ax)
    if not ball.empty:
        sc = ax.scatter(ball["x"], ball["y"], c=ball["frame_number"],
                        cmap="plasma", s=6, alpha=0.7, zorder=3)
        cbar = fig.colorbar(sc, ax=ax, fraction=0.025, pad=0.02)
        cbar.set_label("Frame", color=_WHITE, fontsize=9)
        cbar.ax.yaxis.set_tick_params(color=_WHITE)
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color=_WHITE)
    ax.set_title("Ball Trajectory", color=_WHITE, fontsize=14, pad=10)
    _save(fig, out / "ball_trajectory.png")


def drive_map(events: pd.DataFrame, frames: pd.DataFrame, out: Path) -> None:
    drives = events[events["event_category"] == "drive"].copy()
    fig, ax = _fig()
    _draw_court(ax)

    # Join drive start position from frame data if not already present
    if "x" not in drives.columns and not frames.empty and "frame_number" in drives.columns:
        ball_pos = frames[frames["object_type"] == "player"][
            ["track_id", "frame_number", "x", "y"]
        ]
        drives = drives.merge(ball_pos, on=["track_id", "frame_number"], how="left")

    if not drives.empty and "x" in drives.columns:
        beaten  = drives[drives["defender_beaten"] == True]
        stopped = drives[drives["defender_beaten"] != True]
        if not beaten.empty:
            ax.scatter(beaten["x"],  beaten["y"],  c="lime",    s=100, marker=">",
                       label="Beaten",  zorder=3, edgecolors=_WHITE, lw=0.5)
        if not stopped.empty:
            ax.scatter(stopped["x"], stopped["y"], c="#ff9900", s=80,  marker=">",
                       label="Stopped", zorder=3, edgecolors=_WHITE, lw=0.5)
        ax.legend(loc="upper right", facecolor=_CARD, labelcolor=_WHITE, fontsize=9)

    ax.set_title("Drive Map", color=_WHITE, fontsize=14, pad=10)
    _save(fig, out / "drive_map.png")


def spacing_timeline(data_dir: Path, out: Path) -> None:
    path = data_dir / "spacing.parquet"
    if not path.exists():
        return
    df = pd.read_parquet(path).sort_values("frame_number")
    fig, ax = _fig(10, 4)
    ax.set_facecolor(_CARD)

    if "avg_inter_player_dist" in df.columns:
        ax.plot(df["frame_number"], df["avg_inter_player_dist"],
                color="#a78bfa", lw=1.5, label="Avg Spacing (ft)")
        ax.fill_between(df["frame_number"], df["avg_inter_player_dist"],
                        alpha=0.08, color="#a78bfa")

    if "convex_hull_area" in df.columns and df["convex_hull_area"].max() > 0:
        ax2 = ax.twinx()
        ax2.plot(df["frame_number"], df["convex_hull_area"],
                 color="#34d399", lw=1.2, ls="--", alpha=0.8, label="Hull Area")
        ax2.set_ylabel("Hull Area (sq ft)", color="#34d399", fontsize=9)
        ax2.tick_params(colors="#34d399")

    ax.set_xlabel("Frame", color=_WHITE, fontsize=9)
    ax.set_ylabel("Feet", color=_WHITE, fontsize=9)
    ax.tick_params(colors=_WHITE)
    ax.set_title("Team Spacing Over Time", color=_WHITE, fontsize=14, pad=10)
    ax.legend(loc="upper left", facecolor=_CARD, labelcolor=_WHITE, fontsize=9)
    _save(fig, out / "spacing_timeline.png")


def momentum_timeline(data_dir: Path, out: Path) -> None:
    path = data_dir / "game_flow.parquet"
    if not path.exists():
        return
    df = pd.read_parquet(path).sort_values("frame_number")
    fig, ax = _fig(10, 4)
    ax.set_facecolor(_CARD)

    if "momentum_index" in df.columns:
        ax.plot(df["frame_number"], df["momentum_index"],
                color="#f59e0b", lw=2, label="Momentum")
        ax.fill_between(df["frame_number"], df["momentum_index"],
                        alpha=0.10, color="#f59e0b")
    if "scoring_run_probability" in df.columns:
        ax.plot(df["frame_number"], df["scoring_run_probability"],
                color="#ef4444", lw=1.5, ls="--", label="Scoring Run %")
    if "comeback_probability" in df.columns:
        ax.plot(df["frame_number"], df["comeback_probability"],
                color="#60a5fa", lw=1.2, ls=":", alpha=0.8, label="Comeback %")

    ax.set_xlabel("Frame", color=_WHITE, fontsize=9)
    ax.set_ylabel("Value", color=_WHITE, fontsize=9)
    ax.tick_params(colors=_WHITE)
    ax.set_title("Game Momentum", color=_WHITE, fontsize=14, pad=10)
    ax.legend(loc="upper left", facecolor=_CARD, labelcolor=_WHITE, fontsize=9)
    _save(fig, out / "momentum_timeline.png")


def defensive_scheme_pie(data_dir: Path, out: Path) -> None:
    path = data_dir / "defensive_schemes.parquet"
    if not path.exists():
        return
    df = pd.read_parquet(path)
    if "scheme_label" not in df.columns or df.empty:
        return
    counts = df["scheme_label"].value_counts()
    fig, ax = _fig(7, 5)
    ax.set_facecolor(_BG)
    colors = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"]
    wedges, texts, autotexts = ax.pie(
        counts.values, labels=counts.index, autopct="%1.0f%%",
        colors=colors[:len(counts)],
        wedgeprops=dict(edgecolor=_BG, linewidth=2),
        textprops=dict(color=_WHITE),
    )
    for at in autotexts:
        at.set_fontsize(9)
    ax.set_title("Defensive Scheme Distribution", color=_WHITE, fontsize=14, pad=10)
    _save(fig, out / "defensive_scheme.png")


def player_distance(player_stats: pd.DataFrame, out: Path) -> None:
    if player_stats.empty or "distance_ft" not in player_stats.columns:
        return
    df = player_stats.dropna(subset=["distance_ft"]).sort_values("distance_ft", ascending=True)
    if df.empty:
        return
    fig, ax = _fig(8, max(4, len(df) * 0.4 + 1))
    ax.set_facecolor(_CARD)

    colors = {"team_a": "#3b82f6", "team_b": "#ef4444", "ref": _GRAY}
    bar_colors = [colors.get(str(t), "#60a5fa") for t in df["team"]]

    ax.barh(df["track_id"].astype(str), df["distance_ft"],
            color=bar_colors, edgecolor=_BG, linewidth=0.5)
    ax.set_xlabel("Distance (ft)", color=_WHITE, fontsize=9)
    ax.set_ylabel("Track ID", color=_WHITE, fontsize=9)
    ax.tick_params(colors=_WHITE)
    ax.set_title("Distance Covered by Player", color=_WHITE, fontsize=14, pad=10)

    handles = [mpatches.Patch(color=c, label=t) for t, c in colors.items()]
    ax.legend(handles=handles, facecolor=_CARD, labelcolor=_WHITE, fontsize=9)
    _save(fig, out / "player_distance.png")


# ── Orchestrator ───────────────────────────────────────────────────────────────

def generate_all(game_id: str, force: bool = False) -> Path:
    data_dir = DATA_DIR / game_id
    out_dir  = GRAPHS_DIR / game_id
    out_dir.mkdir(parents=True, exist_ok=True)

    frames   = _load(data_dir / "frame_data.parquet")
    events   = _load(data_dir / "events.parquet")
    p_stats  = _load(data_dir / "player_stats.parquet")
    summary  = json.loads((data_dir / "game_summary.json").read_text()) \
               if (data_dir / "game_summary.json").exists() else {}

    tasks = [
        ("game_summary.png",      lambda: game_summary(summary, out_dir)),
        ("shot_chart.png",        lambda: shot_chart(events, out_dir)),
        ("player_heatmap.png",    lambda: player_heatmap(frames, out_dir)),
        ("ball_trajectory.png",   lambda: ball_trajectory(frames, out_dir)),
        ("drive_map.png",         lambda: drive_map(events, frames, out_dir)),
        ("spacing_timeline.png",  lambda: spacing_timeline(data_dir, out_dir)),
        ("momentum_timeline.png", lambda: momentum_timeline(data_dir, out_dir)),
        ("defensive_scheme.png",  lambda: defensive_scheme_pie(data_dir, out_dir)),
        ("player_distance.png",   lambda: player_distance(p_stats, out_dir)),
    ]

    for fname, fn in tasks:
        path = out_dir / fname
        if force or not path.exists():
            try:
                fn()
                print(f"[graphs]   {fname}")
            except Exception as e:
                print(f"[graphs]   {fname} — skipped ({e})")

    print(f"[graphs] Done → {out_dir}")
    return out_dir


def _load(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Generate static graphs for a game")
    p.add_argument("--game-id", required=True)
    p.add_argument("--force", action="store_true", help="Regenerate even if cached")
    args = p.parse_args()
    generate_all(args.game_id, force=args.force)
