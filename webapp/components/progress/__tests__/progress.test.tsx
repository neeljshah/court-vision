import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { CoverageBars } from "../CoverageBars";
import { VerdictTally } from "../VerdictTally";
import { VerdictTrend } from "../VerdictTrend";
import { BacklogBurndown } from "../BacklogBurndown";
import { CompletenessStrip } from "../CompletenessStrip";
import type { ProgressPerSport, ProgressHistoryPoint } from "@/lib/api";

// ---------------------------------------------------------------------------
// /progress honesty-rail tests:
//   * COVERAGE bars render REAL per-sport coverage % (not fabricated)
//   * the verdict tally surfaces ship / reject / insufficient + SHIP framing
//   * the trend is the REAL recorded-verdict count, labelled NOT-accuracy
//   * backlog burn-down shows closed / total honestly
//   * the completeness strip shows parity GREEN + engine INERT (OFF)
//   * honest empty states (no fabricated bars) when data is absent
//   * NO $/pnl/roi/payout field across any progress source file
// ---------------------------------------------------------------------------

const PER_SPORT: Record<string, ProgressPerSport> = {
  nba: {
    coverage_pct: 33.33,
    n_tested: 2,
    n_ship: 0,
    n_reject: 2,
    n_insufficient: 0,
    n_untested_remaining: 4,
  },
  soccer: {
    coverage_pct: 42.86,
    n_tested: 3,
    n_ship: 1,
    n_reject: 2,
    n_insufficient: 0,
    n_untested_remaining: 4,
  },
  tennis: {
    coverage_pct: 50.0,
    n_tested: 3,
    n_ship: 1,
    n_reject: 1,
    n_insufficient: 1,
    n_untested_remaining: 3,
  },
};

const HISTORY: ProgressHistoryPoint[] = [
  { ts: 1, date_et: "2026-06-19", n_verdicts_cumulative: 1, backlog_total: 73, model_static: true, edge_claimed: false },
  { ts: 2, date_et: "2026-06-19", n_verdicts_cumulative: 6, backlog_total: 73, model_static: true, edge_claimed: false },
  { ts: 3, date_et: "2026-06-20", n_verdicts_cumulative: 9, backlog_total: 73, model_static: true, edge_claimed: false },
];

describe("CoverageBars -- REAL per-sport coverage, honest empty", () => {
  it("renders each sport's coverage percent from the data", () => {
    render(<CoverageBars perSport={PER_SPORT} />);
    expect(screen.getByText("33.3%")).toBeTruthy();
    expect(screen.getByText("42.9%")).toBeTruthy();
    expect(screen.getByText("50.0%")).toBeTruthy();
    expect(screen.getAllByRole("meter").length).toBe(3);
  });

  it("renders an honest empty state, never a fabricated bar", () => {
    render(<CoverageBars perSport={null} />);
    expect(screen.getByText(/honest empty/i)).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });
});

describe("VerdictTally -- ship / reject / insufficient + SHIP framing", () => {
  it("totals the verdicts and highlights surviving SHIP signals", () => {
    render(<VerdictTally perSport={PER_SPORT} />);
    // ship=2 (soccer+tennis), reject=5, insufficient=1
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getAllByText("SHIP").length).toBeGreaterThan(0);
    // SHIP carries the calibration-only / vs_close UNPROVEN framing
    expect(
      screen.getAllByText(/calibration-only, vs_close UNPROVEN/).length,
    ).toBeGreaterThan(0);
  });

  it("shows the honest 'none surviving' state when no ship", () => {
    render(
      <VerdictTally
        perSport={{ nba: PER_SPORT.nba }}
      />,
    );
    expect(screen.getByText(/none surviving/i)).toBeTruthy();
  });
});

describe("VerdictTrend -- REAL trend, labelled NOT accuracy", () => {
  it("renders the cumulative-verdict line and the not-accuracy note", () => {
    render(<VerdictTrend history={HISTORY} />);
    expect(screen.getByRole("img")).toBeTruthy();
    expect(screen.getByText(/NOT a live accuracy/i)).toBeTruthy();
    expect(screen.getAllByText(/9 verdicts/).length).toBeGreaterThan(0);
  });

  it("renders an honest empty state for no history", () => {
    render(<VerdictTrend history={[]} />);
    expect(screen.getByText(/honest empty/i)).toBeTruthy();
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("BacklogBurndown -- closed / total honest", () => {
  it("renders closed vs total from the counts", () => {
    render(<BacklogBurndown total={73} remaining={15} />);
    expect(screen.getByText("58")).toBeTruthy();
    expect(screen.getByText(/15 of 73 remaining/)).toBeTruthy();
  });

  it("renders an honest empty state when counts are absent", () => {
    render(<BacklogBurndown total={null} remaining={null} />);
    expect(screen.getByText(/honest empty/i)).toBeTruthy();
  });
});

describe("CompletenessStrip -- parity GREEN + engine INERT", () => {
  it("shows parity GREEN, engine READY, and INERT (OFF)", () => {
    render(
      <CompletenessStrip parityGreen={true} engineReady={true} engineEnabled={false} />,
    );
    expect(screen.getByText("GREEN")).toBeTruthy();
    expect(screen.getByText("READY")).toBeTruthy();
    expect(screen.getByText("INERT (OFF)")).toBeTruthy();
  });
});

describe("NO $ field across /progress sources", () => {
  it("no progress source emits a $/pnl/roi/payout field", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const root = join(dir, "..");
    const files = readdirSync(root).filter(
      (f) => f.endsWith(".ts") || f.endsWith(".tsx"),
    );
    for (const f of files) {
      const src = readFileSync(join(root, f), "utf8");
      // No dollar-amount tokens, no pnl/roi/payout identifiers.
      expect(/\$\d/.test(src), `dollar amount in ${f}`).toBe(false);
      expect(/\bpnl\b|\bpayout\b|\broi\b/i.test(src), `$-field in ${f}`).toBe(
        false,
      );
    }
  });
});
