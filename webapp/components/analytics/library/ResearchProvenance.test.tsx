import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildComebackAtlasResearch } from "@/lib/analytics/researchComebackAtlas";
import type { ResearchAnalysis } from "@/lib/analytics/researchTypes";
import { ResearchProvenance } from "./ResearchProvenance";

const fields = [
  { key: "result", label: "Result", unit: "number" as const },
  { key: "numerator", label: "Numerator", unit: "number" as const },
  { key: "denominator", label: "Denominator", unit: "number" as const },
];
const boundAnalysis: ResearchAnalysis = {
  id: "test", title: "Test", sport: "nba", category: "Test", source: "test", description: "Test", scope: "Test", caveat: "Test", status: "Test", fields, rows: [], formula: "Result = numerator / denominator", interpretation: "Test", references: [], novelty: "Derived analysis",
  bindings: [
    { operand: "Result", sourcePath: "cells[].result", valueKey: "result", label: "Result" },
    { operand: "numerator", sourcePath: "cells[].numerator", valueKey: "numerator", label: "Numerator" },
    { operand: "denominator", sourcePath: "cells[].denominator", valueKey: "denominator", label: "Denominator" },
  ],
};

describe("ResearchProvenance", () => {
  it("puts exact row paths beside the corresponding input without duplicating them", () => {
    render(<ResearchProvenance analysis={boundAnalysis} fields={fields} resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: 4 }, sourcePaths: ["cells[3].numerator", "cells[3].denominator"] }} />);
    for (const label of ["Numerator", "Denominator"]) {
      fireEvent.click(within(screen.getByText(label, { exact: true }).parentElement!).getByText("Source path"));
    }
    expect(screen.getByText("cells[3].numerator")).toBeVisible();
    expect(screen.getByText("cells[3].denominator")).toBeVisible();
    expect(screen.queryByText("Published row fields")).not.toBeInTheDocument();
    expect(screen.getByText("Result (2) = numerator (8) / denominator (4)")).toBeVisible();
  });

  it("preserves field-aware percentages and formula substitution when paths become exact", () => {
    const percentFields = [{ key: "rate", label: "Rate", unit: "percent" as const, digits: 1 }];
    const analysis = { ...boundAnalysis, fields: percentFields, formula: "Result = rate", bindings: [
      { operand: "rate", sourcePath: "cells[].share", valueKey: "rate", label: "Published rate" },
    ] };
    render(<ResearchProvenance analysis={analysis} fields={percentFields} resultField={percentFields[0]} row={{ id: "r", label: "R", group: "Test", values: { rate: 0.125 }, sourcePaths: ["cells[4].share", "cells[4].date"] }} />);
    const input = screen.getByText("Published rate", { exact: true }).parentElement!;
    expect(input).toHaveTextContent("12.5%");
    fireEvent.click(within(input).getByText("Source path"));
    expect(within(input).getByText("cells[4].share")).toBeVisible();
    expect(screen.getByText("Result = rate (12.5%)")).toBeVisible();
    fireEvent.click(screen.getByText("Published row fields"));
    expect(screen.getByText("cells[4].date")).toBeVisible();
    expect(screen.getAllByText("cells[4].share")).toHaveLength(1);
  });

  it("renders exact binding paths and substitutes only their published values", () => {
    render(<ResearchProvenance analysis={boundAnalysis} fields={fields} resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: 4 }, sourcePaths: ["cells[].numerator", "cells[].denominator"] }} />);
    expect(screen.getByLabelText("Calculation inputs")).toHaveTextContent("Numerator8");
    expect(screen.getByText("cells[].numerator")).toBeInTheDocument();
    expect(screen.getByText("Result (2) = numerator (8) / denominator (4)")).toBeInTheDocument();
  });

  it("leaves the formula unsubstituted and exposes an unresolved input", () => {
    render(<ResearchProvenance analysis={boundAnalysis} fields={fields} resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: null }, sourcePaths: ["cells[].numerator", "cells[].denominator"] }} />);
    expect(screen.getByText("not published for this row")).toBeInTheDocument();
    expect(screen.getByText("Result = numerator / denominator")).toBeInTheDocument();
  });

  it("lists source paths without substituting when an analysis has no bindings", () => {
    const unbound = { ...boundAnalysis, bindings: undefined };
    render(<ResearchProvenance analysis={unbound} fields={fields} resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: 4 }, sourcePaths: ["cells[].numerator"] }} />);
    expect(screen.getByText("cells[].numerator")).toBeInTheDocument();
    expect(screen.getByText("Result = numerator / denominator")).toBeInTheDocument();
  });

  it("uses the comeback row's own time and deficit bands with the exact published operands", () => {
    const analysis = buildComebackAtlasResearch({ cells: [{ lead_band: "lead_+01_05", time_band: "rem_00_02", outcome_rate: 0.8, n_games: 40, n_ticks: 200, masked_n_lt_30: false }] })[0];
    render(<ResearchProvenance analysis={analysis} fields={analysis.fields} resultField={analysis.fields[0]} row={analysis.rows[0]} />);
    expect(screen.getByText("Time band").parentElement).toHaveTextContent("0-2 remaining");
    expect(screen.getByText("Deficit band").parentElement).toHaveTextContent("Deficit 1-5");
    expect(screen.getByText("Displayed comeback share = 1 - outcome_rate (80%). lead_band (Deficit 1-5) and time_band (0-2 remaining) identify the published source cell; n_games (40) and n_ticks (200) report its support.")).toBeInTheDocument();
  });

  it("renders nothing when the analysis did not record provenance", () => {
    const { container } = render(<ResearchProvenance analysis={boundAnalysis} fields={fields} resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: 4 } }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
