import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import MeasurementLab from "./MeasurementLab";
import type { LabData } from "@/lib/analytics/labTypes";

const data: LabData = {
  datasets: [{
    id: "clear", title: "Clear dataset", sport: "nba", category: "Fixture", source: "clear-source", description: "Clear source.", scope: "Fixture scope.", caveat: "Fixture caveat.", status: "Descriptive",
    fields: [{ key: "value", label: "Value", unit: "number" }], rows: [{ id: "row", label: "Row", group: "Published", values: { value: 1 } }],
  }],
  novel: [
    { stat_name: "Live Clock Fraction", abbrev: "LCF", module: "novel_live_clock_fraction", formula: "live clock / total", prior_art_verdict: "incremental", headline: "Published timing measurement." },
    { stat_name: "Clear card", abbrev: "CLR", module: "novel_line_half_life", formula: "clear formula", prior_art_verdict: "incremental", headline: "Clear measurement." },
  ],
};

describe("MeasurementLab novel integrity notices", () => {
  beforeEach(() => window.history.replaceState(null, "", "/analytics/lab"));

  it("labels an affected novel card before its headline and leaves clear cards unmarked", () => {
    render(<MeasurementLab data={data} />);
    const affected = screen.getByRole("heading", { name: "Live Clock Fraction" }).closest("article");
    const clear = screen.getByRole("heading", { name: "Clear card" }).closest("article");
    expect(affected).not.toBeNull();
    expect(clear).not.toBeNull();
    const notice = within(affected!).getByRole("complementary", { name: "Data integrity" });
    expect(notice).toHaveTextContent("MLB/soccer rows are under review");
    expect(notice.compareDocumentPosition(within(affected!).getByRole("heading", { name: "Live Clock Fraction" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(clear!).queryByRole("complementary", { name: "Data integrity" })).not.toBeInTheDocument();
  });
});
