"""
Layer 4 — Lightweight Flask Dashboard.

Pages:
  /                    — game list
  /game/<game_id>      — full analytics dashboard (loads cached PNGs)
  /run/<game_id>       — trigger export + graph generation, then redirect

Static files served from outputs/graphs/<game_id>/.

Usage:
  python -m frontend.app
  python -m frontend.app --port 5050
"""
import argparse
import json
from pathlib import Path

from flask import Flask, abort, redirect, render_template, send_file, url_for

ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
GRAPHS_DIR = ROOT / "outputs" / "graphs"

app = Flask(__name__, template_folder="templates")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _all_games() -> list[dict]:
    """Return list of processed games sorted by date desc."""
    games = []
    for summary_path in sorted(DATA_DIR.glob("*/game_summary.json"), reverse=True):
        try:
            info = json.loads(summary_path.read_text())
            info["has_graphs"] = (GRAPHS_DIR / info["game_id"] / "shot_chart.png").exists()
            games.append(info)
        except Exception:
            pass
    return games


def _summary(game_id: str) -> dict:
    path = DATA_DIR / game_id / "game_summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _graphs(game_id: str) -> list[dict]:
    """Return list of available graph metadata for a game."""
    graph_dir = GRAPHS_DIR / game_id
    if not graph_dir.exists():
        return []

    _META = {
        "game_summary.png":      ("Game Overview",          "overview"),
        "shot_chart.png":        ("Shot Chart",             "shots"),
        "player_heatmap.png":    ("Player Heatmap",         "movement"),
        "ball_trajectory.png":   ("Ball Trajectory",        "movement"),
        "drive_map.png":         ("Drive Map",              "plays"),
        "spacing_timeline.png":  ("Team Spacing",           "team"),
        "momentum_timeline.png": ("Game Momentum",          "team"),
        "defensive_scheme.png":  ("Defensive Schemes",      "defense"),
        "player_distance.png":   ("Player Distance",        "movement"),
    }

    return [
        {"file": fname, "title": title, "tab": tab}
        for fname, (title, tab) in _META.items()
        if (graph_dir / fname).exists()
    ]


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return render_template("index.html", games=_all_games())


@app.get("/game/<game_id>")
def game(game_id: str):
    summary = _summary(game_id)
    if not summary:
        abort(404, f"Game {game_id} not found. Run export first.")
    graphs = _graphs(game_id)
    tabs = list(dict.fromkeys(g["tab"] for g in graphs))
    return render_template("game.html", summary=summary, graphs=graphs, tabs=tabs)


@app.get("/graph/<game_id>/<filename>")
def serve_graph(game_id: str, filename: str):
    path = GRAPHS_DIR / game_id / filename
    if not path.exists() or path.suffix not in (".png", ".svg"):
        abort(404)
    return send_file(path, mimetype="image/png")


@app.post("/run/<game_id>")
def run_pipeline(game_id: str):
    """Trigger export + graph generation for an already-tracked game."""
    from pipeline.export_data import export_game
    from pipeline.generate_graphs import generate_all
    try:
        export_game(game_id)
        generate_all(game_id)
    except Exception as e:
        abort(500, str(e))
    return redirect(url_for("game", game_id=game_id))


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=5001)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)
