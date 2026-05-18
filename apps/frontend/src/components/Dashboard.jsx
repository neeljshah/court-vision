import React, { useState, useEffect } from 'react';
import AIPredictionScreener from './AIPredictionScreener';
import LiveGameFeed from './LiveGameFeed';
import BettingControls from './BettingControls';
import AnalyticsDrillDown from './AnalyticsDrillDown';
import SimulationMode from './SimulationMode';
import PipelineStatus from './PipelineStatus';
import { api } from '../services/api';

export default function Dashboard() {
  const [pipelineData, setPipelineData] = useState(null);

  useEffect(() => {
    api.getPipelineStatus().then(setPipelineData);
  }, []);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-surface-900 text-white">
      {/* Pipeline Status Header */}
      <div className="h-10 shrink-0">
        <PipelineStatus data={pipelineData} />
      </div>

      <div className="flex-1 flex overflow-hidden p-4 gap-4">
        {/* Left Sidebar: Live Game Feed */}
        <div className="w-80 shrink-0 hidden lg:flex flex-col bg-surface-800 rounded-xl border border-surface-700 overflow-hidden">
          <LiveGameFeed />
        </div>

        {/* Core Center Column */}
        <div className="flex-1 flex flex-col gap-4 overflow-hidden relative">
          
          {/* AI Core Panel (Primary Screen) */}
          <div className="flex-1 min-h-[400px] rounded-xl border-2 border-brand-orange/50 overflow-hidden relative shadow-[0_0_15px_rgba(249,115,22,0.15)] bg-surface-800 flex flex-col">
            <AIPredictionScreener />
          </div>

          {/* Bottom Analytics & Simulation Panels */}
          <div className="h-80 shrink-0 flex gap-4">
             <div className="flex-1 rounded-xl bg-surface-800 border border-surface-700 p-4 overflow-hidden">
               <AnalyticsDrillDown />
             </div>
             <div className="w-1/3 min-w-[300px] shrink-0 rounded-xl bg-surface-800 border border-surface-700 p-4">
               <SimulationMode />
             </div>
          </div>
        </div>

        {/* Right Sidebar: Betting Controls */}
        <div className="w-96 shrink-0 bg-surface-800 rounded-xl border border-surface-700 p-4 flex flex-col overflow-hidden">
          <BettingControls />
        </div>
      </div>
    </div>
  );
}
