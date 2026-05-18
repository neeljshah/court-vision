"""
Stitch Integration API Router
Provides endpoints specifically for Google Stitch frontend integration
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
import json
import asyncio
from datetime import datetime, timedelta
import logging

from src.prediction.game_prediction import predict_today, predict_game
from src.prediction.player_props import predict_props
from src.analytics.betting_edge import get_betting_edges
from src.analytics.shot_quality import get_shot_quality_metrics
from src.data.line_monitor import get_current_lines
from src.data.injury_monitor import get_injury_report

router = APIRouter()
logger = logging.getLogger(__name__)

# WebSocket connection manager for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except:
                # Connection closed, remove it
                self.active_connections.remove(connection)

manager = ConnectionManager()

@router.get("/health")
async def stitch_health():
    """Health check endpoint for Stitch to verify API is working"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "features": {
            "predictions": True,
            "analytics": True,
            "realtime": True,
            "websocket": True
        }
    }

@router.get("/dashboard/overview")
async def get_dashboard_overview():
    """Main dashboard data for Stitch frontend"""
    try:
        # Get today's games
        today_games = predict_today()
        
        # Get betting edges
        edges = get_betting_edges(limit=20)
        
        # Get injury updates
        injuries = get_injury_report()
        
        # System performance metrics
        performance = {
            "win_probability_accuracy": 69.1,
            "shots_analyzed": 221866,
            "games_processed": 3627,
            "models_trained": 18,
            "last_update": datetime.utcnow().isoformat()
        }
        
        return {
            "today_games": today_games,
            "betting_edges": edges,
            "injuries": injuries,
            "performance": performance,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Dashboard overview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/games/today")
async def get_today_games():
    """Get today's NBA games with predictions"""
    try:
        games = predict_today()
        return {
            "games": games,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Today's games error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/game/{game_id}")
async def get_game_details(game_id: str, home_team: str = "", away_team: str = ""):
    """Get detailed game analysis"""
    try:
        # Get game prediction
        prediction = predict_game(home_team, away_team) if home_team and away_team else {}
        
        # Get current lines
        lines = get_current_lines(game_id)
        
        # Get player props for both teams
        # This would need to be implemented based on your prop models
        
        return {
            "game_id": game_id,
            "prediction": prediction,
            "lines": lines,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Game details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/player/{player_id}/props")
async def get_player_props(player_id: str, season: str = "2024-25"):
    """Get player prop predictions for a specific player"""
    try:
        props = predict_props(player_id, season)
        return {
            "player_id": player_id,
            "season": season,
            "predictions": props,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Player props error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/shot-quality/{player_id}")
async def get_player_shot_quality(player_id: str, season: str = "2024-25"):
    """Get detailed shot quality analytics for a player"""
    try:
        shot_metrics = get_shot_quality_metrics(player_id, season)
        return {
            "player_id": player_id,
            "season": season,
            "shot_quality": shot_metrics,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Shot quality error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/betting/edges")
async def get_betting_edges_api(limit: int = 50):
    """Get current betting edges and opportunities"""
    try:
        edges = get_betting_edges(limit=limit)
        return {
            "edges": edges,
            "count": len(edges),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Betting edges error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/team/{team_id}")
async def get_team_analytics(team_id: str):
    """Get comprehensive team analytics"""
    try:
        # This would aggregate all your analytics modules for a team
        analytics = {
            "team_id": team_id,
            "offensive_metrics": {},  # From your analytics modules
            "defensive_metrics": {},  # From your analytics modules
            "lineup_analysis": {},    # From lineup synergy
            "momentum": {},           # From momentum analysis
            "timestamp": datetime.utcnow().isoformat()
        }
        return analytics
    except Exception as e:
        logger.error(f"Team analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/models/performance")
async def get_model_performance():
    """Get performance metrics for all ML models"""
    try:
        performance = {
            "win_probability": {
                "accuracy": 69.1,
                "brier_score": 0.203,
                "games_trained": 3627
            },
            "player_props": {
                "points_mae": 0.308,
                "rebounds_mae": 0.113,
                "assists_mae": 0.093,
                "r_squared": 0.93
            },
            "xfG_model": {
                "brier_score": 0.226,
                "shots_analyzed": 221866
            },
            "matchup_model": {
                "r_squared": 0.796,
                "mae": 4.55
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        return performance
    except Exception as e:
        logger.error(f"Model performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "subscribe":
                # Client wants to subscribe to updates
                await websocket.send_text(json.dumps({
                    "type": "subscribed",
                    "message": "Connected to real-time updates"
                }))
            elif message.get("type") == "ping":
                # Keep-alive ping
                await websocket.send_text(json.dumps({"type": "pong"}))
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Background task to broadcast updates
async def broadcast_updates():
    """Broadcast real-time updates to connected clients"""
    while True:
        try:
            # Check for new data updates
            # This would integrate with your data pipeline
            
            # Example: Broadcast updated scores
            await manager.broadcast({
                "type": "score_update",
                "data": {
                    "game_id": "example",
                    "score": "100-95",
                    "time": "Q4 2:30"
                },
                "timestamp": datetime.utcnow().isoformat()
            })
            
            await asyncio.sleep(30)  # Update every 30 seconds
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
            await asyncio.sleep(60)

@router.get("/export/predictions")
async def export_predictions(format: str = "json"):
    """Export current predictions in various formats"""
    try:
        predictions = predict_today()
        
        if format.lower() == "csv":
            # Convert to CSV and return
            import pandas as pd
            df = pd.DataFrame(predictions)
            return JSONResponse(
                content=df.to_csv(index=False),
                media_type="text/csv"
            )
        else:
            return {
                "predictions": predictions,
                "export_timestamp": datetime.utcnow().isoformat(),
                "format": format
            }
    except Exception as e:
        logger.error(f"Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/players")
async def search_players(query: str, limit: int = 10):
    """Search for players by name"""
    try:
        # This would integrate with your player data
        players = []  # Implement player search logic
        return {
            "query": query,
            "players": players,
            "count": len(players)
        }
    except Exception as e:
        logger.error(f"Player search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
