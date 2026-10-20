// Lightweight stand-in for components/paper/PaperEquityChart (recharts-free) so the
// page tests never await the lazy next/dynamic chunk under full-suite load.
import { fmtUnits } from "@/components/paper/equityFormat";
import type { PnlSeriesPoint } from "@/lib/types";

export { fmtUnits, fmtSignedUnits } from "@/components/paper/equityFormat";

export function EquityChartSkeleton() {
  return <div data-testid="paper-equity-loading" aria-busy="true" aria-label="equity curve loading" />;
}

export function PaperEquityChart({ points }: { points: PnlSeriesPoint[] | null }) {
  if (!points || points.length === 0) {
    return <div data-testid="paper-equity-empty">no equity curve yet UNITS only -- no dollars; no edge claimed</div>;
  }
  const last = points[points.length - 1]?.balance_units ?? 0;
  return (
    <div data-testid="paper-equity-chart">
      <span>cumulative bankroll (units)</span>
      <span data-testid="paper-equity-last">{fmtUnits(last)}u</span>
    </div>
  );
}
