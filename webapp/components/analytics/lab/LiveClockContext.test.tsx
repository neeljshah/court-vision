import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getLabData } from "@/lib/analytics/labData";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const published = getLabData();
const dataset = published.datasets.find(item => item.id === "live-clock")!;
const data = { datasets: [dataset], novel: published.novel.filter(card => [dataset.source, "novel_market_foresight_premium"].includes(card.module)) };
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=live-clock&mode=table&allCohorts=1"));
afterEach(() => vi.restoreAllMocks());

describe("live-clock source context", () => {
  it("separates eligible samples from the stored corpus and uses the current card headline", () => {
    render(<MeasurementLab data={data} />);
    const measurements = screen.getByRole("table");
    expect(within(measurements).getByRole("cell", { name: "174" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "26" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "73.68%" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "59.94%" })).toBeInTheDocument();
    expect(screen.getByText(dataset.scope)).toHaveTextContent("174");
    expect(screen.getByText(dataset.scope)).toHaveTextContent("26");
    expect(screen.getByText(dataset.scope)).toHaveTextContent("2026-09-17");
    const card = screen.getByRole("heading", { name: "Live-Clock Fraction", level: 3 }).closest("article")!;
    expect(card).toHaveTextContent("LCF 0.7368 at 3 runs");
    expect(card).toHaveTextContent("LCF 0.5994 at 1 goals");
    expect(card).toHaveTextContent("these values do not rank sports");
    expect(card).not.toHaveTextContent("0.833");
    expect(within(card).getByRole("complementary", { name: "Data integrity" })).toHaveTextContent("stored corpus contains 178 MLB and 27");
    const foresightCard = screen.getByRole("heading", { name: "Market Foresight Premium", level: 3 }).closest("article")!;
    expect(foresightCard).toHaveTextContent("MFP 0.411 (46 checkpoint observations)");
    expect(foresightCard).toHaveTextContent("do not establish an in-game trend");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Rank order" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Inspect MLB" }));
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("results[0]");
  });

  it("exports current denominators and indexed provenance with the same scope", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const rows = exportCSV.mock.calls[0][1];
    expect(rows).toHaveLength(2);
    expect(rows.map(row => row.values.n_games_total)).toEqual([174, 26]);
    expect(rows.map(row => row.values.live_clock_fraction)).toEqual([0.7368, 0.5994]);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain(dataset.scope);
    expect(csv).toContain("results[0]");
    expect(csv).toContain("results[1]");
    expect(csv).not.toContain("178 games");
    expect(csv).not.toContain("29 games");
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "INTERNATIONAL SOCCER" } });
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    expect(exportCSV.mock.calls[1][1].map(row => row.values.n_games_decided)).toEqual([12]);
  });
});
