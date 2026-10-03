import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ClvScoreboard as Clv } from "@/lib/p5api";
import { ClvScoreboard } from "../ClvScoreboard";

afterEach(cleanup);

// Public demo-data/api_paper_clv.json values are already percentages.
// Render assertions guard against treating percent-valued fields as fractions.
const PUBLIC_CLV: Clv = {
  n_bets: 1233,
  pct_beat_close: 36.3341,
  mean_clv_pct: 4.368363,
  median_clv_pct: -3.182161,
  basis: "true_close",
  n_proxy: 264,
  clv_is_proxy: true,
  by_sport: {
    mlb: { n: 1115, pct_beat_close: 34.4395, mean_clv_pct: 3.421528 },
    soccer_intl: { n: 4, pct_beat_close: 100, mean_clv_pct: 26.011333 },
  },
};

function headline(label: string): HTMLElement {
  const stat = screen.getByText(label, { selector: "div" }).parentElement;
  if (!stat) throw new Error(`Missing stat container for ${label}`);
  return stat;
}

describe("ClvScoreboard percentage units", () => {
  it.each([
    ["% beat close", "36.3%"],
    ["Mean CLV", "+4.4%"],
  ])("renders public %s without multiplying by 100", (label, expected) => {
    render(<ClvScoreboard clv={PUBLIC_CLV} />);
    expect(within(headline(label)).getByText(expected)).toBeInTheDocument();
  });

  it("preserves the sign and scale of the negative public median", () => {
    render(<ClvScoreboard clv={PUBLIC_CLV} />);
    expect(screen.getByText(/median CLV \(true-close\): -3\.2%/)).toBeInTheDocument();
  });

  it.each([
    ["mlb", "34.4%", "+3.4%"],
    ["soccer_intl", "100.0%", "+26.0%"],
  ])("preserves public %s rate and mean units", (sport, rate, mean) => {
    render(<ClvScoreboard clv={PUBLIC_CLV} />);
    const row = screen.getByRole("row", { name: new RegExp(sport) });
    expect(within(row).getByText(rate)).toBeInTheDocument();
    expect(within(row).getByText(mean)).toBeInTheDocument();
  });

  it.each([
    { value: 100, rate: "100.0%", mean: "+100.0%" },
    { value: 0, rate: "0.0%", mean: "0.0%" },
    { value: 0.4, rate: "0.4%", mean: "+0.4%" },
    { value: null, rate: "--", mean: "--" },
  ])("preserves boundary percentage $value and missing values", ({ value, rate, mean }) => {
    render(
      <ClvScoreboard
        clv={{
          ...PUBLIC_CLV,
          pct_beat_close: value,
          mean_clv_pct: value,
          median_clv_pct: null,
          by_sport: {
            nba: { n: 1, pct_beat_close: value, mean_clv_pct: value },
          },
        }}
      />,
    );
    expect(within(headline("% beat close")).getByText(rate)).toBeInTheDocument();
    expect(within(headline("Mean CLV")).getByText(mean)).toBeInTheDocument();
    const cells = within(screen.getByRole("row", { name: /nba/ })).getAllByRole("cell");
    expect(cells[2]).toHaveTextContent(rate);
    expect(cells[3]).toHaveTextContent(mean);
    expect(screen.queryByText(/median CLV/)).not.toBeInTheDocument();
  });
});
