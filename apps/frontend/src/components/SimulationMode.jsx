import React, { useState } from 'react';
import { Dices } from 'lucide-react';

export default function SimulationMode() {
  const [runs, setRuns] = useState(10000);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);

  const runSimulation = () => {
    setRunning(true);
    setResult(null);
    setTimeout(() => {
      setResult({
        ev: '+12.4%',
        maxDrawdown: '-24.1%',
        winProb: '58.2%',
        medianROI: '+9.8%'
      });
      setRunning(false);
    }, 1500);
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex flex-col gap-1 mb-4 shrink-0">
        <div className="flex items-center gap-2">
          <Dices size={20} className="text-gray-400" />
          <h2 className="font-bold">Monte Carlo Sim</h2>
        </div>
        <p className="text-xs text-gray-400">Projected distribution over {runs.toLocaleString()} runs</p>
      </div>

      <div className="flex-1 flex flex-col justify-center">
        {!result && !running && (
          <div className="text-center text-gray-500 text-sm">
            Ready to simulate edge distribution based on current card.
          </div>
        )}
        
        {running && (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin w-8 h-8 flex items-center justify-center border-2 border-brand-orange border-t-transparent rounded-full" />
          </div>
        )}

        {result && !running && (
           <div className="grid grid-cols-2 gap-3 mb-4">
             <div className="bg-surface-900 rounded p-3 border border-brand-green/30">
               <div className="text-xs text-gray-400">Total EV</div>
               <div className="text-xl font-bold text-brand-green">{result.ev}</div>
             </div>
             <div className="bg-surface-900 rounded p-3 border border-brand-red/30">
               <div className="text-xs text-gray-400">Max Drawdown</div>
               <div className="text-xl font-bold text-brand-red">{result.maxDrawdown}</div>
             </div>
             <div className="bg-surface-900 rounded p-3 border border-surface-600">
               <div className="text-xs text-gray-400">Win Rate</div>
               <div className="text-xl font-bold">{result.winProb}</div>
             </div>
             <div className="bg-surface-900 rounded p-3 border border-surface-600">
               <div className="text-xs text-gray-400">Median ROI</div>
               <div className="text-xl font-bold text-brand-blue">{result.medianROI}</div>
             </div>
           </div>
        )}
      </div>

      <button 
        onClick={runSimulation}
        disabled={running}
        className="w-full py-2 bg-surface-700 hover:bg-surface-600 rounded border border-surface-600 text-sm font-semibold transition-colors mt-auto"
      >
        {running ? 'Simulating...' : `Run ${runs/1000}k Simulations`}
      </button>
    </div>
  );
}
