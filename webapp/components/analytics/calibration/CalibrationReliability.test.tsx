import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import CalibrationReliability from "./CalibrationReliability";
import type { ReliabilitySeries } from "@/lib/analytics/calibrationReliability";

const series: ReliabilitySeries[] = ["mlb", "soccer_intl"].flatMap(sport => (["model", "market"] as const).map(side => ({ sport, side, meta: { nBoot: 1000, ciPct: [2.5, 97.5], clusterUnit: "game_id", minGamesPerBinFloor: 5, asOf: null, nRows: 20, nGames: 5, lowPower: false }, bins: [{ binLo: 0, binHi: 0.1, meanP: side === "model" ? 0.04 : 0.06, meanY: sport === "mlb" ? 0.08 : 0.12, meanYCi: [0.02, 0.15], gap: 0.04, gapCi: [-0.01, 0.09], n: 20, nGames: 5, lowN: false }] })));

describe("CalibrationReliability", () => {
  it("renders the published bins and their table", async () => {
    render(<CalibrationReliability series={series} />);
    expect(await screen.findByTestId("reliability-diagram")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /published reliability bins for mlb/i })).toHaveTextContent("0% to 10%");
    expect(screen.getAllByText("20").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("MLB:")).toBeInTheDocument();
    expect(screen.getByText(/20 ticks from 5 games; ticks are not independent games/i)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /published reliability bins for mlb/i })).toHaveTextContent("Gap (pp)");
    expect(screen.getByRole("table", { name: /published reliability bins for mlb/i })).toHaveTextContent("4.00 pp");
  });

  it("switches sports", async () => {
    render(<CalibrationReliability series={series} />);
    fireEvent.change(await screen.findByLabelText("Reliability sport"), { target: { value: "soccer_intl" } });
    expect(screen.getByRole("table", { name: /international soccer/i })).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toContain("sport=soccer_intl"));
  });

  it("filters the table to one selected series", async () => {
    render(<CalibrationReliability series={series} />);
    fireEvent.click(await screen.findByRole("button", { name: "Model" }));
    const table = screen.getByRole("table", { name: /published reliability bins/i });
    expect(within(table).getAllByText("Model")).toHaveLength(1);
    expect(within(table).queryByText("Market")).not.toBeInTheDocument();
  });
});
