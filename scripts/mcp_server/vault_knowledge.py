"""scripts/mcp_server/vault_knowledge.py -- stdio MCP server for the vault RAG layer.

Exposes EXACTLY three retrieval/synthesis tools (text + [[note_id]] citations only):
  vault_search(sport, query, category?, top_k=6)   -> ranked hits
  assemble_pregame_context(sport, home_id, away_id, question?) -> cited bundle
  related_nodes(note_id, hops=1)                    -> graph neighbours

HARD BOUNDARY (binding, tested in scripts/mcp_server/test_boundary.py and the
knowledge tests/test_boundary.py): NO numeric/predict tool is registered. No tool
name or docstring matches predict|prob|odds|edge|bet|kelly|roi|wager|spread_price|
win_prob. assemble_pregame_context NEVER emits a probability/odds/ROI/edge token and
always carries the no-edge disclaimer; empty retrieval -> honest-reject.

The FastMCP SDK is import-guarded so the module (and TOOL_NAMES / the underlying
functions) is unit-testable without a running server. Person-free vault.

SETTINGS SNIPPET (HUMAN-CONFIRM before applying to .claude/settings.json):
  "mcpServers": {
    "vault-knowledge": {
      "command": "C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe",
      "args": ["scripts/mcp_server/vault_knowledge.py"],
      "env": {"PYTHONPATH": "C:/Users/neelj/nba-ai-system"}
    }
  }

ASCII only. <=300 LOC. No src/kernel/api edits.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import config  # noqa: E402
from scripts.platformkit.knowledge.assemble import (  # noqa: E402
    NO_EDGE_DISCLAIMER, assemble, check_bundle)
from scripts.platformkit.knowledge import retrieve as _retrieve  # noqa: E402

# The ONLY tool names this server is allowed to register. The boundary test asserts
# the registered set equals this set and that none matches a numeric/predict pattern.
TOOL_NAMES = ("vault_search", "assemble_pregame_context", "related_nodes")


# ---------------------------------------------------------------------------
# Pure tool implementations (no MCP dependency; directly unit-testable)
# ---------------------------------------------------------------------------
def vault_search(sport: str, query: str, category: Optional[str] = None,
                 top_k: int = config.TOP_K) -> List[dict]:
    """Search the vault for SCOUTING CONCEPTS. Returns ranked hits with [[note_id]]
    citations and snippets. Qualitative text only -- this is a narration surface."""
    res = _retrieve.retrieve(query, sport=sport, category=category, top_k=top_k)
    if res.reject:
        return []
    return [{"note_id": h.note_id, "sport": h.sport, "category": h.category,
             "title": h.title, "snippet": h.snippet, "citation": h.citation,
             "relevance": round(h.score, 4)} for h in res.hits]


def assemble_pregame_context(sport: str, home_id: str = "", away_id: str = "",
                             question: str = "") -> dict:
    """Assemble a citation-grounded SCOUTING bundle for a matchup. Synthesis/narration
    only. Carries a no-advantage disclaimer; honest-reject when nothing is relevant.
    Returns qualitative concept text, never a forecast number."""
    b = assemble(sport, home_id=home_id, away_id=away_id, question=question or None)
    if check_bundle(b):  # defense in depth: never serve a boundary-violating bundle
        b = assemble(sport, home_id=home_id, away_id=away_id, question=None)
    return {"bundle": b.markdown, "citations": b.citations, "reject": b.reject,
            "disclaimer": NO_EDGE_DISCLAIMER}


def related_nodes(note_id: str, hops: int = 1) -> List[dict]:
    """Follow the note's ## Related wikilinks `hops` deep -> neighbouring concept
    nodes with [[note_id]] citations. Graph context only; no numbers."""
    hits = _retrieve.related_nodes(note_id, hops=hops)
    return [{"note_id": h.note_id, "sport": h.sport, "category": h.category,
             "title": h.title, "snippet": h.snippet, "citation": h.citation}
            for h in hits]


def manifest() -> dict:
    """Index build stats (freshness) so any agent sees note count + last refresh."""
    if config.MANIFEST_PATH.exists():
        return json.loads(config.MANIFEST_PATH.read_text(encoding="ascii"))
    return {"status": "index not built",
            "hint": "python -m scripts.platformkit.knowledge.index --build"}


# ---------------------------------------------------------------------------
# MCP wiring (import-guarded so tests run without the SDK / a live server)
# ---------------------------------------------------------------------------
def build_server():  # pragma: no cover - exercised only when mcp is installed
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("vault-knowledge")
    mcp.tool()(vault_search)
    mcp.tool()(assemble_pregame_context)
    mcp.tool()(related_nodes)

    @mcp.resource("vault://index/manifest")
    def _manifest() -> str:
        return json.dumps(manifest(), indent=2)

    @mcp.resource("vault://note/{note_id}")
    def _note(note_id: str) -> str:
        st = _retrieve.get_state()
        sub = st.df[st.df["note_id"] == note_id]
        if sub.empty:
            return "Note not found."
        return str(sub.iloc[0]["body"])

    return mcp


if __name__ == "__main__":  # pragma: no cover
    build_server().run()
