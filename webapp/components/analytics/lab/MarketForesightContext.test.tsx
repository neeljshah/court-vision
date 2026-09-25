import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getLabData } from "@/lib/analytics/labData";
import MeasurementLab from "./MeasurementLab";
import * as table from "./LabTable";

const published = getLabData();
const dataset = published.datasets.find(item => item.id === "market-foresight")!;
const data = { datasets: [dataset], novel: [] };
beforeEach(() => window.history.replaceState(null, "", "/analytics/lab/?dataset=market-foresight&view=table&allCohorts=1"));
afterEach(() => vi.restoreAllMocks());

describe("market foresight source context", () => {
  it("separates game clocks from unknown observation dates and keeps source details inspectable", () => {
    render(<MeasurementLab data={data} />);
    const definition = screen.getByRole("region", { name: "Published definition" });
    expect(within(definition).getByText("Observation window").nextElementSibling).toHaveTextContent("Not published");
    expect(within(definition).getByText("Clock unit").nextElementSibling).toHaveTextContent("inning");
    expect(within(definition).getByText("Clock unit").nextElementSibling).toHaveTextContent("minute");
    expect(screen.getByText(dataset.scope)).toHaveTextContent("2026-09-17");
    expect(screen.getByRole("status")).toHaveTextContent("29 rows");
    expect(screen.getByRole("columnheader", { name: "Game-clock checkpoint" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Closing reference skill vs. naive" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Measurement summary" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Rank order" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Inspect MLB / 1" }));
    const detail = screen.getByRole("region", { name: "Selected measurement" });
    expect(detail).toHaveTextContent("results.mlb.checkpoints[0]");
    expect(detail).toHaveTextContent(/entropy.*floor.*no/i);
    expect(detail).toHaveTextContent("3,589");
  });

  it("exports filtered observations with clock units and row provenance, without invented dates", () => {
    const exportCSV = vi.spyOn(table, "exportLabCSV").mockImplementation(() => undefined);
    render(<MeasurementLab data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const allRows = exportCSV.mock.calls[0][1];
    expect(allRows).toHaveLength(29);
    expect(allRows.every(row => row.definition?.observationWindow === undefined)).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "Search measurement rows" }), { target: { value: "INTERNATIONAL SOCCER" } });
    fireEvent.click(screen.getByRole("button", { name: "Export rows" }));
    const soccer = exportCSV.mock.calls[1][1];
    expect(soccer).toHaveLength(19);
    expect(soccer.map(row => row.values.checkpoint)).toEqual(Array.from({ length: 19 }, (_, index) => index * 5));
    expect(soccer.at(-1)?.values.n).toBe(33);
    const csv = table.buildLabCSV(dataset, soccer);
    expect(csv).toContain(dataset.scope);
    expect(csv).toContain("results.soccer_intl.checkpoints[18]");
    expect(csv).toContain("90+");
    expect(csv).not.toContain("observationWindow");
    expect(csv).not.toContain("Checkpoints 0 to 90");
  });

  it("plots source checkpoints within one clock and preserves the sample count on inspection", () => {
    render(<MeasurementLab data={data} />);
    const mlb = screen.getByRole("option", { name: /^MLB \/ inning/ }) as HTMLOptionElement;
    fireEvent.change(screen.getByRole("combobox", { name: "Published group" }), { target: { value: mlb.value } });
    fireEvent.change(screen.getByRole("combobox", { name: "Primary measurement" }), { target: { value: "checkpoint" } });
    fireEvent.click(screen.getByRole("button", { name: "Scatter plot" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Vertical measurement" }), { target: { value: "mfp" } });
    const plot = screen.getByRole("group", { name: /Market foresight premium against Game-clock checkpoint/ });
    expect(within(plot).getAllByRole("button")).toHaveLength(10);
    fireEvent.keyDown(within(plot).getByRole("button", { name: /^Inspect MLB \/ 10:/ }), { key: "Enter" });
    const detail = screen.getByRole("region", { name: "Selected measurement" });
    expect(within(detail).getByRole("heading", { name: "MLB / 10" })).toBeInTheDocument();
    expect(within(detail).getByText("Checkpoint observations").nextElementSibling).toHaveTextContent("46");
    expect(detail).toHaveTextContent("results.mlb.checkpoints[9]");
  });
});
