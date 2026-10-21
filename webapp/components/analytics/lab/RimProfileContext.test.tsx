import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { establishedDatasets } from "@/lib/analytics/labEstablished";
import { labComparisonPolicy } from "@/lib/analytics/labComparisonPolicy";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const dataset = establishedDatasets().find(item => item.id === "rim-deterrence")!;
const data = { datasets: [dataset], novel: [] };
// Cohort keys are built from every published definition field, so read them from the policy rather than spelling them out.
const cohortKey = (season: string) => labComparisonPolicy(dataset.rows).cohorts.find(cohort => cohort.definition.season === season)!.key;
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=rim-deterrence&field=relative_rim_share_difference&view=table"));
afterEach(() => vi.restoreAllMocks());

describe("rim profile context", () => {
  it("isolates one season by default and suppresses pooled summaries across seasons", () => {
    window.history.replaceState(null, "", "/analytics/lab?dataset=rim-deterrence");
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("status")).toHaveTextContent("15 rows");
    expect(screen.getByLabelText("Published group")).toHaveValue(cohortKey("2025-26"));
    const definition = screen.getByRole("region", { name: "Published definition" });
    expect(within(definition).getByText("2025-26")).toBeInTheDocument();
    expect(within(definition).getByText("Sport").nextElementSibling).toHaveTextContent("NBA");
    expect(within(definition).getByText("Population").nextElementSibling).toHaveTextContent("370 qualified players; 500 on-court minute floor");
    expect(within(definition).getByText("Observation window").nextElementSibling).toHaveTextContent("2025-26 (complete NBA season)");
    fireEvent.change(screen.getByLabelText("Published group"), { target: { value: "all" } });
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(window.location.search).toContain("allCohorts=true");
    window.history.replaceState(null, "", "/analytics/lab?dataset=rim-deterrence&allCohorts=true");
    act(() => window.dispatchEvent(new PopStateEvent("popstate")));
    expect(screen.getByLabelText("Published group")).toHaveValue("all");
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
  });

  it("restores a selected cohort from the lab URL", () => {
    window.history.replaceState(null, "", `/analytics/lab?${new URLSearchParams({ dataset: "rim-deterrence", cohort: cohortKey("2024-25") })}`);
    render(<MeasurementLab data={data} />);
    expect(screen.getByLabelText("Published group")).toHaveValue(cohortKey("2024-25"));
    expect(screen.getByRole("status")).toHaveTextContent("15 rows");
    expect(new URLSearchParams(window.location.search).get("cohort")).toBe(cohortKey("2024-25"));
  });

  it("distinguishes relative percentages from percentage points and keeps source support visible", () => {
    render(<MeasurementLab data={data} />);
    expect(screen.getByRole("combobox", { name: "Primary measurement" })).toHaveValue("relative_rim_share_difference");
    expect(screen.getByRole("combobox", { name: "Published group" })).toHaveValue(cohortKey("2025-26"));
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "Victor Wembanyama" } });
    const measurements = screen.getByRole("table");
    expect(within(measurements).getByRole("cell", { name: "-6.18 pp" })).toBeInTheDocument();
    expect(within(measurements).getByRole("cell", { name: "-19.82%" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect Victor Wembanyama" }));
    const details = screen.getByRole("region", { name: "Selected measurement" });
    expect(details).toHaveTextContent("seasons[0].leaders[0]");
    expect(details).toHaveTextContent("370");
    expect(details).toHaveTextContent("500");
    expect(details).toHaveTextContent(/shot-attempt counts/i);
    expect(details).toHaveTextContent(/off-court minutes/i);
    fireEvent.change(screen.getByRole("combobox", { name: "Published group" }), { target: { value: cohortKey("2024-25") } });
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "Rudy Gobert" } });
    expect(within(screen.getByRole("table")).getByRole("cell", { name: "-18.5%" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect Rudy Gobert" }));
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("seasons[1].leaders[0]");
    expect(screen.getByRole("region", { name: "Selected measurement" })).toHaveTextContent("387");
  });

  it("exports all selected player-seasons with their original deltas and source-specific context", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    expect(exportCSV.mock.calls[0][1]).toHaveLength(15);
    fireEvent.change(screen.getByRole("combobox", { name: "Published group" }), { target: { value: "all" } });
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const rows = exportCSV.mock.calls[1][1];
    expect(rows).toHaveLength(30);
    expect(rows[0].values.delta).toBe(-0.0618);
    expect(rows[0].values.relative_rim_share_difference).toBe((0.25 - 0.3118) / 0.3118);
    expect(rows[15].values.relative_rim_share_difference).toBe((0.2785 - 0.3417) / 0.3417);
    const csv = table.buildLabCSV(dataset, rows);
    expect(csv).toContain("Relative rim-share difference (percent; raw value)");
    expect(csv).toContain("seasons[0].leaders[0]");
    expect(csv).toContain("seasons[1].leaders[0]");
    expect(csv).toContain("370");
    expect(csv).toContain("387");
  });
});
