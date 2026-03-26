import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Settings, Play, CheckCircle2 } from 'lucide-react';

export default function BettingControls() {
  const [bankroll, setBankroll] = useState(5000);
  const [bets, setBets] = useState([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    api.getSuggestedBets().then(setBets);
  }, []);

  const handleExecute = async () => {
    setIsExecuting(true);
    try {
      const payload = {
        bankroll,
        bets: bets.filter(b => b.status === 'positive').map(b => ({
          game_id: b.id,
          player_or_game: b.details,
          bet_type: b.type,
          stake: b.recommendedStake
        }))
      };
      await api.placeAutoBets(payload);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <Settings size={20} className="text-gray-400" />
        <h2 className="font-bold text-lg">Betting Control</h2>
      </div>

      <div className="bg-surface-700 rounded-lg p-4 mb-4 grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs text-gray-400 block mb-1">Bankroll ($)</label>
          <input 
            type="number" 
            value={bankroll}
            onChange={e => setBankroll(Number(e.target.value))}
            className="w-full bg-surface-900 border border-surface-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-orange transition-colors"
          />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">Risk Tolerance</label>
          <select className="w-full bg-surface-900 border border-surface-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-brand-orange transition-colors">
            <option>Kelly (Full)</option>
            <option>Kelly (Half)</option>
            <option>Kelly (Quarter)</option>
            <option>Flat Unit</option>
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-auto bg-surface-900 rounded-lg border border-surface-700 relative">
        <table className="w-full text-xs text-left">
          <thead className="text-gray-400 uppercase bg-surface-800 sticky top-0">
            <tr>
              <th className="px-3 py-2">Bet</th>
              <th className="px-3 py-2 text-right">Edge</th>
              <th className="px-3 py-2 text-right">Stake ($)</th>
            </tr>
          </thead>
          <tbody>
            {bets.map(b => (
              <tr key={b.id} className="border-b border-surface-700 hover:bg-surface-800/50">
                <td className="px-3 py-2 font-medium">{b.details}</td>
                <td className={`px-3 py-2 text-right font-mono ${b.status === 'positive' ? 'text-brand-green' : 'text-brand-red'}`}>
                  {b.edge > 0 ? '+' : ''}{b.edge}%
                </td>
                <td className="px-3 py-2 text-right font-mono">{b.recommendedStake}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 shrink-0">
        <button 
          onClick={handleExecute}
          disabled={isExecuting}
          className={`w-full py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition-all ${
            success ? 'bg-brand-green text-white' : 'bg-brand-orange hover:bg-orange-600 text-white'
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {success ? (
            <><CheckCircle2 size={18} /> Bets Placed!</>
          ) : isExecuting ? (
            <div className="animate-spin w-5 h-5 border-2 border-white/20 border-t-white rounded-full" />
          ) : (
             <><Play size={18} /> Execute AI Edges</>
          )}
        </button>
      </div>
    </div>
  );
}
