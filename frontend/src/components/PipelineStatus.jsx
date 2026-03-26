import React, { useState } from 'react';
import { Server, AlertTriangle, Download, CheckCircle2 } from 'lucide-react';

export default function PipelineStatus({ data }) {
  const [exported, setExported] = useState(false);

  if (!data) return <div className="h-full bg-surface-900 border-b border-surface-800 animate-pulse" />;

  const handleExport = () => {
    setExported(true);
    setTimeout(() => setExported(false), 2000);
  };

  return (
    <div className="h-full flex items-center justify-between px-4 bg-surface-900 border-b border-surface-800 text-xs text-gray-300">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-brand-green animate-pulse" />
          <span className="font-mono">API: {data.health}</span>
        </div>
        <div className="flex items-center gap-2 text-gray-400">
          Last Retrain: {new Date(data.lastRetrain).toLocaleTimeString()}
        </div>
        {data.driftAlerts?.length > 0 && (
          <div className="flex items-center gap-2 text-brand-orange bg-brand-orange/10 px-3 py-1 rounded-full border border-brand-orange/20">
            <AlertTriangle size={14} />
            {data.driftAlerts.length} Feature Drift Alerts Active
          </div>
        )}
      </div>
      
      <button 
        onClick={handleExport}
        className="flex items-center gap-2 bg-surface-800 hover:bg-surface-700 border border-surface-600 px-3 py-1 rounded transition-colors"
      >
        {exported ? <CheckCircle2 size={14} className="text-brand-green" /> : <Download size={14} />}
        {exported ? 'Exported!' : 'Export CSV'}
      </button>
    </div>
  );
}
