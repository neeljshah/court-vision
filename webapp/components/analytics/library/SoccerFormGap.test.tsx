import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getSoccerFormGapResearch } from "@/lib/analytics/researchSoccerFormGap";
import ResearchDetail from "./ResearchDetail";
import * as table from "../lab/LabTable";

const analysis = getSoccerFormGapResearch()[0];

beforeEach(() => window.history.replaceState(null, "", `/analytics/research/${analysis.id}/`));
afterEach(() => vi.restoreAllMocks());

describe("Published soccer home-away form investigation", () => {
  it("keeps all public venue operands, signed gaps, provenance, and CSV limits together", () => {
    expect(analysis).toMatchObject({ id: "soccer-home-away-trailing-form-gap", title: "Soccer form: home versus away" });
    expect(analysis.rows).toHaveLength(187);
    expect(analysis.rows.find(row => row.label === "Brest")?.values).toMatchObject({ home_minus_away_ppg: 1.3, ppg_home_l10: 1.9, ppg_away_l10: 0.6 });
    expect(analysis.rows.find(row => row.label === "Bologna")?.values).toMatchObject({ home_minus_away_ppg: -1.5, ppg_home_l10: 0.7, ppg_away_l10: 2.2 });
    expect(analysis.rows.find(row => row.label === "Chelsea")?.values.home_minus_away_ppg).toBe(0);
    expect(analysis.rows.find(row => row.label === "Brest")?.sourcePaths).toEqual([
      "entries[].key_numbers.ppg_home_l10", "entries[].key_numbers.ppg_away_l10",
    ]);

    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("combobox", { name: "Order" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Order" })).toHaveTextContent("Published source order");
    expect(screen.getByRole("region", { name: "Population comparison notice" })).toHaveTextContent(analysis.populationDefinition?.reason || "");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Scrollable measurements" })).getAllByRole("button", { name: /^Inspect / }).slice(0, 3).map(button => button.getAttribute("aria-label"))).toEqual([
      "Inspect Ajaccio", "Inspect Ajaccio GFCO", "Inspect Alaves",
    ]);
    fireEvent.change(screen.getByRole("textbox", { name: "Search analysis rows" }), { target: { value: "Brest" } });
    fireEvent.click(screen.getByRole("button", { name: "Inspect Brest" }));
    const selected = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(selected).queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    expect(within(within(selected).getByText("Home minus away PPG").parentElement!).getByText("1.3")).toBeVisible();
    expect(within(within(selected).getByText("Home PPG, prior 10").parentElement!).getByText("1.9")).toBeVisible();
    expect(within(within(selected).getByText("Away PPG, prior 10").parentElement!).getByText("0.6")).toBeVisible();
    const provenance = within(selected).getByRole("region", { name: "Calculation inputs" });
    expect(provenance).toHaveTextContent("1.9");
    expect(provenance).toHaveTextContent("0.6");
    expect(provenance).not.toHaveTextContent("Unavailable");
    expect(within(provenance).getByText("entries[].key_numbers.ppg_home_l10")).toBeInTheDocument();
    expect(within(provenance).getByText("entries[].key_numbers.ppg_away_l10")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    const [dataset, rows] = exportCSV.mock.calls[0];
    expect(rows).toHaveLength(1);
    expect(rows[0].values).toMatchObject({ home_minus_away_ppg: 1.3, ppg_home_l10: 1.9, ppg_away_l10: 0.6 });
    const csv = table.buildLabCSV(dataset, rows);
    for (const text of ["Brest", "atlas_soccer_manifest", analysis.scope, analysis.caveat, analysis.formula]) expect(csv).toContain(text);
  });

  it("restores a shared Bologna table investigation with its selected operand", () => {
    window.history.replaceState(null, "", "?q=Bologna&view=table&metric=ppg_away_l10&utm_source=shared");
    render(<ResearchDetail analysis={analysis} related={[]} />);

    expect(screen.getByRole("textbox", { name: "Search analysis rows" })).toHaveValue("Bologna");
    expect(screen.getByRole("combobox", { name: "Measurement" })).toHaveValue("ppg_away_l10");
    expect(screen.getByRole("button", { name: "Data table" })).toHaveAttribute("aria-pressed", "true");
    const measurements = screen.getByRole("region", { name: "Scrollable measurements" });
    for (const value of ["-1.5", "0.7", "2.2"]) expect(within(measurements).getByText(value)).toBeVisible();
    expect(new URLSearchParams(window.location.search).get("utm_source")).toBe("shared");
  });

  it("does not restore pooled charts or positions from an old URL", () => {
    window.history.replaceState(null, "", "?population=sport%3Dsoccer&view=distribution&row=soccer-form-gap-brest");
    render(<ResearchDetail analysis={analysis} related={[]} />);
    expect(screen.getByRole("region", { name: "Population comparison notice" })).toHaveTextContent("comparable population cannot be verified");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement distribution" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement context" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Data table" }));
    expect(screen.getByRole("region", { name: "Scrollable measurements" })).toBeVisible();
  });
});
