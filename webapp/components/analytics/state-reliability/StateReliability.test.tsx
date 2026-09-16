import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StateReliability } from "./StateReliability";
import type { StateReliabilitySport } from "@/lib/analytics/stateReliability";

const sports: StateReliabilitySport[] = [
  { sport: "mlb", nSkippedNoStateField: 26, timeBuckets: ["late"], probabilityBuckets: [".8-1"], rows: [
    { sport: "mlb", timeBucket: "late", probabilityBucket: ".8-1", source: "model", n: 5037, meanP: 0.9211, meanY: 0.6853, calibrationError: 0.2357 },
    { sport: "mlb", timeBucket: "late", probabilityBucket: ".8-1", source: "market", n: 2771, meanP: 0.9199, meanY: 0.9405, calibrationError: 0.0206 },
  ] },
  { sport: "soccer_intl", nSkippedNoStateField: 5, timeBuckets: ["late"], probabilityBuckets: [".8-1"], rows: [
    { sport: "soccer_intl", timeBucket: "late", probabilityBucket: ".8-1", source: "model", n: 16, meanP: 0.9211, meanY: 1, calibrationError: 0.0789 },
    { sport: "soccer_intl", timeBucket: "late", probabilityBucket: ".8-1", source: "market", n: 18, meanP: 0.8583, meanY: 1, calibrationError: 0.1417 },
  ] },
];

describe("StateReliability", () => {
  it("switches the rendered metric without changing source supports", () => {
    render(<StateReliability sports={sports} />);
    const cell = screen.getByTestId("model-late-.8-1");
    expect(within(cell).getByText("-23.58 pp")).toBeInTheDocument();
    expect(within(cell).getByText(/Model n 5,037 \| Reference n 2,771/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Support (n)" }));
    expect(within(cell).getByText("5,037")).toBeInTheDocument();
  });

  it("names the selected sport in its explanation and table", () => {
    render(<StateReliability sports={sports} />);
    fireEvent.change(screen.getByLabelText("State reliability sport"), { target: { value: "soccer_intl" } });
    expect(screen.getByText((_, element) => element?.tagName === "P" && (element.textContent || "").startsWith("Showing Signed gap (pp) for International soccer."))).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /all published state-conditioned rows for international soccer/i })).toBeInTheDocument();
  });
});
