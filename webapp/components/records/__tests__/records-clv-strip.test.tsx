import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

// records-clv-strip.test.tsx -- W2-records-clv-deep per-file test.
//
// Acceptance assertions:
//   1. Renders INSUFFICIENT_DATA when n_bets=0 (never fabricated CLV%).
//   2. Renders mean_clv_pct when n_bets>0 (real value surfaced).
//   3. No '$' token in output.
//   4. Renders INSUFFICIENT_DATA when clv is null (loading/unavailable).
//   5. CLV is proxy -> shows "(proxy close)" note.
//   6. Negative mean_clv_pct rendered with minus sign.

import { RecordsClvStrip } from "../RecordsClvStrip";
import type { ClvScoreboard, Unavailable } from "@/lib/types";

function makeClv(overrides: Partial<ClvScoreboard> = {}): ClvScoreboard {
  return {
    n_bets:         0,
    pct_beat_close: null,
    mean_clv_pct:   null,
    by_sport:       null,
    clv_is_proxy:   false,
    note:           undefined,
    ...overrides,
  };
}

describe("RecordsClvStrip -- INSUFFICIENT_DATA when n_bets=0", () => {
  it("renders INSUFFICIENT_DATA when n_bets is 0", () => {
    render(<RecordsClvStrip clv={makeClv({ n_bets: 0 })} />);
    expect(screen.getByTestId("clv-strip-insufficient")).toBeInTheDocument();
    expect(screen.getByTestId("clv-strip-insufficient").textContent).toContain(
      "INSUFFICIENT_DATA",
    );
  });

  it("does NOT render mean_clv_pct cell when n_bets=0", () => {
    render(<RecordsClvStrip clv={makeClv({ n_bets: 0 })} />);
    expect(screen.queryByTestId("clv-strip-mean-clv")).not.toBeInTheDocument();
  });

  it("renders INSUFFICIENT_DATA when clv is null", () => {
    render(<RecordsClvStrip clv={null} />);
    expect(screen.getByTestId("clv-strip-insufficient")).toBeInTheDocument();
  });

  it("renders INSUFFICIENT_DATA when clv is unavailable sentinel", () => {
    const unavail: Unavailable = { status: "unavailable", reason: "service down" };
    render(<RecordsClvStrip clv={unavail} />);
    expect(screen.getByTestId("clv-strip-insufficient")).toBeInTheDocument();
  });
});

describe("RecordsClvStrip -- real data when n_bets>0", () => {
  it("renders mean_clv_pct as +X.X% when n_bets>0 and positive", () => {
    render(
      <RecordsClvStrip
        clv={makeClv({ n_bets: 12, mean_clv_pct: 0.025, pct_beat_close: 0.6 })}
      />,
    );
    const meanCell = screen.getByTestId("clv-strip-mean-clv");
    expect(meanCell.textContent).toContain("+2.5%");
    // Must not show INSUFFICIENT_DATA
    expect(screen.queryByTestId("clv-strip-insufficient")).not.toBeInTheDocument();
  });

  it("renders mean_clv_pct as -X.X% when negative", () => {
    render(
      <RecordsClvStrip
        clv={makeClv({ n_bets: 5, mean_clv_pct: -0.015, pct_beat_close: 0.4 })}
      />,
    );
    const meanCell = screen.getByTestId("clv-strip-mean-clv");
    expect(meanCell.textContent).toContain("-1.5%");
  });

  it("renders pct_beat_close as a percentage", () => {
    render(
      <RecordsClvStrip
        clv={makeClv({ n_bets: 10, mean_clv_pct: 0.01, pct_beat_close: 0.6 })}
      />,
    );
    const beatCell = screen.getByTestId("clv-strip-beat-close");
    expect(beatCell.textContent).toContain("60.0%");
  });

  it("shows n_bets count in graded-bets cell", () => {
    render(
      <RecordsClvStrip
        clv={makeClv({ n_bets: 97, mean_clv_pct: 0.02, pct_beat_close: 0.55 })}
      />,
    );
    const nCell = screen.getByTestId("clv-strip-graded-bets");
    expect(nCell.textContent).toContain("97");
  });

  it("shows proxy note when clv_is_proxy is true", () => {
    render(
      <RecordsClvStrip
        clv={makeClv({
          n_bets: 5,
          mean_clv_pct: 0.01,
          pct_beat_close: 0.5,
          clv_is_proxy: true,
        })}
      />,
    );
    // Should mention proxy somewhere in the strip
    expect(screen.getByTestId("records-clv-strip").textContent).toContain("proxy");
  });
});

describe("RecordsClvStrip -- no $ token anywhere", () => {
  it("renders no $ token when n_bets=0", () => {
    const { container } = render(<RecordsClvStrip clv={makeClv({ n_bets: 0 })} />);
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });

  it("renders no $ token when n_bets>0 with real CLV", () => {
    const { container } = render(
      <RecordsClvStrip
        clv={makeClv({ n_bets: 20, mean_clv_pct: 0.03, pct_beat_close: 0.65 })}
      />,
    );
    expect(/\$\s*\d/.test(container.textContent ?? "")).toBe(false);
  });
});

describe("RecordsClvStrip -- loading skeleton", () => {
  it("renders records-clv-strip testid in loading state", () => {
    render(<RecordsClvStrip clv={null} loading />);
    expect(screen.getByTestId("records-clv-strip")).toBeInTheDocument();
  });
});
