/**
 * api.js — Court Vision Frontend ↔ Backend API Client
 * 
 * Every function calls your FastAPI backend at request time.
 * When models improve → same endpoint returns better data → zero frontend changes.
 * 
 * Graceful fallback: if the API is unreachable, returns mock data so the
 * website always works during development.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function safeFetch(url, options = {}) {
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    return await res.json();
  } catch (err) {
    console.warn(`[Court Vision API] ${url} failed:`, err.message);
    return null; // caller handles fallback
  }
}

// ═══════════════════════════════════════════════════════════
// AI CONSOLE
// ═══════════════════════════════════════════════════════════

/** Send a chat message to the Claude-backed AI engine */
export async function chatQuery(message, gameId = null) {
  const data = await safeFetch(`${API_BASE}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message, game_id: gameId }),
  });
  return data?.response || 'System offline — model loading...';
}

/** Get the full dashboard overview (games + edges + injuries + performance) */
export async function getDashboardOverview() {
  return await safeFetch(`${API_BASE}/stitch/dashboard/overview`);
}

// ═══════════════════════════════════════════════════════════
// BETTING MODELS
// ═══════════════════════════════════════════════════════════

/** Today's game predictions with win prob, spread, total */
export async function getTodayGames() {
  return await safeFetch(`${API_BASE}/predictions/today`);
}

/** Player prop projections (pts, reb, ast, 3pm, etc.) */
export async function getPlayerProps(playerId, season = '2024-25') {
  return await safeFetch(`${API_BASE}/predictions/props/${playerId}?season=${season}`);
}

/** Today's ranked betting edges with Kelly sizing */
export async function getTodayEdges(minEv = 0.03) {
  return await safeFetch(`${API_BASE}/analytics/edges/today?min_ev=${minEv}`);
}

/** Current +EV betting edges from live odds */
export async function getBettingEdges(limit = 20) {
  return await safeFetch(`${API_BASE}/stitch/betting/edges?limit=${limit}`);
}

/** Injury risk for a specific player */
export async function getInjuryRisk(playerId, season = '2024-25') {
  return await safeFetch(`${API_BASE}/predictions/injury-risk`, {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, season }),
  });
}

/** Breakout potential for a specific player */
export async function getBreakout(playerId, opponentTeam = null) {
  return await safeFetch(`${API_BASE}/predictions/breakout`, {
    method: 'POST',
    body: JSON.stringify({ player_id: playerId, opponent_team: opponentTeam }),
  });
}

// ═══════════════════════════════════════════════════════════
// ANALYTICS
// ═══════════════════════════════════════════════════════════

/** Rolling CLV summary (7d, 30d for spread + total) */
export async function getCLVSummary() {
  return await safeFetch(`${API_BASE}/analytics/clv-summary`);
}

/** Model performance metrics (accuracy, brier, MAE, R²) */
export async function getModelPerformance() {
  return await safeFetch(`${API_BASE}/stitch/models/performance`);
}

/** Shot chart data for a specific game */
export async function getShotChart(gameId) {
  return await safeFetch(`${API_BASE}/analytics/shot-chart?game_id=${gameId}`);
}

// ═══════════════════════════════════════════════════════════
// SYSTEM
// ═══════════════════════════════════════════════════════════

/** Health check — is the API up? */
export async function healthCheck() {
  const data = await safeFetch(`${API_BASE}/health`);
  return data?.status === 'ok';
}

// ═══════════════════════════════════════════════════════════
// WEBSOCKET (Real-time updates)
// ═══════════════════════════════════════════════════════════

const WS_BASE = API_BASE.replace('http', 'ws');

export function connectRealtime(onMessage) {
  try {
    const ws = new WebSocket(`${WS_BASE}/ws/realtime`);
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'subscribe' }));
    };
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onMessage(data);
    };
    ws.onerror = (err) => console.warn('[WS] Error:', err);
    ws.onclose = () => {
      console.warn('[WS] Disconnected — reconnecting in 5s');
      setTimeout(() => connectRealtime(onMessage), 5000);
    };
    return ws;
  } catch (err) {
    console.warn('[WS] Could not connect:', err);
    return null;
  }
}
