"""scripts.platformkit.mcp_server.sports_predictor_server -- stdio MCP server SKELETON.

Exposes the system's READ-ONLY calibrated predictor over the Model Context Protocol so an
MCP client (e.g. an LLM host) can REQUEST predictions -- but the LLM NEVER authors a number.
Every tool SHELLS OUT to the existing, validated CLI
(`python -m scripts.platformkit.predict_matchup` / `recal_report`) and returns that process's
own JSON/text verbatim. The model only chooses the matchup/state; the deterministic predictor
computes every figure. Honest framing only: pregame MATCHES the devigged close (calibration,
not a $ edge); in-game ADDS the realized state. No $ edge is ever claimed here.

Tools:
  * predict_pregame(sport, home, away)  -> shells predict_matchup --json
  * predict_ingame(sport, state)        -> shells predict_matchup with in-game flags from state
  * calibration_report(sport)           -> shells recal_report (per-sport slice)
Resource:
  * edge_map://<sport>                  -> read-only vault/_Edge_Maps text, IF present

SKELETON: the `mcp` SDK is optional. If it is not installed the module still PARSES and its
helpers stay unit-testable; only `serve()` requires `mcp`. Nothing is wired into the live
session -- this file is additive and inert until a human runs it / adds it to .mcp.json.

INVARIANTS: read-only; never authors numbers; never edits src/ or kernel/; <=300 LOC; ASCII
only; no secrets. Shells the EXISTING predictor; degrades cleanly when corpora are absent.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

# Repo root = .../nba-ai-system (this file is scripts/platformkit/mcp_server/<here>).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PREDICT_MOD = "scripts.platformkit.predict_matchup"
_RECAL_MOD = "scripts.platformkit.recal_report"
_SPORTS = ("nba", "mlb", "soccer", "tennis")
_ALIASES = {"basketball_nba": "nba"}
# ponytail: process-local cap on concurrent heavy subprocess launches -- same
# "one heavy python at a time" rule as winprob_dispatch.py's gate.
_SUBPROC_GATE = threading.BoundedSemaphore(1)
# Canonical (current) edge-map location; legacy copy lives under _vault_legacy_archive.
_EDGE_MAP_DIR = _REPO_ROOT / "vault" / "_Edge_Maps"

# Guarded optional import: the SDK is not required for the helpers below to work / be tested.
try:  # pragma: no cover - import shape only
    import mcp  # noqa: F401
    from mcp.server import Server  # type: ignore
    from mcp.server.stdio import stdio_server  # type: ignore
    from mcp.types import Resource, TextContent, Tool  # type: ignore

    _HAVE_MCP = True
except Exception:  # ImportError or partial SDK -- skeleton still parses.
    _HAVE_MCP = False


# ---------------------------------------------------------------------------
# Pure helpers (no SDK, fully testable)
# ---------------------------------------------------------------------------
def _norm_sport(sport: str) -> str:
    s = (sport or "").strip().lower()
    return _ALIASES.get(s, s)


def _run_cli(args: List[str]) -> Dict[str, Any]:
    """Run a repo CLI module read-only and capture stdout. NEVER raises to the caller.

    Returns {"ok": bool, "stdout": str, "stderr": str, "returncode": int}. The predictor
    CLIs exit 0 and print an 'unavailable' note when corpora are absent, so a clean clone
    degrades to a benign message rather than an error.
    """
    cmd = [sys.executable, "-m", *args]
    try:
        with _SUBPROC_GATE:
            proc = subprocess.run(
                cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=600,
            )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "returncode": proc.returncode,
        }
    except Exception as exc:  # subprocess/timeout/OS errors -> structured, not a crash.
        return {"ok": False, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}",
                "returncode": -1}


def _parse_or_wrap(out: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer the CLI's own JSON; if it printed a plain note, wrap it. The model gets the
    predictor's verbatim numbers -- this function never invents or edits a figure."""
    txt = (out.get("stdout") or "").strip()
    if out["ok"] and txt:
        try:
            return {"prediction": json.loads(txt)}
        except json.JSONDecodeError:
            return {"note": txt}
    return {"error": "predictor produced no usable output",
            "stderr": out.get("stderr", ""), "returncode": out.get("returncode")}


def predict_pregame(sport: str, home: str, away: str) -> Dict[str, Any]:
    """Calibrated PRE-GAME surface for a matchup. Shells predict_matchup --json."""
    s = _norm_sport(sport)
    if s not in _SPORTS:
        return {"error": f"unknown sport {sport!r}; expected one of {list(_SPORTS)}"}
    args = [_PREDICT_MOD, "--sport", s, "--home", str(home), "--away", str(away), "--json"]
    return _parse_or_wrap(_run_cli(args))


def _ingame_flags(sport: str, state: Dict[str, Any]) -> List[str]:
    """Map a sport-appropriate state dict onto predict_matchup's in-game flags. Unknown keys
    are ignored; the CLI itself notes any inapplicable state -- we never synthesize one."""
    flags: List[str] = []
    fmap = {
        "elapsed": "--elapsed", "inning": "--inning", "half": "--half",
        "home_score": "--home-score", "away_score": "--away-score",
        "sets_home": "--sets-home", "sets_away": "--sets-away",
        "games_home": "--games-home", "games_away": "--games-away",
        "surface": "--surface",
    }
    for key, flag in fmap.items():
        if key in state and state[key] is not None:
            flags.extend([flag, str(state[key])])
    return flags


def predict_ingame(sport: str, state: Dict[str, Any]) -> Dict[str, Any]:
    """Calibrated IN-GAME surface: pregame prior + realized state through the validated
    repricer/recalibrator. Shells predict_matchup with state-derived flags."""
    s = _norm_sport(sport)
    if s not in _SPORTS:
        return {"error": f"unknown sport {sport!r}; expected one of {list(_SPORTS)}"}
    if not isinstance(state, dict):
        return {"error": "state must be an object/dict of in-game fields"}
    home = state.get("home") or state.get("home_team") or "HOME"
    away = state.get("away") or state.get("away_team") or "AWAY"
    args = [_PREDICT_MOD, "--sport", s, "--home", str(home), "--away", str(away), "--json"]
    args.extend(_ingame_flags(s, state))
    return _parse_or_wrap(_run_cli(args))


def calibration_report(sport: str) -> Dict[str, Any]:
    """Read-only calibration/reliability report. Shells recal_report (all sports) and slices
    to the requested sport. The numbers are the report's own; we only filter rows."""
    s = _norm_sport(sport)
    if s not in _SPORTS:
        return {"error": f"unknown sport {sport!r}; expected one of {list(_SPORTS)}"}
    out = _run_cli([_RECAL_MOD])
    text = out.get("stdout") or ""
    lines = [ln for ln in text.splitlines()
             if (s in ln.lower()) or ln.lower().startswith(("sport", "===", "---", "[warn]"))]
    sliced = "\n".join(lines).strip()
    return {"sport": s, "report": sliced or text.strip() or "(no report produced)",
            "stderr": out.get("stderr", "")}


def read_edge_map(sport: Optional[str] = None) -> Dict[str, Any]:
    """Read-only edge-map text from vault/_Edge_Maps IF present (gitignored/local). Returns a
    benign 'unavailable' note on a clone without the vault -- never raises."""
    if not _EDGE_MAP_DIR.is_dir():
        return {"available": False,
                "note": f"no edge maps at {_EDGE_MAP_DIR} (vault is local/gitignored)"}
    s = _norm_sport(sport) if sport else None
    docs: Dict[str, str] = {}
    for path in sorted(_EDGE_MAP_DIR.glob("*.md")):
        if s and s not in path.name.lower():
            continue
        try:
            docs[path.name] = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # unreadable file -> skip, stay read-only/benign.
            docs[path.name] = f"(unreadable: {type(exc).__name__})"
    return {"available": bool(docs), "sport": s, "edge_maps": docs}


# ---------------------------------------------------------------------------
# MCP wiring (only active when the SDK is installed and serve() is called)
# ---------------------------------------------------------------------------
_TOOLS_SPEC = [
    ("predict_pregame", "Calibrated pre-game prediction for a matchup (shells the validated "
     "predictor; the LLM never authors a number).",
     {"type": "object", "required": ["sport", "home", "away"],
      "properties": {"sport": {"type": "string", "enum": list(_SPORTS)},
                     "home": {"type": "string"}, "away": {"type": "string"}}}),
    ("predict_ingame", "Calibrated in-game prediction: pregame prior + realized state.",
     {"type": "object", "required": ["sport", "state"],
      "properties": {"sport": {"type": "string", "enum": list(_SPORTS)},
                     "state": {"type": "object",
                               "description": "in-game fields: home, away, elapsed, inning, "
                               "half, home_score, away_score, sets_home, games_home, surface"}}}),
    ("calibration_report", "Read-only calibration/reliability report for one sport.",
     {"type": "object", "required": ["sport"],
      "properties": {"sport": {"type": "string", "enum": list(_SPORTS)}}}),
]


def _dispatch(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Route a tool call to its pure helper. Central guard: the LLM picks inputs only."""
    if name == "predict_pregame":
        return predict_pregame(args.get("sport", ""), args.get("home", ""), args.get("away", ""))
    if name == "predict_ingame":
        return predict_ingame(args.get("sport", ""), args.get("state", {}) or {})
    if name == "calibration_report":
        return calibration_report(args.get("sport", ""))
    return {"error": f"unknown tool {name!r}"}


def build_server() -> Any:  # pragma: no cover - requires the SDK
    """Construct the stdio MCP Server with the 3 read-only tools + the edge_map resource."""
    if not _HAVE_MCP:
        raise RuntimeError("the 'mcp' SDK is not installed; pip install mcp to serve")
    server = Server("sports_predictor")

    @server.list_tools()
    async def _list_tools() -> List["Tool"]:
        return [Tool(name=n, description=d, inputSchema=s) for (n, d, s) in _TOOLS_SPEC]

    @server.call_tool()
    async def _call_tool(name: str, arguments: Dict[str, Any]) -> List["TextContent"]:
        result = _dispatch(name, arguments or {})
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    @server.list_resources()
    async def _list_resources() -> List["Resource"]:
        return [Resource(uri="edge_map://all", name="edge_map",
                         description="Read-only edge maps (local vault, if present).",
                         mimeType="application/json")]

    @server.read_resource()
    async def _read_resource(uri: str) -> str:
        sport = str(uri).split("://", 1)[-1] if "://" in str(uri) else None
        if sport in ("all", "", None):
            sport = None
        return json.dumps(read_edge_map(sport), indent=2, default=str)

    return server


async def _serve_async() -> None:  # pragma: no cover - requires the SDK + a live stdio peer
    server = build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def serve() -> int:
    """Blocking entry point. Requires the SDK; otherwise prints a guidance note and exits 1."""
    if not _HAVE_MCP:
        print("sports_predictor MCP server: the 'mcp' SDK is not installed "
              "(pip install mcp). Skeleton parsed OK; nothing served.", file=sys.stderr)
        return 1
    import asyncio
    asyncio.run(_serve_async())
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
