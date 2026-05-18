// Mock API Service for NBA AI Dashboard

// Mock Data Generators
const generateGameEdges = () => [
  {
    id: 'g1',
    home: 'BOS',
    away: 'MIA',
    winProb: { home: 78.5, away: 21.5 },
    spread: { line: -8.5, modelProj: -11.2, edge: 2.7, clv_color: 'green' },
    total: { line: 212.5, modelProj: 205.1, edge: 7.4, clv_color: 'green' },
    status: 'Upcoming',
    time: '7:30 PM ET'
  },
  {
    id: 'g2',
    home: 'DEN',
    away: 'LAL',
    winProb: { home: 65.2, away: 34.8 },
    spread: { line: -5.5, modelProj: -4.1, edge: -1.4, clv_color: 'red' },
    total: { line: 228.5, modelProj: 231.0, edge: 2.5, clv_color: 'green' },
    status: 'Live',
    quarter: '3rd',
    timeRemaining: '04:12',
    score: { home: 78, away: 71 },
    momentum: { current: 'DEN', value: 85 } // 0-100, >50 favors home
  },
  {
    id: 'g3',
    home: 'PHX',
    away: 'GSW',
    winProb: { home: 52.1, away: 47.9 },
    spread: { line: -1.5, modelProj: -0.5, edge: -1.0, clv_color: 'red' },
    total: { line: 235.5, modelProj: 235.8, edge: 0.3, clv_color: 'green' },
    status: 'Upcoming',
    time: '10:00 PM ET'
  }
];

const generatePlayerProps = () => [
  { id: 'p1', player: 'Jayson Tatum', market: 'Points', line: 26.5, proj: 29.8, edge: 3.3, clv_color: 'green', hitRate: 68 },
  { id: 'p2', player: 'Jimmy Butler', market: 'Rebounds', line: 6.5, proj: 5.1, edge: -1.4, clv_color: 'red', hitRate: 42 },
  { id: 'p3', player: 'Nikola Jokic', market: 'Assists', line: 9.5, proj: 11.2, edge: 1.7, clv_color: 'green', hitRate: 75 },
  { id: 'p4', player: 'LeBron James', market: 'Points', line: 24.5, proj: 22.1, edge: -2.4, clv_color: 'red', hitRate: 50 },
  { id: 'p5', player: 'Devin Booker', market: 'Threes', line: 2.5, proj: 3.8, edge: 1.3, clv_color: 'green', hitRate: 62 }
];

const generateSuggestedBets = () => [
  { id: 'b1', type: 'Player Prop', details: 'Tatum O 26.5 Pts', edge: 8.5, kellyFrac: 0.045, recommendedStake: 225, status: 'positive' },
  { id: 'b2', type: 'Game Total', details: 'BOS/MIA U 212.5', edge: 6.2, kellyFrac: 0.038, recommendedStake: 190, status: 'positive' },
  { id: 'b3', type: 'Spread', details: 'DEN -5.5', edge: -2.1, kellyFrac: 0, recommendedStake: 0, status: 'negative' },
  { id: 'b4', type: 'Player Prop', details: 'Booker O 2.5 3PT', edge: 5.1, kellyFrac: 0.025, recommendedStake: 125, status: 'positive' }
];

const generatePipelineStatus = () => ({
  health: 'Healthy',
  lastRetrain: new Date(Date.now() - 3600 * 1000 * 2).toISOString(), // 2 hours ago
  driftAlerts: ['Slight pace variance in MIA games', 'Rebound rate drift for LAL centers'],
  uptime: '99.98%'
});

// Simulated delay to mimic network request
const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const api = {
  getGameEdges: async () => {
    await delay(300);
    return generateGameEdges();
  },
  getPlayerProps: async () => {
    await delay(200);
    return generatePlayerProps();
  },
  getSuggestedBets: async () => {
    await delay(250);
    return generateSuggestedBets();
  },
  getPipelineStatus: async () => {
    await delay(100);
    return generatePipelineStatus();
  },
  placeAutoBets: async (payload) => {
    await delay(800);
    console.log('Bets executed payload:', payload);
    return { success: true, message: `Successfully executed ${payload.bets.length} bets with combined stake $${payload.bets.reduce((a,b) => a+b.stake, 0)}` };
  }
};
