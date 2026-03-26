"""Dashboard-specific API routes — expose chat, CLV, and edge detection."""

import os
import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

router = APIRouter()


# ── 1. AI Chat ───────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    game_id: Optional[str] = None


@router.post("/chat")
async def chat(req: ChatRequest):
    """AI chat powered by Claude + live DB + model tools."""
    try:
        from src.analytics.chat import answer
        response = answer(req.message, game_id=req.game_id)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 2. CLV Summary ───────────────────────────────────────────────────────────

@router.get("/analytics/clv-summary")
async def clv_summary():
    """Rolling CLV for spread and total (7d, 30d)."""
    try:
        from src.analytics.clv_tracker import get_clv_summary
        return get_clv_summary()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 3. Today's Edges ─────────────────────────────────────────────────────────

@router.get("/analytics/edges/today")
async def edges_today(min_ev: float = 0.03):
    """Ranked betting edges for today's slate."""
    try:
        from src.analytics.edge_detector import EdgeDetector
        detector = EdgeDetector()
        edges = detector.find_today_edges(min_ev=min_ev)
        return {
            "edges": [e.to_dict() for e in edges],
            "count": len(edges),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
