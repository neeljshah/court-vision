import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { Radio, Flame } from 'lucide-react';

export default function LiveGameFeed() {
  const [games, setGames] = useState([]);

  useEffect(() => {
    api.getGameEdges().then(data => {
      // simulate all games being live for the feed
      setGames(data);
    });
  }, []);

  return (
    <div className="flex-1 flex flex-col h-full bg-surface-800">
      <div className="p-4 border-b border-surface-700 flex items-center justify-between">
        <h2 className="font-bold flex items-center gap-2">
          <Radio size={18} className="text-brand-red animate-pulse" /> Live Feed
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {games.map((g) => (
          <div key={g.id} className="bg-surface-700 rounded-lg p-3 border border-surface-600 relative overflow-hidden group">
            <div className="absolute top-0 left-0 w-1 h-full bg-brand-orange opacity-50 group-hover:opacity-100 transition-opacity" />
            
            <div className="flex justify-between items-center mb-2">
              <div className="text-xs font-semibold text-brand-red px-1.5 py-0.5 rounded bg-brand-red/10 animate-pulse">
                {g.quarter || '1st'} {g.timeRemaining || '12:00'}
              </div>
              <div className="text-xs text-gray-400">Score</div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between items-center">
                <span className="font-bold flex items-center gap-2">
                  {g.away} {g.momentum?.current === g.away && <Flame size={14} className="text-brand-orange" />}
                </span>
                <span className="font-mono text-lg">{g.score?.away || 0}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="font-bold flex items-center gap-2">
                  {g.home} {g.momentum?.current === g.home && <Flame size={14} className="text-brand-orange" />}
                </span>
                <span className="font-mono text-lg">{g.score?.home || 0}</span>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-surface-600">
              <div className="flex justify-between text-xs text-brand-green">
                <span>Live CLV Update</span>
                <span>+1.5% Edge</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
