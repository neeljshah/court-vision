"use client";

// Sparkline -- a 24px x 96px line for a numeric series. Dependency-free SVG:
// the previous recharts LineChart pulled the entire chart bundle (373 KB raw)
// into every page that rendered a sparkline. Same props and stroke colours.

export function Sparkline({
  data,
  positive = true,
}: {
  data: number[];
  positive?: boolean;
}) {
  if (!data || data.length < 2) {
    return <div className="h-6 text-faint text-xs">no data</div>;
  }
  const colour = positive ? "#22c55e" : "#ef4444";
  const width = 96;
  const height = 24;
  const pad = 1;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = (width - pad * 2) / (data.length - 1);
  const points = data
    .map((y, i) => {
      const px = pad + i * stepX;
      const py = pad + (1 - (y - min) / span) * (height - pad * 2);
      return `${px.toFixed(1)},${py.toFixed(1)}`;
    })
    .join(" ");
  return (
    <div className="h-6 w-24">
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`trend of ${data.length} values, ${positive ? "up" : "down"}`}
      >
        <polyline
          points={points}
          fill="none"
          stroke={colour}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}
