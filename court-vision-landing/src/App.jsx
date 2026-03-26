import React, { useState, useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { Crosshair, BarChart3, TerminalSquare, ArrowUpRight, Cpu, Activity, Zap, Search } from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, BarChart, Bar, Cell } from 'recharts';

import { 
  chatQuery, 
  getDashboardOverview, 
  getTodayGames, 
  getTodayEdges, 
  getCLVSummary, 
  getModelPerformance,
  connectRealtime
} from './api';

// ===================================
// MICRO-COMPONENTS
// ===================================

const MagneticButton = ({ children, className = '', onClick }) => (
  <button 
    onClick={onClick}
    className={`btn-magnetic btn-slide-accent rounded-xl px-4 py-2 border border-surfaceHover text-xs tracking-wider uppercase font-mono ${className}`}
  >
    <div className="slide-layer" />
    <span className="relative flex items-center justify-center gap-2 z-10">{children}</span>
  </button>
);

const SystemStatus = ({ connected }) => (
  <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent/5 border border-accent/20">
    <div className={`w-1.5 h-1.5 rounded-full ${connected ? 'bg-accent animate-pulse-slow shadow-[0_0_8px_rgba(0,228,255,0.8)]' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]'}`} />
    <span className="text-[10px] font-mono text-accent uppercase tracking-widest">
      {connected ? 'System Online // Live API' : 'Fallback Mode // Mock Data'}
    </span>
  </div>
);

// ===================================
// 1. AI CHAT - MAIN PRODUCT
// ===================================

const AIChat = () => {
  const [query, setQuery] = useState('');
  const [chat, setChat] = useState([
    { role: 'system', content: 'INITIALIZING PROJECT COURT VISION...' },
    { role: 'system', content: 'LATEST RUN CONCLUDED: Searching for +EV opportunities...' },
    { role: 'system', content: 'AWAITING COMMAND EXECUTIVE.' }
  ]);
  const [telemetry, setTelemetry] = useState(null);
  const chatEndRef = useRef(null);

  useEffect(() => {
    async function loadTelemetry() {
      const data = await getDashboardOverview();
      if (data) {
        setTelemetry(data);
      } else {
        // Fallback mocked telemetry
        setTelemetry({
          performance: { win_probability_accuracy: 69.1, shots_analyzed: 221000 },
          betting_edges: [
            { player: 'L. Doncic', stat: 'pts', direction: 'over', line: 32.5, edge_pct: 0.054 },
            { player: 'S. Curry', stat: 'ast', direction: 'under', line: 5.5, edge_pct: 0.048 }
          ]
        });
      }
    }
    loadTelemetry();
  }, []);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    
    setChat(prev => [...prev, { role: 'user', content: query }]);
    const currentQuery = query;
    setQuery('');
    
    setTimeout(() => {
      setChat(prev => [...prev, { role: 'system', content: 'PROCESSING REQUEST VIA CLAUDE ENGINE...' }]);
    }, 100);

    const response = await chatQuery(currentQuery);
    
    setChat(prev => {
      const newChat = [...prev];
      newChat[newChat.length - 1] = { 
        role: 'system', 
        content: response || 'API OFFLINE: Fallback model recommends standard Kelly execution.' 
      };
      return newChat;
    });
  };

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat]);

  return (
    <div className="w-full h-full flex flex-col md:flex-row gap-6 p-6 md:p-8 overflow-hidden h-screen pt-24">
      
      {/* Primary Chat Window */}
      <div className="flex-1 flex flex-col pt-0 pb-6 h-full max-h-full">
        <div className="flex items-center gap-3 mb-6">
          <Cpu className="text-accent" size={24} />
          <h2 className="font-sans font-bold text-2xl text-primary">Intelligence Console</h2>
        </div>

        <div className="flex-1 overflow-y-auto mb-4 p-6 rounded-2xl bg-[#0A0A0F] border border-surfaceHover shadow-inner custom-scroll">
          {chat.map((msg, i) => (
            <div key={i} className={`flex mb-6 ${msg.role === 'system' ? 'text-accent' : 'text-primary opacity-80'}`}>
              <div className="font-data font-bold mr-4 text-xs mt-1 w-4 opacity-50">
                {msg.role === 'system' ? '>' : '$'}
              </div>
              <div className="font-mono text-xs md:text-sm whitespace-pre-wrap leading-relaxed tracking-wide">
                {msg.content}
              </div>
            </div>
          ))}
          <div ref={chatEndRef} />
        </div>

        <div className="flex gap-2 mb-4 overflow-x-auto no-scrollbar">
          {['Identify highest edges today', 'Analyze LAL vs DEN props', 'Summarize recent performance'].map((q, i) => (
            <button 
              key={i} 
              onClick={() => setQuery(q)}
              className="px-3 py-1.5 rounded-lg border border-surfaceHover bg-surface text-[10px] font-mono hover:border-accent hover:text-accent transition-colors whitespace-nowrap"
            >
              {q}
            </button>
          ))}
        </div>

        <form onSubmit={handleSend} className="relative w-full">
          <input 
            type="text" 
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Enter parameters or query..." 
            className="w-full bg-[#0A0A0F] border border-surfaceHover rounded-xl py-4 pl-4 pr-12 font-mono text-sm text-primary focus:outline-none focus:border-accent transition-colors shadow-lg"
          />
          <button type="submit" className="absolute right-3 top-1/2 -translate-y-1/2 text-accent p-2 hover:bg-accent/10 rounded-lg transition-colors">
            <ArrowUpRight size={18} />
          </button>
        </form>
      </div>

      {/* Side Telemetry panel */}
      <div className="w-full md:w-80 flex flex-col gap-6 h-full pb-6 overflow-y-auto no-scrollbar">
        <div className="card-container p-5 bg-[#12121A]">
          <div className="flex items-center gap-2 border-b border-surfaceHover pb-3 mb-4">
            <Zap size={14} className="text-accent" />
            <h3 className="font-mono text-xs text-primary uppercase font-bold tracking-widest">Live Signatures</h3>
          </div>
          <div className="space-y-4">
            {telemetry?.betting_edges?.slice(0,4).map((sig, i) => (
              <div key={i} className="group relative overflow-hidden rounded-lg border border-surfaceHover bg-background p-3 hover:border-accent/40 transition-colors cursor-pointer">
                <div className="flex justify-between items-start mb-2">
                  <span className="font-sans text-xs font-bold text-primary">{sig.player} {sig.direction?.toUpperCase() || ''} {sig.line} {sig.stat?.toUpperCase() || ''}</span>
                  <span className="font-data text-[10px] text-green-400 font-bold bg-green-900/20 px-1.5 py-0.5 rounded border border-green-500/30">
                    +{(sig.edge_pct * 100).toFixed(1)}% Edge
                  </span>
                </div>
                <div className="font-mono text-[10px] text-muted">High Confidence Signal</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card-container p-5 bg-[#12121A]">
           <div className="flex items-center gap-2 border-b border-surfaceHover pb-3 mb-4">
            <Activity size={14} className="text-muted" />
            <h3 className="font-mono text-xs text-primary uppercase font-bold tracking-widest">Run Telemetry</h3>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1 p-2 bg-background rounded-lg border border-surfaceHover">
              <span className="font-mono text-[9px] text-muted uppercase">Model Accuracy</span>
              <span className="font-data text-sm text-accent font-bold">{telemetry?.performance?.win_probability_accuracy || 69.1}%</span>
            </div>
            <div className="flex flex-col gap-1 p-2 bg-background rounded-lg border border-surfaceHover">
              <span className="font-mono text-[9px] text-muted uppercase">Shots Analyzed</span>
              <span className="font-data text-sm text-primary font-bold">{telemetry?.performance?.shots_analyzed?.toLocaleString() || '221K'}</span>
            </div>
            <div className="col-span-2 flex flex-col gap-1 p-2 bg-background rounded-lg border border-surfaceHover">
              <span className="font-mono text-[9px] text-muted uppercase">Allocated Compute (Live)</span>
              <div className="w-full h-1.5 bg-surfaceHover rounded-full mt-1 overflow-hidden">
                <div className="h-full bg-accent w-[82%]" />
              </div>
              <span className="font-data text-xs text-muted mt-0.5">XGBoost / Sonnet-4.6</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ===================================
// 2. BETTING MODELS
// ===================================

const BettingModels = () => {
  const comp = useRef(null);
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fallback Mock Data
  const MOCK_GAMES = [
    { 
      game_id: '1', home_team: 'LAL', away_team: 'DEN', 
      spread_detail: { spread_est: 4.5, confidence: 'high' },
      home_win_prob: 0.582, edge_ev: 0.045, 
      betting_edges: [{ player: 'LAL', stat: 'ML', line: -110, direction: 'over', kelly_size: 21.5 }] 
    },
    { 
      game_id: '2', home_team: 'BOS', away_team: 'MIA', 
      spread_detail: { spread_est: -3.1, confidence: 'medium' },
      home_win_prob: 0.621, edge_ev: 0.031, 
      betting_edges: [] 
    },
    { 
      game_id: '3', home_team: 'GSW', away_team: 'SAC', 
      spread_detail: { spread_est: -1.5, confidence: 'low' },
      home_win_prob: 0.490, edge_ev: -0.015, 
      betting_edges: [] 
    },
  ];

  useEffect(() => {
    async function loadGames() {
      const data = await getTodayGames();
      if (data && data.games && data.games.length > 0) {
        setGames(data.games);
      } else {
        setGames(MOCK_GAMES);
      }
      setLoading(false);
    }
    loadGames();
  }, []);

  useEffect(() => {
    if (loading) return;
    let ctx = gsap.context(() => {
      gsap.from('.model-card', {
        y: 30,
        opacity: 0,
        duration: 0.6,
        stagger: 0.08,
        ease: 'power2.out'
      });
    }, comp);
    return () => ctx.revert();
  }, [loading]);

  if (loading) return <div className="p-24 text-center text-accent font-mono uppercase">Syncing Live Models...</div>;

  return (
    <div ref={comp} className="w-full h-full p-6 md:p-8 pt-24 overflow-y-auto custom-scroll">
      <div className="flex items-center justify-between mb-8 max-w-7xl mx-auto">
        <h2 className="font-sans font-bold text-2xl text-primary">Prediction Engine Dashboard</h2>
        <div className="flex gap-3">
          <MagneticButton>Refresh Lines</MagneticButton>
          <MagneticButton>Sort: Edge %</MagneticButton>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto">
        {games.map((game, idx) => {
          const edgePct = (game.edge_ev * 100).toFixed(1);
          const hasEdge = game.edge_ev > 0;
          const prob = (game.home_win_prob * 100).toFixed(1);
          const recBet = hasEdge ? 'YES' : 'NO';
          const stake = game.betting_edges?.[0]?.kelly_size 
                        ? `$${game.betting_edges[0].kelly_size.toFixed(0)}` 
                        : '0';

          return (
            <div key={game.game_id || idx} className="model-card card-container p-6 relative group bg-[#12121A] hover:border-accent/40 overflow-hidden cursor-crosshair transition-colors">
              <div className="flex justify-between items-start mb-4">
                <span className="font-sans font-bold text-sm text-primary uppercase tracking-wide">
                  {game.away_team || game.away_abbrev} <span className="opacity-50">@</span> {game.home_team || game.home_abbrev}
                </span>
                <span className={`font-data text-[10px] font-bold px-2 py-0.5 rounded border ${hasEdge ? 'text-green-400 border-green-400/30 bg-green-900/20' : 'text-red-400 border-red-400/30 bg-red-900/20'}`}>
                  {hasEdge ? '+' : ''}{edgePct}% EDGE
                </span>
              </div>

              <div className="w-full py-2 px-3 bg-background border border-surfaceHover rounded-lg mb-4 text-center">
                <span className="font-mono text-xs text-accent uppercase">
                  {game.spread_detail?.spread_est > 0 ? `Spread (-${game.spread_detail.spread_est} ${game.home_team})` : `Spread (+${Math.abs(game.spread_detail?.spread_est || 0)} ${game.home_team})`}
                </span>
              </div>

              <div className="flex justify-between items-center mb-6 px-1">
                <div className="flex flex-col items-center">
                  <span className="font-mono text-[9px] text-muted uppercase">Home Win Prob</span>
                  <span className="font-data text-sm text-primary font-bold">{prob}%</span>
                </div>
                <div className="flex flex-col items-center">
                  <span className="font-mono text-[9px] text-muted uppercase">Conf.</span>
                  <span className={`font-data text-sm font-bold ${game.spread_detail?.confidence === 'high' ? 'text-green-400' : 'text-primary'}`}>
                    {game.spread_detail?.confidence?.toUpperCase() || 'MED'}
                  </span>
                </div>
                <div className="flex flex-col items-center">
                  <span className="font-mono text-[9px] text-muted uppercase">Rec Stake</span>
                  <span className="font-data text-sm text-green-400 font-bold">{stake}</span>
                </div>
              </div>

              <div className="flex justify-between items-center pt-4 border-t border-surfaceHover/50">
                <span className="font-mono text-xs font-bold text-muted">SYSTEM DIRECTIVE:</span>
                <span className={`font-mono text-xs font-bold px-3 py-1 rounded bg-surface border ${recBet === 'YES' ? 'text-accent border-accent/40' : 'text-muted border-surfaceHover'}`}>
                  {recBet}
                </span>
              </div>

              <div className="absolute inset-0 bg-[#0A0A0F]/95 backdrop-blur-sm flex flex-col items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300 gap-4 p-6 z-10">
                <div className="font-sans font-bold text-lg text-primary">Deep Breakdown</div>
                <div className="w-full space-y-2">
                  <div>
                    <div className="flex justify-between font-mono text-[9px] text-muted mb-1"><span>Matchup Adv</span><span>{prob}%</span></div>
                    <div className="w-full h-1.5 bg-background rounded-full overflow-hidden"><div className="h-full bg-accent" style={{width: `${prob}%`}} /></div>
                  </div>
                </div>
                {game.betting_edges?.length > 0 && (
                  <div className="w-full text-center mt-2">
                    <span className="font-mono text-[10px] text-accent">Top Prop: {game.betting_edges[0].player} {game.betting_edges[0].direction}</span>
                  </div>
                )}
                <MagneticButton>Load Full Model Outputs</MagneticButton>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ===================================
// 3. ANALYTICS DB
// ===================================

const AnalyticsDash = () => {
  const comp = useRef(null);
  const [clvData, setClvData] = useState(null);

  // Fallback charts
  const PNL_DATA = [ { date: '10-01', pnl: 1000 }, { date: '10-05', pnl: 2400 }, { date: '10-10', pnl: 1800 }, { date: '10-15', pnl: 4500 }, { date: '10-20', pnl: 3900 }, { date: '10-25', pnl: 6200 }, { date: '10-30', pnl: 8100 } ];
  const BET_TYPE_DATA = [ { name: 'Spreads', roi: 4.2 }, { name: 'Totals', roi: 1.8 }, { name: 'Props', roi: 8.5 }, { name: 'SGP', roi: 12.4 } ];

  useEffect(() => {
    async function loadData() {
      const data = await getCLVSummary();
      if (data && data.spread_7d) {
        setClvData(data);
      }
    }
    loadData();
  }, []);

  useEffect(() => {
    let ctx = gsap.context(() => {
      gsap.from('.anim-chart', {
        y: 20,
        opacity: 0,
        duration: 0.8,
        stagger: 0.2,
        ease: 'power2.out'
      });
    }, comp);
    return () => ctx.revert();
  }, []);

  const clvVal = clvData?.spread_7d?.mean_clv ? `+${clvData.spread_7d.mean_clv.toFixed(2)}` : '+1.42';

  return (
    <div ref={comp} className="w-full h-full p-6 md:p-8 pt-24 overflow-y-auto custom-scroll">
      <div className="flex items-center justify-between mb-8 max-w-7xl mx-auto">
        <h2 className="font-sans font-bold text-2xl text-primary">Performance & Analytics</h2>
        <div className="flex gap-2">
          {['7D', '30D', 'YTD'].map(l => (
            <button key={l} className="px-3 py-1 font-mono text-[10px] uppercase border border-surfaceHover rounded-lg hover:border-accent hover:text-accent transition-colors bg-[#12121A]">{l}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 max-w-7xl mx-auto mb-6">
        {[
          { l: 'Total PnL', v: '+$8,100', c: 'text-green-400' },
          { l: 'System ROI', v: '+14.2%', c: 'text-green-400' },
          { l: '7D CLV (Spread)', v: clvVal, c: 'text-accent' },
          { l: 'Sharpe', v: '2.41', c: 'text-primary' }
        ].map((s, i) => (
          <div key={i} className="anim-chart card-container p-5 bg-[#12121A] flex flex-col gap-2 relative overflow-hidden">
            <div className="absolute right-0 top-0 bottom-0 w-16 bg-gradient-to-l from-white/[0.02] to-transparent pointer-events-none" />
            <span className="font-mono text-[10px] text-muted uppercase">{s.l}</span>
            <span className={`font-data text-2xl font-bold ${s.c}`}>{s.v}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 max-w-7xl mx-auto mb-6">
        {/* Equity Curve */}
        <div className="anim-chart card-container p-6 lg:col-span-2 bg-[#12121A] h-80 flex flex-col">
          <div className="flex justify-between items-center mb-4">
            <span className="font-sans font-bold text-sm text-primary uppercase">Equity Curve</span>
            <span className="font-mono text-[9px] text-green-400 border border-green-400/30 px-2 py-0.5 rounded">LIVE</span>
          </div>
          <div className="flex-1 w-full relative">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={PNL_DATA} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00E4FF" stopOpacity={0.3}/>
                    <stop offset="95%" stopColor="#00E4FF" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#2A2A35" vertical={false} />
                <XAxis dataKey="date" stroke="#5A5A66" fontSize={10} tickLine={false} />
                <YAxis stroke="#5A5A66" fontSize={10} tickLine={false} tickFormatter={(val) => `$${val}`} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1A1A24', border: '1px solid #2A2A35', borderRadius: '8px', fontFamily: 'JetBrains Mono', fontSize: '12px' }}
                  itemStyle={{ color: '#00E4FF' }}
                />
                <Area type="monotone" dataKey="pnl" stroke="#00E4FF" strokeWidth={2} fillOpacity={1} fill="url(#colorPnl)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Bar chart */}
        <div className="anim-chart card-container p-6 bg-[#12121A] h-80 flex flex-col">
          <span className="font-sans font-bold text-sm text-primary uppercase mb-4">ROI by Bet Type</span>
          <div className="flex-1 w-full relative">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={BET_TYPE_DATA} margin={{ top: 5, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2A2A35" vertical={false} />
                <XAxis dataKey="name" stroke="#5A5A66" fontSize={10} tickLine={false} />
                <YAxis stroke="#5A5A66" fontSize={10} tickLine={false} tickFormatter={(val) => `${val}%`} />
                <Tooltip cursor={{fill: '#1A1A24'}} contentStyle={{ backgroundColor: '#12121A', border: '1px solid #2A2A35', borderRadius: '8px', fontFamily: 'Space Mono', fontSize: '10px' }} />
                <Bar dataKey="roi" radius={[4, 4, 0, 0]}>
                  {BET_TYPE_DATA.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.roi >= 0 ? '#00E4FF' : '#E63B2E'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

    </div>
  );
};

// ===================================
// APP LAYOUT SHELL
// ===================================

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');
  const [apiConnected, setApiConnected] = useState(false);

  useEffect(() => {
    // Healthcheck polling
    let interval;
    const check = async () => {
      try {
        const res = await fetch('http://localhost:8000/health');
        if (res.ok) setApiConnected(true);
        else setApiConnected(false);
      } catch {
        setApiConnected(false);
      }
    };
    check();
    interval = setInterval(check, 10000);
    return () => clearInterval(interval);
  }, []);

  const navItems = [
    { id: 'chat', label: 'Console', icon: TerminalSquare },
    { id: 'models', label: 'Models', icon: Crosshair },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 }
  ];

  return (
    <div className="flex h-screen w-full bg-background text-primary font-sans overflow-hidden bg-noise">
      
      {/* Sidebar */}
      <div className="w-16 md:w-64 bg-[#0A0A0F] border-r border-surfaceHover flex flex-col z-50 shadow-2xl shrink-0">
        <div className="h-20 flex items-center justify-center md:justify-start md:px-6 border-b border-surfaceHover">
          <div className="w-8 h-8 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center shrink-0">
            <span className="font-drama font-bold text-accent italic">CV</span>
          </div>
          <span className="hidden md:block ml-3 font-sans font-bold text-sm tracking-widest text-primary uppercase whitespace-nowrap">Court Vision</span>
        </div>

        <div className="flex-1 py-6 flex flex-col gap-2 px-2 md:px-4">
          {navItems.map(item => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button 
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`relative flex items-center gap-3 p-3 rounded-xl transition-all duration-300 w-full group overflow-hidden ${isActive ? 'bg-surface text-accent' : 'text-muted hover:text-primary hover:bg-[#12121A]'}`}
              >
                {isActive && <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-1/2 bg-accent rounded-r-md shadow-[0_0_10px_rgba(0,228,255,0.8)]" />}
                <Icon size={18} className="shrink-0 md:ml-2" />
                <span className="hidden md:block font-mono text-xs uppercase tracking-wide whitespace-nowrap">{item.label}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative h-screen overflow-hidden">
        {/* Topbar sticky overlay */}
        <div className="absolute top-0 left-0 right-0 h-20 bg-gradient-to-b from-background via-background/90 to-transparent flex items-center justify-end px-6 md:px-8 z-40 pointer-events-none">
          <div className="pointer-events-auto">
            <SystemStatus connected={apiConnected} />
          </div>
        </div>

        {/* Tab Content Views */}
        {activeTab === 'chat' && <AIChat />}
        {activeTab === 'models' && <BettingModels />}
        {activeTab === 'analytics' && <AnalyticsDash />}
      </div>
    </div>
  );
}
