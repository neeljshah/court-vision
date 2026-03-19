"""Conversational AI interface backed by Claude + live DB + models."""
import os
import json
import anthropic

from tracking.database import get_connection


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


# ── DB query helpers ──────────────────────────────────────────────────────────

def _query_db(sql: str, params: tuple = ()) -> list[dict]:
    """Run a read-only SQL query and return rows as dicts."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        return [{"error": str(e)}]


def _get_game_summary(game_id: str | None) -> dict:
    if not game_id:
        return {"note": "No game selected"}
    rows = _query_db(
        "SELECT home_team, away_team, game_date FROM games WHERE id = %s", (game_id,)
    )
    return rows[0] if rows else {"note": "Game not found"}


def _get_shot_stats(game_id: str | None) -> dict:
    if not game_id:
        return {"total": 0, "made": 0, "fg_pct": 0}
    rows = _query_db(
        "SELECT COUNT(*) as total, SUM(CASE WHEN made THEN 1 ELSE 0 END) as made FROM shot_logs WHERE game_id = %s",
        (game_id,),
    )
    r = rows[0] if rows else {}
    total = r.get("total") or 0
    made = r.get("made") or 0
    return {"total": total, "made": made, "fg_pct": round(made / total, 3) if total else 0}


def _get_momentum_snapshots(game_id: str | None) -> list[dict]:
    if not game_id:
        return []
    return _query_db(
        "SELECT segment_number, scoring_run, possession_streak, swing_point FROM momentum_snapshots WHERE game_id = %s ORDER BY segment_number",
        (game_id,),
    )


def _predict_shot(defender_dist: float, shot_angle: float, court_zone: str, fatigue_proxy: float = 0.5) -> float:
    try:
        from models.shot_probability import ShotProbabilityModel
        model = ShotProbabilityModel.load("shot_probability")
        return model.predict({"defender_dist": defender_dist, "shot_angle": shot_angle,
                              "fatigue_proxy": fatigue_proxy, "court_zone": court_zone})
    except Exception as e:
        return -1.0


def _predict_win(convex_hull_area: float, avg_dist: float, scoring_run: int = 0,
                 possession_streak: int = 0, swing_point: int = 0) -> float:
    try:
        from models.win_probability import WinProbabilityModel
        model = WinProbabilityModel.load("win_probability")
        return model.predict({"convex_hull_area": convex_hull_area, "avg_inter_player_dist": avg_dist,
                              "scoring_run": scoring_run, "possession_streak": possession_streak,
                              "swing_point": swing_point})
    except Exception as e:
        return -1.0


def _get_player_impact_rankings(game_id: str | None) -> list[dict]:
    if not game_id:
        return []
    rows = _query_db("""
        SELECT player_id, COUNT(*) as shots,
               SUM(CASE WHEN made THEN 1 ELSE 0 END) as made_shots
        FROM shot_logs WHERE game_id = %s
        GROUP BY player_id ORDER BY made_shots DESC LIMIT 10
    """, (game_id,))
    return rows


# ── Tool definitions for Claude ───────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_game_summary",
        "description": "Get basic game info (teams, date) for the selected game.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_shot_stats",
        "description": "Get total shots, made shots, and FG% for the selected game.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_momentum_snapshots",
        "description": "Get per-segment momentum data: scoring runs, possession streaks, swing points.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_player_impact_rankings",
        "description": "Get player shot stats (shots taken, makes) ranked by performance.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "predict_shot_probability",
        "description": "Predict the probability a shot goes in given context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "defender_dist": {"type": "number", "description": "Distance to nearest defender in pixels"},
                "shot_angle": {"type": "number", "description": "Shot angle in degrees"},
                "court_zone": {"type": "string", "enum": ["paint", "midrange", "three"]},
                "fatigue_proxy": {"type": "number", "description": "0=fresh, 1=exhausted"},
            },
            "required": ["defender_dist", "shot_angle", "court_zone"],
        },
    },
    {
        "name": "predict_win_probability",
        "description": "Predict current win probability given game state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "convex_hull_area": {"type": "number"},
                "avg_inter_player_dist": {"type": "number"},
                "scoring_run": {"type": "integer"},
                "possession_streak": {"type": "integer"},
                "swing_point": {"type": "integer", "enum": [0, 1]},
            },
            "required": ["convex_hull_area", "avg_inter_player_dist"],
        },
    },
    {
        "name": "run_sql",
        "description": "Run a custom read-only SQL query against the NBA database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SELECT query only"},
            },
            "required": ["sql"],
        },
    },
]


def _dispatch_tool(name: str, inputs: dict, game_id: str | None) -> str:
    if name == "get_game_summary":
        return json.dumps(_get_game_summary(game_id))
    if name == "get_shot_stats":
        return json.dumps(_get_shot_stats(game_id))
    if name == "get_momentum_snapshots":
        return json.dumps(_get_momentum_snapshots(game_id))
    if name == "get_player_impact_rankings":
        return json.dumps(_get_player_impact_rankings(game_id))
    if name == "predict_shot_probability":
        prob = _predict_shot(
            defender_dist=inputs["defender_dist"],
            shot_angle=inputs["shot_angle"],
            court_zone=inputs["court_zone"],
            fatigue_proxy=inputs.get("fatigue_proxy", 0.5),
        )
        return json.dumps({"shot_probability": prob})
    if name == "predict_win_probability":
        prob = _predict_win(
            convex_hull_area=inputs["convex_hull_area"],
            avg_dist=inputs["avg_inter_player_dist"],
            scoring_run=inputs.get("scoring_run", 0),
            possession_streak=inputs.get("possession_streak", 0),
            swing_point=inputs.get("swing_point", 0),
        )
        return json.dumps({"win_probability": prob})
    if name == "run_sql":
        sql = inputs.get("sql", "")
        if not sql.strip().upper().startswith("SELECT"):
            return json.dumps({"error": "Only SELECT queries are allowed"})
        return json.dumps(_query_db(sql))
    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Main entry point ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an NBA analytics AI assistant with access to a live basketball tracking database and ML prediction models. You answer questions about games, players, shot quality, win probability, and momentum.

Be concise and data-driven. When you have numbers, cite them. When data is unavailable, say so clearly.

You have tools to query the database and run model predictions. Use them to answer questions accurately."""


def answer(question: str, game_id: str | None = None) -> str:
    """Answer a natural-language question using Claude + tools."""
    client = _get_client()
    messages = [{"role": "user", "content": question}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "No response generated."

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _dispatch_tool(block.name, block.input, game_id)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        return "Unexpected response from model."
