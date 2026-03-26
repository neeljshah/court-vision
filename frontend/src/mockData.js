// ============================================================
// mockData.js — NBA AI Platform Mock Dataset
// Source: nba-ai-system data/nba/ + model_reports/
// TODO: Replace with live API calls to FastAPI backend (Phase 13)
// ============================================================

// --- REAL GAME RESULTS from data/nba/comparison_*.json ---
export const recentResults = [
  { id: '0022401117', home: 'GSW', away: 'LAL', homeScore: 116, awayScore: 123, date: '2025-03-20' },
  { id: '0022400852', home: 'CLE', away: 'BOS', homeScore: 123, awayScore: 116, date: '2025-03-18' },
  { id: '0022400737', home: 'OKC', away: 'DAL', homeScore: 118, awayScore: 104, date: '2025-03-16' },
  { id: '0022400430', home: 'DEN', away: 'PHX', homeScore: 112, awayScore: 108, date: '2025-03-14' },
  { id: '0022400537', home: 'MIL', away: 'CHI', homeScore: 121, awayScore: 113, date: '2025-03-12' },
  { id: '0022400909', home: 'LAL', away: 'SAS', homeScore: 126, awayScore: 115, date: '2025-03-10' },
  { id: '0022400923', home: 'BOS', away: 'MIA', homeScore: 119, awayScore: 107, date: '2025-03-09' },
  { id: '0022401066', home: 'MEM', away: 'NOP', homeScore: 117, awayScore: 99,  date: '2025-03-07' },
];

// --- TODAY'S SLATE (2025-03-24) — model predictions ---
// TODO: Replace with GET /api/predictions/today
export const todayGames = [
  {
    id: 'g001',
    homeTeam: 'GSW', homeName: 'Golden State Warriors', homeLogo: '🟡',
    awayTeam: 'OKC', awayName: 'Oklahoma City Thunder', awayLogo: '🔵',
    gameTime: '7:30 PM ET',
    status: 'Upcoming',
    winProb: { home: 0.41, away: 0.59 },
    spread: { favorite: 'OKC', line: -4.5 },
    total: { line: 228.5 },
    prediction: 'OKC',
    confidence: 0.59,
    // Data from matchup_GSW_LAL_2024-25_Reg.json (similar matchup)
    shotsPerMinute: 3.5,
    totalFGA: 168,
    modelNote: 'OKC top net-rtg differential; GSW 2nd-night B2B fatigue flag',
    edge: '+EV',
  },
  {
    id: 'g002',
    homeTeam: 'CLE', homeName: 'Cleveland Cavaliers', homeLogo: '🍷',
    awayTeam: 'MIL', awayName: 'Milwaukee Bucks', awayLogo: '🟢',
    gameTime: '8:00 PM ET',
    status: 'Upcoming',
    winProb: { home: 0.67, away: 0.33 },
    spread: { favorite: 'CLE', line: -6.5 },
    total: { line: 222.0 },
    prediction: 'CLE',
    confidence: 0.67,
    // CLE beat BOS 123-116 in last tracked game (0022400852)
    shotsPerMinute: 3.81,
    totalFGA: 183,
    modelNote: 'CLE home dominance; Bucks missing Khris Middleton',
    edge: 'NO EDGE',
  },
  {
    id: 'g003',
    homeTeam: 'BOS', homeName: 'Boston Celtics', homeLogo: '☘️',
    awayTeam: 'MIA', awayName: 'Miami Heat', awayLogo: '🔴',
    gameTime: '8:30 PM ET',
    status: 'Upcoming',
    winProb: { home: 0.72, away: 0.28 },
    spread: { favorite: 'BOS', line: -8.5 },
    total: { line: 216.5 },
    prediction: 'BOS',
    confidence: 0.72,
    // BOS vs MIA playoff matchup in data
    shotsPerMinute: 3.4,
    totalFGA: 171,
    modelNote: 'BOS highest eFG% in league; MIA road record 12-21',
    edge: '+EV',
  },
  {
    id: 'g004',
    homeTeam: 'DEN', homeName: 'Denver Nuggets', homeLogo: '⛰️',
    awayTeam: 'LAL', awayName: 'Los Angeles Lakers', awayLogo: '💛',
    gameTime: '10:00 PM ET',
    status: 'Upcoming',
    winProb: { home: 0.55, away: 0.45 },
    spread: { favorite: 'DEN', line: -2.5 },
    total: { line: 230.0 },
    prediction: 'DEN',
    confidence: 0.55,
    // DEN vs PHX matchup data used as proxy
    shotsPerMinute: 3.6,
    totalFGA: 176,
    modelNote: 'Altitude edge for Denver; LeBron load management risk',
    edge: 'LEAN',
  },
  {
    id: 'g005',
    homeTeam: 'SAC', homeName: 'Sacramento Kings', homeLogo: '👑',
    awayTeam: 'POR', awayName: 'Portland Trail Blazers', awayLogo: '🌹',
    gameTime: '10:00 PM ET',
    status: 'Upcoming',
    winProb: { home: 0.78, away: 0.22 },
    spread: { favorite: 'SAC', line: -11.5 },
    total: { line: 225.5 },
    prediction: 'SAC',
    confidence: 0.78,
    // SAC vs POR matchup in data
    shotsPerMinute: 3.7,
    totalFGA: 181,
    modelNote: 'SAC pace advantage; POR tank mode — soft Book line',
    edge: '+EV',
  },
];

// --- PLAYER PROPS ---
// TODO: Replace with GET /api/predictions/props/{player_id}
// Model metrics: PTS MAE=0.310 R²=0.994 | REB MAE=0.115 R²=0.995 | AST MAE=0.091 R²=0.992
export const playerProps = [
  {
    playerId: 203999,
    player: 'LeBron James',
    team: 'LAL',
    opponent: 'DEN',
    position: 'SF',
    stat: 'PTS',
    line: 25.5,
    projection: 27.8,
    edge: +2.3,
    ev: 0.082,
    recommendation: 'OVER',
    confidence: 0.71,
    dnpRisk: 0.04,
    // Last 5 from gamelog_203999_2024-25.json
    last5: [18, 26, 20, 41, 33],
    last10avg: 27.4,
  },
  {
    playerId: 203999,
    player: 'LeBron James',
    team: 'LAL',
    opponent: 'DEN',
    position: 'SF',
    stat: 'AST',
    line: 7.5,
    projection: 9.1,
    edge: +1.6,
    ev: 0.094,
    recommendation: 'OVER',
    confidence: 0.74,
    dnpRisk: 0.04,
    last5: [7, 13, 11, 13, 9],
    last10avg: 8.8,
  },
  {
    playerId: 1629029,
    player: 'Luka Doncic',
    team: 'DAL',
    opponent: 'OKC',
    position: 'PG',
    stat: 'PTS',
    line: 31.5,
    projection: 29.4,
    edge: -2.1,
    ev: -0.061,
    recommendation: 'UNDER',
    confidence: 0.65,
    dnpRisk: 0.07,
    last5: [28, 35, 22, 31, 40],
    last10avg: 31.2,
  },
  {
    playerId: 1629029,
    player: 'Luka Doncic',
    team: 'DAL',
    opponent: 'OKC',
    position: 'PG',
    stat: 'REB',
    line: 8.5,
    projection: 9.3,
    edge: +0.8,
    ev: 0.044,
    recommendation: 'OVER',
    confidence: 0.57,
    dnpRisk: 0.07,
    last5: [9, 7, 11, 8, 10],
    last10avg: 8.9,
  },
  {
    playerId: 1628384,
    player: 'Jayson Tatum',
    team: 'BOS',
    opponent: 'MIA',
    position: 'SF',
    stat: 'PTS',
    line: 27.5,
    projection: 30.2,
    edge: +2.7,
    ev: 0.103,
    recommendation: 'OVER',
    confidence: 0.77,
    dnpRisk: 0.02,
    last5: [34, 28, 35, 24, 31],
    last10avg: 29.8,
  },
  {
    playerId: 1628384,
    player: 'Jayson Tatum',
    team: 'BOS',
    opponent: 'MIA',
    position: 'SF',
    stat: 'REB',
    line: 8.5,
    projection: 8.1,
    edge: -0.4,
    ev: -0.019,
    recommendation: 'UNDER',
    confidence: 0.53,
    dnpRisk: 0.02,
    last5: [9, 7, 8, 10, 6],
    last10avg: 8.2,
  },
  {
    playerId: 1628369,
    player: 'Nikola Jokic',
    team: 'DEN',
    opponent: 'LAL',
    position: 'C',
    stat: 'PTS',
    line: 25.5,
    projection: 28.1,
    edge: +2.6,
    ev: 0.097,
    recommendation: 'OVER',
    confidence: 0.73,
    dnpRisk: 0.01,
    last5: [31, 22, 35, 27, 29],
    last10avg: 27.3,
  },
  {
    playerId: 1628369,
    player: 'Nikola Jokic',
    team: 'DEN',
    opponent: 'LAL',
    position: 'C',
    stat: 'AST',
    line: 9.5,
    projection: 11.2,
    edge: +1.7,
    ev: 0.088,
    recommendation: 'OVER',
    confidence: 0.69,
    dnpRisk: 0.01,
    last5: [9, 12, 14, 8, 11],
    last10avg: 10.4,
  },
  {
    playerId: 1629627,
    player: 'Shai Gilgeous-Alexander',
    team: 'OKC',
    opponent: 'GSW',
    position: 'PG',
    stat: 'PTS',
    line: 29.5,
    projection: 31.7,
    edge: +2.2,
    ev: 0.091,
    recommendation: 'OVER',
    confidence: 0.72,
    dnpRisk: 0.02,
    last5: [32, 28, 34, 29, 36],
    last10avg: 31.1,
  },
  {
    playerId: 203507,
    player: 'Giannis Antetokounmpo',
    team: 'MIL',
    opponent: 'CLE',
    position: 'PF',
    stat: 'PTS',
    line: 29.5,
    projection: 27.3,
    edge: -2.2,
    ev: -0.071,
    recommendation: 'UNDER',
    confidence: 0.66,
    dnpRisk: 0.06,
    last5: [31, 24, 28, 33, 26],
    last10avg: 28.4,
  },
];

// --- WIN PROBABILITY MODEL METRICS ---
// Source: data/model_reports/win_probability_latest.json (retrained 2026-03-18)
export const winProbMetrics = {
  accuracy: 0.691,
  brier: 0.2675,
  clvProxy: 0.0807,
  homeBaseline: 0.5451,
  seasons: ['2022-23', '2023-24', '2024-25'],
  folds: [
    { fold: 1, n: 737, acc: 0.6282, brier: 0.2859 },
    { fold: 2, n: 737, acc: 0.6065, brier: 0.2840 },
    { fold: 3, n: 737, acc: 0.6649, brier: 0.2402 },
    { fold: 4, n: 737, acc: 0.6038, brier: 0.2598 },
  ],
  featureImportance: [
    { feature: 'net_rtg_diff',        importance: 0.1248 },
    { feature: 'home_net_rtg',        importance: 0.1117 },
    { feature: 'away_net_rtg',        importance: 0.0655 },
    { feature: 'home_season_win_pct', importance: 0.0576 },
    { feature: 'away_season_win_pct', importance: 0.0531 },
    { feature: 'pace_diff',           importance: 0.0412 },
    { feature: 'rest_days_diff',      importance: 0.0388 },
    { feature: 'home_off_rtg',        importance: 0.0344 },
  ],
};

// --- PROPS MODEL METRICS ---
// Source: data/model_reports/player_props_latest.json
export const propsModelMetrics = {
  pts: { mae: 0.310, r2: 0.994, label: 'Points' },
  reb: { mae: 0.115, r2: 0.995, label: 'Rebounds' },
  ast: { mae: 0.091, r2: 0.992, label: 'Assists' },
  fg3m: { mae: 0.083, r2: 0.941, label: '3-Pointers' },
  stl:  { mae: 0.066, r2: 0.931, label: 'Steals' },
  blk:  { mae: 0.044, r2: 0.948, label: 'Blocks' },
  tov:  { mae: 0.078, r2: 0.930, label: 'Turnovers' },
};

// --- LEBRON JAMES GAME LOG (player 203999) ---
// Source: data/nba/gamelog_203999_2024-25.json — first 20 entries
export const lebroGameLog = [
  { game: 1,  pts: 18, reb: 7,  ast: 7,  min: 31 },
  { game: 2,  pts: 26, reb: 16, ast: 13, min: 41 },
  { game: 3,  pts: 20, reb: 12, ast: 11, min: 38 },
  { game: 4,  pts: 41, reb: 15, ast: 13, min: 39 },
  { game: 5,  pts: 33, reb: 12, ast: 9,  min: 37 },
  { game: 6,  pts: 61, reb: 10, ast: 10, min: 53 },
  { game: 7,  pts: 27, reb: 14, ast: 6,  min: 32 },
  { game: 8,  pts: 39, reb: 10, ast: 10, min: 38 },
  { game: 9,  pts: 40, reb: 13, ast: 9,  min: 39 },
  { game: 10, pts: 28, reb: 7,  ast: 5,  min: 38 },
  { game: 11, pts: 34, reb: 8,  ast: 4,  min: 38 },
  { game: 12, pts: 35, reb: 18, ast: 8,  min: 40 },
  { game: 13, pts: 24, reb: 13, ast: 9,  min: 41 },
  { game: 14, pts: 31, reb: 21, ast: 22, min: 45 },
  { game: 15, pts: 22, reb: 15, ast: 6,  min: 38 },
  { game: 16, pts: 20, reb: 14, ast: 9,  min: 39 },
  { game: 17, pts: 23, reb: 17, ast: 15, min: 34 },
  { game: 18, pts: 32, reb: 14, ast: 10, min: 38 },
  { game: 19, pts: 18, reb: 9,  ast: 19, min: 39 },
  { game: 20, pts: 12, reb: 13, ast: 10, min: 35 },
];

// --- TEAM COMPARISON (GSW vs LAL) ---
// Source: data/nba/matchup_GSW_LAL_2024-25_Reg.json + team stats
export const teamComparison = {
  teamA: {
    abbr: 'GSW', name: 'Golden State Warriors',
    offRtg: 112.4, defRtg: 112.1, netRtg: 0.3,
    pace: 100.2, eFGpct: 0.546, tovPct: 14.1,
    winPct: 0.470, last10: '5-5',
  },
  teamB: {
    abbr: 'LAL', name: 'Los Angeles Lakers',
    offRtg: 114.8, defRtg: 111.9, netRtg: 2.9,
    pace: 98.7, eFGpct: 0.531, tovPct: 12.8,
    winPct: 0.530, last10: '7-3',
  },
};

// Radar chart dimensions for team comparison
export const radarDimensions = [
  { key: 'offRtg',  label: 'Off Rtg',  max: 120, min: 105 },
  { key: 'defRtg',  label: 'Def Rtg',  max: 120, min: 105, invert: true },
  { key: 'pace',    label: 'Pace',     max: 105, min: 95 },
  { key: 'eFGpct',  label: 'eFG%',    max: 0.58, min: 0.50 },
  { key: 'winPct',  label: 'Win%',    max: 0.75, min: 0.25 },
];

// --- DATASET STATS (used in Analytics header) ---
export const datasetStats = {
  gamesTracked: 17,
  seasonGames: 3675,
  playerGameLogs: 622,
  shotCharts: 569,
  pbpGames: 3627,
  modelsLive: 18,
  modelsTotal: 90,
};

// --- MOCK CHAT HISTORY ---
// TODO: Replace with Claude API (claude-sonnet-4-6) + tool calls (Phase 15)
export const initialChatHistory = [
  {
    id: 1,
    role: 'assistant',
    text: "Welcome to NBA AI. I'm your analytics assistant powered by 18 trained ML models and 3 seasons of NBA data.\n\nYou can ask me about:\n• **Game predictions** — win probabilities, spread edges\n• **Player props** — projections vs book lines, EV\n• **Analytics** — shot quality, defensive pressure, spacing\n• **Betting** — Kelly sizing, CLV tracking, soft book lag\n\nTry: *\"What's the edge on tonight's DEN vs LAL game?\"*",
    timestamp: '9:00 AM',
  },
  {
    id: 2,
    role: 'user',
    text: "What's the model saying about LeBron's points prop tonight?",
    timestamp: '9:01 AM',
  },
  {
    id: 3,
    role: 'assistant',
    text: "**LeBron James — PTS vs DEN (Tonight)**\n\nModel projection: **27.8 pts** (line: 25.5)\nEdge: **+2.3 over par** | EV: **+8.2%** | Confidence: 71%\n\nKey factors:\n• Season avg 28.3 pts, L10 avg 27.4 pts\n• 61-pt game in game 6 skews upside; floor is ~18\n• DEN allows 114.2 pts/100 vs SF — slightly favorable matchup\n• Altitude flag: 1st Denver game since Nov — minor fatigue factor\n• DNP risk: 4% (load mgmt model)\n\nRecommendation: **OVER 25.5** (moderate size — Kelly 4.1% of bankroll)\n\n*Prop correlation alert: If taking LeBron PTS OVER, avoid LAL team total OVER (0.68 correlation — redundant exposure).*",
    timestamp: '9:01 AM',
  },
  {
    id: 4,
    role: 'user',
    text: "How confident is the win probability model overall?",
    timestamp: '9:03 AM',
  },
  {
    id: 5,
    role: 'assistant',
    text: "**Win Probability Model — Performance Summary**\n\nTrained on 3,675 games across 2022-23, 2023-24, 2024-25:\n\n| Metric | Value | Baseline |\n|--------|-------|----------|\n| Accuracy | **69.1%** | 54.5% (home) |\n| Brier Score | 0.2675 | — |\n| CLV Proxy | +0.081 | 0.0 |\n\n4-fold cross-validation: 60.4%–66.5% range (fold 3 best at 66.5%)\n\nTop predictive features:\n1. net_rtg_diff (12.5% importance)\n2. home_net_rtg (11.2%)\n3. away_net_rtg (6.6%)\n\n*Phase G note: After 10+ full game CV clips, win prob will incorporate spatial features (defender distance, spacing index) — projected +2-3% accuracy lift.*",
    timestamp: '9:03 AM',
  },
];

// --- MOCK CHAT RESPONSES for new user messages ---
// TODO: Replace with real Claude API tool calls (Phase 15)
export const mockResponses = [
  {
    trigger: ['okc', 'thunder', 'gsw', 'warriors', 'tonight'],
    response: "**OKC Thunder vs GSW Warriors (7:30 PM ET)**\n\nModel prediction: **OKC wins** (59% probability)\nSpread: OKC -4.5 | Our line: OKC -5.2 → **book is soft by 0.7 pts**\n\nKey factors:\n• OKC league-best net_rtg differential (+8.1)\n• GSW on 2nd night of B2B — fatigue penalty applied\n• Shai GCA projection: 31.7 pts vs line 29.5 → OVER +2.2 edge\n\nRecommendation: **OKC -4.5** (lean) + **SGA OVER 29.5** (strong)",
  },
  {
    trigger: ['jokic', 'nikola', 'denver', 'nuggets'],
    response: "**Nikola Jokic — Projections vs LAL Tonight**\n\nPTS: **28.1** (line 25.5) → OVER +2.6 | EV +9.7%\nAST: **11.2** (line 9.5) → OVER +1.7 | EV +8.8%\nREB: **12.4** (line 11.5) → OVER +0.9 | EV +4.1%\n\nJokic is 3rd in prop model accuracy (R² 0.994). Season avg: 26.8/12.2/9.0.\n\nCorrelation note: PTS + AST OVER have 0.71 correlation — consider a parlay only if line is +185 or better.",
  },
  {
    trigger: ['tatum', 'jayson', 'celtics', 'boston'],
    response: "**Jayson Tatum — Projections vs MIA Tonight**\n\nPTS: **30.2** (line 27.5) → **OVER** +2.7 | EV +10.3% — strongest edge tonight\nREB: **8.1** (line 8.5) → UNDER -0.4 | EV -1.9% (no edge)\n\nBOS vs MIA historical (from playoff matchup data): BOS avg 119 pts, 54.3% eFG%. Tatum performs 12% above season avg vs MIA.\n\nModel note: DNP risk 2%. High confidence pick.",
  },
  {
    trigger: ['edge', 'best', 'pick', 'tonight', 'recommend'],
    response: "**Top Edges Tonight (2025-03-24)**\n\n🟢 **Jayson Tatum PTS OVER 27.5** — EV +10.3%, conf 77%\n🟢 **Nikola Jokic PTS OVER 25.5** — EV +9.7%, conf 73%\n🟢 **SGA PTS OVER 29.5** — EV +9.1%, conf 72%\n🟡 **OKC -4.5 ML** — EV lean, book soft by 0.7 pts\n🟡 **LeBron PTS OVER 25.5** — EV +8.2%, DNP risk 4%\n\n⚠️ No edge: MIL/CLE spread (line matches model exactly)\n\nKelly sizing: Max 5% bankroll per bet. Correlated picks (Tatum PTS + BOS team total) count as one exposure.",
  },
];

export function getMockResponse(userMessage) {
  const lower = userMessage.toLowerCase();
  for (const r of mockResponses) {
    if (r.trigger.some(t => lower.includes(t))) return r.response;
  }
  return "I'm analyzing that query... For full AI responses with chart rendering, connect the Claude API backend (Phase 15). In the meantime, check the Betting Dashboard for all today's projections and edges.\n\n*Tip: Ask about a specific player (e.g. 'LeBron points') or tonight's matchup (e.g. 'OKC vs GSW') for detailed analysis.*";
}
