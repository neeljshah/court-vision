"""
Real-time WebSocket service for NBA AI System
Handles live updates for scores, injuries, odds, and predictions
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set
import websockets
from websockets.server import WebSocketServerProtocol

from src.data.line_monitor import get_current_lines
from src.data.injury_monitor import get_injury_report
from src.prediction.game_prediction import get_live_predictions
from src.pipeline.tasks import update_game_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealtimeService:
    def __init__(self):
        self.clients: Dict[str, WebSocketServerProtocol] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # client_id -> set of subscription types
        self.game_cache: Dict[str, Dict] = {}
        self.last_update = {}
        
    async def register_client(self, websocket: WebSocketServerProtocol, client_id: str):
        """Register a new client"""
        self.clients[client_id] = websocket
        self.subscriptions[client_id] = set()
        logger.info(f"Client {client_id} connected. Total clients: {len(self.clients)}")
        
        # Send initial data
        await self.send_initial_data(client_id)
    
    async def unregister_client(self, client_id: str):
        """Unregister a client"""
        if client_id in self.clients:
            del self.clients[client_id]
        if client_id in self.subscriptions:
            del self.subscriptions[client_id]
        logger.info(f"Client {client_id} disconnected. Total clients: {len(self.clients)}")
    
    async def subscribe(self, client_id: str, subscription_type: str, params: Dict = None):
        """Subscribe client to specific data type"""
        if client_id in self.subscriptions:
            self.subscriptions[client_id].add(subscription_type)
            logger.info(f"Client {client_id} subscribed to {subscription_type}")
            
            # Send immediate data for this subscription
            if subscription_type == "scores":
                await self.send_scores_update(client_id)
            elif subscription_type == "odds":
                await self.send_odds_update(client_id)
            elif subscription_type == "injuries":
                await self.send_injury_update(client_id)
            elif subscription_type == "predictions":
                await self.send_predictions_update(client_id)
    
    async def unsubscribe(self, client_id: str, subscription_type: str):
        """Unsubscribe client from specific data type"""
        if client_id in self.subscriptions:
            self.subscriptions[client_id].discard(subscription_type)
            logger.info(f"Client {client_id} unsubscribed from {subscription_type}")
    
    async def send_initial_data(self, client_id: str):
        """Send initial data to newly connected client"""
        try:
            # Send today's games
            await self.send_to_client(client_id, {
                "type": "initial_games",
                "data": await self.get_today_games(),
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Send current betting edges
            await self.send_to_client(client_id, {
                "type": "initial_edges",
                "data": await self.get_betting_edges(),
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Error sending initial data to {client_id}: {e}")
    
    async def send_to_client(self, client_id: str, message: Dict):
        """Send message to specific client"""
        if client_id in self.clients:
            try:
                await self.clients[client_id].send(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}")
                await self.unregister_client(client_id)
    
    async def broadcast(self, message_type: str, data: Dict, subscription_type: str = None):
        """Broadcast message to all subscribed clients"""
        message = {
            "type": message_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for client_id, subscriptions in self.subscriptions.items():
            if subscription_type is None or subscription_type in subscriptions:
                await self.send_to_client(client_id, message)
    
    async def get_today_games(self):
        """Get today's games with current status"""
        # This would integrate with your game prediction system
        return {
            "games": [
                {
                    "game_id": "GSW/BOS/2024-03-24",
                    "home_team": "GSW",
                    "away_team": "BOS",
                    "status": "live",
                    "score": {"home": 89, "away": 85},
                    "time": "Q4 2:30",
                    "win_prob": {"home": 0.65, "away": 0.35}
                }
            ]
        }
    
    async def get_betting_edges(self):
        """Get current betting edges"""
        # This would integrate with your betting edge detection
        return {
            "edges": [
                {
                    "type": "player_prop",
                    "player": "Stephen Curry",
                    "prop": "points",
                    "line": 28.5,
                    "prediction": 31.2,
                    "edge": 2.7,
                    "confidence": 0.73,
                    "ev": 0.08
                }
            ]
        }
    
    async def send_scores_update(self, client_id: str = None):
        """Send score updates"""
        scores = await self.get_live_scores()
        if client_id:
            await self.send_to_client(client_id, {
                "type": "scores_update",
                "data": scores
            })
        else:
            await self.broadcast("scores_update", scores, "scores")
    
    async def send_odds_update(self, client_id: str = None):
        """Send odds updates"""
        odds = await self.get_live_odds()
        if client_id:
            await self.send_to_client(client_id, {
                "type": "odds_update",
                "data": odds
            })
        else:
            await self.broadcast("odds_update", odds, "odds")
    
    async def send_injury_update(self, client_id: str = None):
        """Send injury updates"""
        injuries = await self.get_live_injuries()
        if client_id:
            await self.send_to_client(client_id, {
                "type": "injury_update",
                "data": injuries
            })
        else:
            await self.broadcast("injury_update", injuries, "injuries")
    
    async def send_predictions_update(self, client_id: str = None):
        """Send prediction updates"""
        predictions = await self.get_live_predictions()
        if client_id:
            await self.send_to_client(client_id, {
                "type": "predictions_update",
                "data": predictions
            })
        else:
            await self.broadcast("predictions_update", predictions, "predictions")
    
    async def get_live_scores(self):
        """Get live game scores"""
        # This would integrate with NBA API or similar
        return {
            "games": [
                {
                    "game_id": "GSW/BOS/2024-03-24",
                    "home_team": "GSW",
                    "away_team": "BOS",
                    "score": {"home": 92, "away": 88},
                    "status": "live",
                    "time": "Q4 1:45",
                    "possession": "home"
                }
            ]
        }
    
    async def get_live_odds(self):
        """Get live betting odds"""
        try:
            lines = get_current_lines()
            return {"odds": lines}
        except Exception as e:
            logger.error(f"Error getting live odds: {e}")
            return {"odds": []}
    
    async def get_live_injuries(self):
        """Get live injury updates"""
        try:
            injuries = get_injury_report()
            return {"injuries": injuries}
        except Exception as e:
            logger.error(f"Error getting injuries: {e}")
            return {"injuries": []}
    
    async def get_live_predictions(self):
        """Get live prediction updates"""
        try:
            predictions = get_live_predictions()
            return {"predictions": predictions}
        except Exception as e:
            logger.error(f"Error getting predictions: {e}")
            return {"predictions": []}
    
    async def start_update_loop(self):
        """Background task to update data and push to clients"""
        while True:
            try:
                # Update scores every 30 seconds during games
                await self.send_scores_update()
                
                # Update odds every 2 minutes
                if datetime.utcnow().second % 120 < 30:
                    await self.send_odds_update()
                
                # Update injuries every 5 minutes
                if datetime.utcnow().second % 300 < 30:
                    await self.send_injury_update()
                
                # Update predictions every minute
                await self.send_predictions_update()
                
                await asyncio.sleep(30)  # Main update interval
                
            except Exception as e:
                logger.error(f"Error in update loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error

# Global service instance
realtime_service = RealtimeService()

async def handle_websocket(websocket: WebSocketServerProtocol, path: str):
    """Handle WebSocket connections"""
    client_id = f"client_{id(websocket)}"
    
    try:
        await realtime_service.register_client(websocket, client_id)
        
        async for message in websocket:
            try:
                data = json.loads(message)
                
                if data.get("type") == "subscribe":
                    await realtime_service.subscribe(
                        client_id, 
                        data.get("subscription"),
                        data.get("params", {})
                    )
                elif data.get("type") == "unsubscribe":
                    await realtime_service.unsubscribe(
                        client_id, 
                        data.get("subscription")
                    )
                elif data.get("type") == "ping":
                    await realtime_service.send_to_client(client_id, {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    logger.warning(f"Unknown message type: {data.get('type')}")
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from client {client_id}")
            except Exception as e:
                logger.error(f"Error handling message from {client_id}: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        await realtime_service.unregister_client(client_id)

async def start_websocket_server(host: str = "0.0.0.0", port: int = 8765):
    """Start the WebSocket server"""
    logger.info(f"🚀 Starting WebSocket server on {host}:{port}")
    
    # Start the update loop in background
    asyncio.create_task(realtime_service.start_update_loop())
    
    # Start the WebSocket server
    server = await websockets.serve(handle_websocket, host, port)
    logger.info(f"✅ WebSocket server started on ws://{host}:{port}")
    
    return server

if __name__ == "__main__":
    import asyncio
    
    async def main():
        server = await start_websocket_server()
        try:
            await server.wait_closed()
        except KeyboardInterrupt:
            logger.info("🛑 WebSocket server stopped")
    
    asyncio.run(main())
