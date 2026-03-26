import React from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { Target } from 'lucide-react';

const mockData = [
  { game: 'G1', actual: 24, proj: 26.5 },
  { game: 'G2', actual: 28, proj: 25.1 },
  { game: 'G3', actual: 31, proj: 30.0 },
  { game: 'G4', actual: 22, proj: 27.5 },
  { game: 'G5', actual: 29, proj: 28.2 },
  { game: 'G6', actual: 33, proj: 29.8 },
];

export default function AnalyticsDrillDown() {
  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4 shrink-0">
        <Target size={20} className="text-gray-400" />
        <h2 className="font-bold">Player Analytics Drill-Down</h2>
      </div>

      <div className="flex gap-4 mb-4 shrink-0">
        <select className="bg-surface-900 border border-surface-600 rounded px-3 py-1 text-sm focus:outline-none focus:border-brand-blue">
          <option>Jayson Tatum (BOS)</option>
          <option>Nikola Jokic (DEN)</option>
          <option>LeBron James (LAL)</option>
        </select>
        <select className="bg-surface-900 border border-surface-600 rounded px-3 py-1 text-sm focus:outline-none focus:border-brand-blue">
          <option>Points (PTS)</option>
          <option>Rebounds (REB)</option>
          <option>Assists (AST)</option>
        </select>
      </div>

      <div className="flex-1 w-full min-h[200px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={mockData} margin={{ top: 5, right: 20, bottom: 5, left: -20 }}>
            <XAxis dataKey="game" stroke="#6b7280" fontSize={12} tickLine={false} axisLine={false} />
            <YAxis stroke="#6b7280" fontSize={12} tickLine={false} axisLine={false} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#1a1d24', border: '1px solid #374151', borderRadius: '8px' }}
              itemStyle={{ color: '#f1f5f9' }}
            />
            <ReferenceLine y={26.5} label={{ position: 'top', value: 'Current Line (26.5)', fill: '#ef4444', fontSize: 10 }} stroke="#ef4444" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="proj" stroke="#3b82f6" strokeWidth={2} dot={false} name="AI Proj" />
            <Line type="monotone" dataKey="actual" stroke="#22c55e" strokeWidth={3} dot={{ r: 4 }} name="Actual" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
