import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Activity, Zap, ShieldAlert, BarChart3 } from 'lucide-react';

export default function AIPredictionScreener() {
  const [games, setGames] = useState([]);
  const [props, setProps] = useState([]);

  useEffect(() => {
    Promise.all([api.getGameEdges(), api.getPlayerProps()]).then(([g, p]) => {
      setGames(g);
      setProps(p);
    });
  }, []);

  return (
    <div className="flex-1 flex flex-col h-full bg-gradient-to-b from-surface-800 to-surface-900 overflow-auto">
      <div className="p-4 border-b border-surface-700 flex justify-between items-center bg-surface-800/80 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-brand-orange/20 rounded-lg text-brand-orange">
            <Zap size={24} className="animate-pulse-orange" />
          </div>
          <h2 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-brand-orange to-yellow-500">
            NBA AI Core
          </h2>
        </div>
        <div className="text-sm text-gray-400 flex items-center gap-2">
          <Activity size={16} /> Models Synced & Live
        </div>
      </div>

      <div className="p-4 space-y-6 flex-1 overflow-auto">
        {/* Game Level Edges */}
        <div>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <BarChart3 size={16} /> Top Game Edges
          </h3>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            {games.map(g => (
              <div key={g.id} className="p-4 rounded-lg bg-surface-700 border border-surface-600 hover:border-brand-orange/30 transition-colors">
                <div className="flex justify-between items-center mb-2">
                  <span className="font-bold text-lg">{g.away} @ {g.home}</span>
                  <span className="text-xs px-2 py-1 rounded bg-surface-600 text-gray-300">{g.status}</span>
                </div>
                
                <div className="grid grid-cols-2 gap-4 mt-4">
                  <div className="space-y-1">
                    <div className="text-xs text-gray-400">Win Probability</div>
                    <div className="flex h-1.5 w-full bg-surface-800 rounded-full overflow-hidden">
                      <div className="bg-brand-blue h-full" style={{ width: `${g.winProb.away}%` }} />
                      <div className="bg-white h-full" style={{ width: `${g.winProb.home}%` }} />
                    </div>
                    <div className="flex justify-between text-xs font-mono">
                      <span className="text-brand-blue">{g.winProb.away}%</span>
                      <span className="text-white">{g.winProb.home}%</span>
                    </div>
                  </div>
                  
                  <div className="space-y-1">
                    <div className="text-xs text-gray-400">Total Edge</div>
                    <div className="text-sm font-medium">Model: {g.total.modelProj}</div>
                    <div className={`text-xs font-bold ${g.total.clv_color === 'green' ? 'text-brand-green' : 'text-brand-red'}`}>
                      {g.total.edge > 0 ? '+' : ''}{g.total.edge} Edge
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Player Prop Projections */}
        <div>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-2">
            <ShieldAlert size={16} /> High-Value Prop Projections
          </h3>
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-400 uppercase bg-surface-800 rounded-t-lg">
              <tr>
                <th className="px-4 py-3 rounded-tl-lg">Player</th>
                <th className="px-4 py-3">Market</th>
                <th className="px-4 py-3">Line</th>
                <th className="px-4 py-3">Proj</th>
                <th className="px-4 py-3 text-right rounded-tr-lg">Edge</th>
              </tr>
            </thead>
            <tbody>
              {props.map((p, i) => (
                <tr key={p.id} className="border-b border-surface-600 hover:bg-surface-700/50">
                  <td className="px-4 py-3 font-medium text-white">{p.player}</td>
                  <td className="px-4 py-3 text-gray-300">{p.market}</td>
                  <td className="px-4 py-3 font-mono">{p.line}</td>
                  <td className="px-4 py-3 font-mono font-bold">{p.proj}</td>
                  <td className={`px-4 py-3 font-mono text-right font-bold ${p.clv_color === 'green' ? 'text-brand-green' : 'text-brand-red'}`}>
                    {p.edge > 0 ? '+' : ''}{p.edge}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
