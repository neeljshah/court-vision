import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BlowoutTiming } from "./BlowoutTiming";
import type { BlowoutTimingSport } from "@/lib/analytics/blowoutTiming";

const sports: BlowoutTimingSport[] = [
  { sport: "mlb", unit: "runs", clockField: "inning", thresholds: [{ threshold: 2, nGamesTotal: 20, nGamesDecided: 10, incidence: 0.5, publishedIncidence: 0.5, masked: false, maskReason: null, p25: 4, median: 6, p75: 8 }] },
  { sport: "soccer_intl", unit: "goals", clockField: "minute", thresholds: [{ threshold: 1, nGamesTotal: 29, nGamesDecided: 14, incidence: 0.482759, publishedIncidence: 0.4828, masked: false, maskReason: null, p25: 22.75, median: 39.5, p75: 56.25 }, { threshold: 2, nGamesTotal: 29, nGamesDecided: 3, incidence: 0.103448, publishedIncidence: 0.1034, masked: true, maskReason: "Below the published minimum of 10 decided games.", p25: null, median: null, p75: null }] },
];

describe("BlowoutTiming", () => {
  it("renders incidence and conditional timing panels for each sport", () => {
    render(<BlowoutTiming sports={sports} />);
    const mlb = screen.getByRole("heading", { name: "MLB" }).closest("section");
    expect(within(mlb as HTMLElement).getByRole("heading", { name: "Incidence" })).toBeInTheDocument();
    expect(within(mlb as HTMLElement).getByRole("heading", { name: "Conditional timing" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "International soccer" })).toBeInTheDocument();
  });

  it("keeps a masked row visibly identified with its reason", () => {
    const { container } = render(<BlowoutTiming sports={sports} />);
    const masked = container.querySelectorAll('[data-masked="true"]');
    expect(masked).toHaveLength(2);
    expect(masked[0]).toHaveClass("bt-is-masked");
    expect(masked[0]).toHaveTextContent("Below the published minimum of 10 decided games.");
  });

  it("states that timing scales are not pooled across innings and minutes", () => {
    render(<BlowoutTiming sports={sports} />);
    expect(screen.getAllByText(/innings and minutes are not combined/i)).toHaveLength(2);
    expect(screen.getAllByText((_, element) => element?.textContent === "Margin unit: runs | Clock field: inning")[0]).toBeInTheDocument();
    expect(screen.getAllByText((_, element) => element?.textContent === "Margin unit: goals | Clock field: minute")[0]).toBeInTheDocument();
  });

  it("keeps decorative bars hidden while retaining the published text values", () => {
    const { container } = render(<BlowoutTiming sports={sports} />);
    const bars = Array.from(container.querySelectorAll(".bt-bar-track"));
    expect(bars.length).toBeGreaterThan(0);
    expect(bars.every(bar => bar.getAttribute("aria-hidden") === "true")).toBe(true);
    expect(screen.getByText("10 / 20 (50.0%)")).toBeInTheDocument();
    expect(screen.getByText("4 inning / 6 inning / 8 inning")).toBeInTheDocument();
  });
});
