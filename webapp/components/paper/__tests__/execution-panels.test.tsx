// execution-panels.test.tsx -- honest-empty + populated rendering for the three
// new /paper execution panels (PerMarketClvStrips, CircuitBreakerPanel,
// ExecutionQualityPanel). No network -- pure prop-driven rendering.

import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { ExecutionBlock } from "@/lib/paperToday";
import { PerMarketClvStrips } from "@/components/paper/PerMarketClvStrips";
import { CircuitBreakerPanel } from "@/components/paper/CircuitBreakerPanel";
import { ExecutionQualityPanel } from "@/components/paper/ExecutionQualityPanel";
import { RealizedIngameClvPanel } from "@/components/paper/RealizedIngameClvPanel";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

const EXEC: ExecutionBlock = {
  by_market_type: {
    prop: {
      mean_clv_pct: 1.4, median_clv_pct: 1.25, mean_winsorized: true,
      n: 10, n_proxy: 1, basis: "true_close",
      state: "LIVE", cap_per_day: null, placed_today: 3,
    },
    moneyline: {
      mean_clv_pct: 8.0, median_clv_pct: -0.5, mean_winsorized: true,
      n: 4, n_proxy: 0, basis: "true_close",
      state: "CAPPED", cap_per_day: 5, placed_today: 1,
    },
  },
  quality: {
    n_gated: 2, n_ungated: 8, avg_expected_clv_pct: 1.4, median_placement_latency_ms: 220,
  },
  breaker_module_loaded: true,
  realized_ingame: {
    mlb: {
      "30s": { n: 8, mean_pp: 0.4, median_pp: 0.3, pct_favorable: 62.5 },
      "120s": { n: 0, mean_pp: null, median_pp: null, pct_favorable: null },
    },
  },
  thresholds: {
    prop_expected_clv_min_pct: 1.0,
    ingame_expected_clv_min_pct: 1.0,
    ingame_max_drift_pct: 1.0,
    ingame_max_spread_bp: 800.0,
  },
};

describe("PerMarketClvStrips", () => {
  it.each([null, EXEC])("renders only the site-wide CLV sentence (%#)", (execution) => {
    render(<PerMarketClvStrips execution={execution} />);
    const el = screen.getByTestId("per-market-clv-strips");
    expect(el).toHaveTextContent(CLV_UNAVAILABLE);
    expect(el).not.toHaveTextContent("+1.25%");
    expect(el).not.toHaveTextContent("+8.00%");
  });
});

describe("CircuitBreakerPanel", () => {
  it("renders honest empty state with no execution data", () => {
    render(<CircuitBreakerPanel execution={null} />);
    expect(screen.getByTestId("circuit-breaker-panel")).toHaveTextContent(
      /No markets to gate yet/i,
    );
  });

  it("shows LIVE and CAPPED chips with cap/placed-today", () => {
    render(<CircuitBreakerPanel execution={EXEC} />);
    const panel = screen.getByTestId("circuit-breaker-panel");
    expect(panel).toHaveTextContent("LIVE");
    expect(panel).toHaveTextContent("CAPPED");
    expect(panel).toHaveTextContent("5"); // cap/day for moneyline
  });
});

describe("ExecutionQualityPanel", () => {
  it("shows honest no-gated-placements note when quality is null", () => {
    render(<ExecutionQualityPanel execution={null} />);
    expect(screen.getByTestId("execution-quality-panel")).toHaveTextContent(
      /No gated placements yet/i,
    );
  });

  it("renders gated/ungated counts and no expected-CLV figure", () => {
    render(<ExecutionQualityPanel execution={EXEC} />);
    const panel = screen.getByTestId("execution-quality-panel");
    expect(panel).toHaveTextContent("2"); // n_gated
    expect(panel).toHaveTextContent("8"); // n_ungated
    expect(panel).not.toHaveTextContent("+1.40%");
    expect(screen.getByTestId("exec-quality-clv-unavailable")).toHaveTextContent(CLV_UNAVAILABLE);
    expect(panel).toHaveTextContent("220ms");
  });

  it("surfaces the pre-registered thresholds next to measured avgs", () => {
    render(<ExecutionQualityPanel execution={EXEC} />);
    const panel = screen.getByTestId("execution-quality-panel");
    expect(panel).toHaveTextContent("800bp");
  });
});

describe("RealizedIngameClvPanel", () => {
  it("renders honest empty state with no execution data", () => {
    render(<RealizedIngameClvPanel execution={null} />);
    expect(screen.getByTestId("realized-ingame-clv-panel")).toHaveTextContent(
      /No in-game placements gradeable yet/i,
    );
  });

  it("renders only horizons with n > 0, with median move and pct favorable", () => {
    render(<RealizedIngameClvPanel execution={EXEC} />);
    const table = screen.getByTestId("realized-ingame-clv-table");
    expect(table).toHaveTextContent("mlb");
    expect(table).toHaveTextContent("30s");
    expect(table).toHaveTextContent("+0.30pp");
    expect(table).toHaveTextContent("63%");
    expect(table).not.toHaveTextContent("120s");
  });
});
