import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ObservationDependence } from "./ObservationDependence";
import type { DependenceSport } from "@/lib/analytics/observationDependence";

const sports: DependenceSport[] = [
  { sport: "mlb", nRecords: 12, nSeries: 5, sides: [
    { side: "model", values: [0.2, 0.95], nGames: 2, skipped: { lowN: 1, flat: 0 }, median: 0.575, shareAbovePointNine: 0.5 },
    { side: "market", values: [0.1, 0.91, 0.99], nGames: 3, skipped: { lowN: 0, flat: 2 }, median: 0.91, shareAbovePointNine: 2 / 3 },
  ] },
  { sport: "soccer_intl", nRecords: 7, nSeries: 2, sides: [{ side: "model", values: [0.94], nGames: 1, skipped: { lowN: 0, flat: 0 }, median: 0.94, shareAbovePointNine: 1 }] },
];

describe("ObservationDependence", () => {
  it("renders a section for each sport", () => {
    render(<ObservationDependence sports={sports} asOf="2026-09-16" />);
    expect(screen.getByRole("heading", { name: "MLB" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "International soccer" })).toBeInTheDocument();
  });

  it("shows eligible counts and skipped exclusions", () => {
    render(<ObservationDependence sports={sports} />);
    const table = screen.getByRole("table");
    expect(table).toHaveTextContent("2");
    expect(table).toHaveTextContent("low rows 1; flat residuals 0");
    expect(table).toHaveTextContent("low rows 0; flat residuals 2");
  });

  it("renders each side as an independent distribution with no paired dots", () => {
    const { container } = render(<ObservationDependence sports={sports} />);
    const model = container.querySelector('[data-side="model"][data-series-count="2"]');
    const market = container.querySelector('[data-side="market"][data-series-count="3"]');
    expect(model?.querySelectorAll("circle")).toHaveLength(2);
    expect(market?.querySelectorAll("circle")).toHaveLength(3);
    expect(within(screen.getAllByRole("figure")[0]).getByText(/dots are not paired/i)).toBeInTheDocument();
  });

  it("reports each present side's eligible-series count in the figure caption", () => {
    render(<ObservationDependence sports={sports} asOf="2026-09-16" />);
    const [mlb, soccer] = screen.getAllByRole("figure").map(figure => figure.querySelector("figcaption")!);
    expect(within(mlb).getByText("Model: 2 eligible series; Market: 3 eligible series")).toBeInTheDocument();
    expect(within(soccer).getByText("Model: 1 eligible series")).toBeInTheDocument();
    expect(soccer).not.toHaveTextContent("Market:");
    expect(mlb).not.toHaveTextContent("n not published");
    expect(soccer).not.toHaveTextContent("n not published");
  });
});
