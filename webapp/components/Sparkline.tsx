"use client";

import { LineChart, Line, YAxis, ResponsiveContainer } from "recharts";

export function Sparkline({
  data,
  positive = true,
}: {
  data: number[];
  positive?: boolean;
}) {
  if (!data || data.length < 2) {
    return <div className="h-6 text-slate-600 text-xs">no data</div>;
  }
  const colour = positive ? "#22c55e" : "#ef4444";
  const series = data.map((y, i) => ({ x: i, y }));
  return (
    <div className="h-6 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={series} margin={{ top: 1, right: 1, bottom: 1, left: 1 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line
            type="monotone"
            dataKey="y"
            stroke={colour}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
