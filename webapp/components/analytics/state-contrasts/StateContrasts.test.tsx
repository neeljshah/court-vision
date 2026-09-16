import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StateContrasts } from "./StateContrasts";
import type { StateContrastSport } from "@/lib/analytics/stateContrasts";

const sports: StateContrastSport[] = [
  { sport: "mlb", adjacentTimePairs: [{ id: "early__mid", fromTime: "early", toTime: "mid" }, { id: "mid__late", fromTime: "mid", toTime: "late" }], contrasts: [
    { sport: "mlb", from: { time: "early", probabilityBand: ".2-.4", meanOutcomeFrequency: 0.35, n: 100 }, to: { time: "mid", probabilityBand: ".2-.4", meanOutcomeFrequency: 0.48, n: 120 }, winprobDelta: 0.13, minSupportN: 100 },
    { sport: "mlb", from: { time: "mid", probabilityBand: ".6-.8", meanOutcomeFrequency: 0.70, n: 80 }, to: { time: "late", probabilityBand: ".6-.8", meanOutcomeFrequency: 0.28, n: 90 }, winprobDelta: -0.42, minSupportN: 80 },
  ] },
  { sport: "soccer_intl", adjacentTimePairs: [{ id: "0-15__15-30", fromTime: "0-15", toTime: "15-30" }], contrasts: [
    { sport: "soccer_intl", from: { time: "0-15", probabilityBand: "0-.2", meanOutcomeFrequency: 0.39, n: 109 }, to: { time: "15-30", probabilityBand: "0-.2", meanOutcomeFrequency: 1, n: 41 }, winprobDelta: 0.61, minSupportN: 41 },
  ] },
];

describe("StateContrasts", () => {
  it("filters rows when the adjacent time bucket changes", () => {
    render(<StateContrasts sports={sports} />);
    fireEvent.change(screen.getByLabelText("Adjacent time buckets"), { target: { value: "mid__late" } });
    const table = screen.getByRole("table");
    expect(within(table).getByText("mid / .6-.8")).toBeInTheDocument();
    expect(within(table).queryByText("early / .2-.4")).not.toBeInTheDocument();
  });

  it("keeps all forecast-band contrasts behind an explicit control", () => {
    render(<StateContrasts sports={sports} />);
    const control = screen.getByLabelText("Same forecast band");
    expect(within(control).getByRole("option", { name: "All forecast-band contrasts" })).toBeInTheDocument();
    fireEvent.change(control, { target: { value: "all" } });
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("filters the table when the sport selector changes", () => {
    render(<StateContrasts sports={sports} />);
    fireEvent.change(screen.getByLabelText("State contrast sport"), { target: { value: "soccer_intl" } });
    const table = screen.getByRole("table");
    expect(within(table).getByText("0-15 / 0-.2")).toBeInTheDocument();
    expect(within(table).getByText("15-30 / 0-.2")).toBeInTheDocument();
    expect(within(table).getByText("109")).toBeInTheDocument();
    expect(within(table).getAllByText("41")[0]).toBeInTheDocument();
  });

  it("states the definition that rules out transition and paired-game readings without an independence claim", () => {
    render(<StateContrasts sports={sports} />);
    const definition = screen.getByText(/BETWEEN-BUCKET differences in outcome frequency/i);
    expect(definition).toHaveTextContent("not transition frequencies and not paired movements within individual games");
    expect(definition).toHaveTextContent("does not follow identical games");
    expect(screen.queryByText(/independent published populations/i)).not.toBeInTheDocument();
  });

  it("keeps both populations and the difference together in compact cards, with a full-table control", () => {
    const { container } = render(<StateContrasts sports={sports} />);
    const compact = screen.getByRole("list", { name: "MLB compact state contrasts" });
    expect(within(compact).getByText("From state: early / .2-.4")).toBeInTheDocument();
    expect(within(compact).getByText("To state: mid / .2-.4")).toBeInTheDocument();
    expect(within(compact).getByText((_, element) => Boolean(element?.classList.contains("sc-compact-values") && element.textContent === "Outcome frequency 35.00% | Forecast observations 100"))).toBeInTheDocument();
    expect(within(compact).getByText((_, element) => Boolean(element?.classList.contains("sc-compact-values") && element.textContent === "Outcome frequency 48.00% | Forecast observations 120"))).toBeInTheDocument();
    expect(within(compact).getByText((_, element) => Boolean(element?.classList.contains("sc-compact-delta") && element.textContent === "Difference +13.00 pp | Minimum support 100"))).toBeInTheDocument();
    const control = screen.getByRole("button", { name: "Full table" });
    expect(container.querySelector(".sc-full-table-open")).toBeNull();
    fireEvent.click(control);
    expect(container.querySelector(".sc-full-table-open")).toBeInTheDocument();
    expect(control).toHaveAttribute("aria-expanded", "true");
  });
});
