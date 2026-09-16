import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResearchProvenance } from "./ResearchProvenance";

const fields = [
  { key: "result", label: "Result", unit: "number" as const },
  { key: "numerator", label: "Numerator", unit: "number" as const },
  { key: "denominator", label: "Denominator", unit: "number" as const },
];

describe("ResearchProvenance", () => {
  it("renders exact published paths and matched operand values", () => {
    render(<ResearchProvenance fields={fields} formula="Result = Numerator / Denominator" resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: 4 }, sourcePaths: ["cells[].numerator", "cells[].denominator"] }} />);
    expect(screen.getByLabelText("Calculation inputs")).toHaveTextContent("Numerator8");
    expect(screen.getByText("cells[].numerator")).toBeInTheDocument();
    expect(screen.getByText("cells[].denominator")).toBeInTheDocument();
    expect(screen.getByText("cells[].numerator").closest("details")?.parentElement?.tagName).toBe("DD");
  });

  it("renders nothing when the analysis did not record provenance", () => {
    const { container } = render(<ResearchProvenance fields={fields} formula="Result = Numerator / Denominator" resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: 4 } }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the selected result beside a formula with its operands substituted", () => {
    render(<ResearchProvenance fields={fields} formula="Result = Numerator / Denominator" resultField={fields[0]} row={{ id: "row", label: "Row", group: "Test", values: { result: 2, numerator: 8, denominator: 4 }, sourcePaths: ["cells[].numerator"] }} />);
    expect(screen.getByText("Result: 2")).toBeInTheDocument();
    expect(screen.getByText("Result (2) = Numerator (8) / Denominator (4)")).toBeInTheDocument();
  });
});
