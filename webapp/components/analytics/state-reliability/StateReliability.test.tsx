import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StateReliability } from "./StateReliability";
import type { StateReliabilitySport } from "@/lib/analytics/stateReliability";

const buckets = ["0-.2", ".2-.4", ".4-.6", ".6-.8", ".8-1"];
const sports: StateReliabilitySport[] = [
  { sport: "mlb", artifactDate: null, nForecastObservations: 200, nSkippedNoStateField: 26, nCells: 5, timeBuckets: ["early"], probabilityBuckets: buckets, rows: [
    { sport: "mlb", timeBucket: "early", probabilityBucket: ".8-1", source: "model", n: 5037, meanP: 0.9211, meanY: 0.6853, calibrationError: 0.2357 },
    { sport: "mlb", timeBucket: "early", probabilityBucket: ".8-1", source: "market", n: 2771, meanP: 0.9199, meanY: 0.9405, calibrationError: 0.0206 },
  ] },
  { sport: "soccer_intl", artifactDate: null, nForecastObservations: 100, nSkippedNoStateField: 5, nCells: 5, timeBuckets: ["0-15"], probabilityBuckets: buckets, rows: [
    { sport: "soccer_intl", timeBucket: "0-15", probabilityBucket: ".8-1", source: "model", n: 16, meanP: 0.9211, meanY: 1, calibrationError: 0.0789 },
    { sport: "soccer_intl", timeBucket: "0-15", probabilityBucket: ".8-1", source: "market", n: 18, meanP: 0.8583, meanY: 1, calibrationError: 0.1417 },
  ] },
];

function modelHeaders(): string[] {
  return within(screen.getByLabelText("Model source state grid")).getAllByRole("columnheader").map(header => header.textContent || "");
}

describe("StateReliability", () => {
  it("switches the rendered metric without changing source support", () => {
    render(<StateReliability sports={sports} />);
    const cell = screen.getByTestId("model-early-.8-1");
    expect(within(cell).getByText("-23.58 pp")).toBeInTheDocument();
    expect(within(cell).getByText("n 5,037")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Support (n)" }));
    expect(within(cell).getByText("5,037")).toBeInTheDocument();
  });

  it("renders numeric columns, distinct coverage nouns, scales, and missing cells for both sports", () => {
    render(<StateReliability sports={sports} />);
    expect(modelHeaders()).toEqual(["Time", ...buckets]);
    expect(within(screen.getByTestId("model-early-0-.2")).getByText("not published")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.tagName === "P" && (element.textContent || "").includes("200 forecast observations across 5 cells; 26 skipped without a state field."))).toBeInTheDocument();
    expect(screen.getByText(/signed gap scale/i)).toBeInTheDocument();
    expect(screen.getByText(/support scale/i)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("State reliability sport"), { target: { value: "soccer_intl" } });
    expect(modelHeaders()).toEqual(["Time", ...buckets]);
  });

  it("names the selected sport in its explanation and table", () => {
    render(<StateReliability sports={sports} />);
    fireEvent.change(screen.getByLabelText("State reliability sport"), { target: { value: "soccer_intl" } });
    expect(screen.getByText((_, element) => element?.tagName === "P" && (element.textContent || "").startsWith("Showing Signed gap (pp) for International soccer."))).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /all published state-conditioned rows for international soccer/i })).toBeInTheDocument();
  });
});
