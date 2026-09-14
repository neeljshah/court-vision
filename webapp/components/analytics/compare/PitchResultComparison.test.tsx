import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ComparisonEntity } from "@/lib/analytics/comparisonData";
import { PitchResultComparison } from "./PitchResultComparison";

const a: ComparisonEntity = { slug: "ff", sourceEntity: "pitch_type:FF", name: "pitch type FF", asOf: "2025-09-28", floors: "2025 historical snapshot", values: { n_pitches: 220235, outcome_mix_pct: { ball: 36.1, strike: 44, "in-play": 20 } }, percentiles: {} };
const b: ComparisonEntity = { slug: "sc", sourceEntity: "pitch_type:SC", name: "pitch type SC", asOf: "2025-09-28", floors: "n=7 has high sampling noise", values: { n_pitches: 7, outcome_mix_pct: { ball: 0, "in-play": 100.1 } }, percentiles: {} };
const sourceHref = "/data/showcase/atlas_mlb_pitch_manifest.json";

describe("PitchResultComparison", () => {
  it("shows fixed-scale published values, including zero and an unserialized category", () => {
    render(<PitchResultComparison a={a} b={b} sourceHref={sourceHref} />);
    expect(screen.getByRole("heading", { name: "Recorded pitch-result mix" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Published pitch-result shares" })).toBeInTheDocument();
    expect(screen.getAllByText("0.0%")).toHaveLength(2);
    expect(screen.getAllByText("20.0%")).toHaveLength(2);
    expect(screen.getAllByText("Not published")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "pitch type SC Ball: 0.0%" }).querySelector("i")).toHaveStyle({ width: "0%" });
    expect(screen.getByRole("img", { name: "pitch type FF Strike: 44.0%" }).querySelector("i")).toHaveStyle({ width: "44%" });
    expect(screen.getByText(/Statcast type codes: B = ball, S = strike, X = in play/)).toBeInTheDocument();
    expect(screen.getByText("Categories are rounded independently to one decimal place. Missing categories have no published value.")).toBeVisible();
    expect(screen.getByText("Source cutoff: 2025-09-28")).toBeVisible();
    const warning = document.querySelector<HTMLElement>(".pitch-result-source-note");
    expect(warning).toHaveTextContent("pitch type SC: n=7 has high sampling noise");
    expect(warning).toBeVisible();
    expect(screen.getByRole("link", { name: "Statcast CSV documentation" })).toHaveAttribute("href", "https://baseballsavant.mlb.com/csv-docs");
    expect(screen.getByRole("link", { name: "Raw MLB atlas manifest" })).toHaveAttribute("href", sourceHref);
  });

  it("labels an invalid whole result measurement unavailable and excludes mixed families", () => {
    const unavailable = { ...a, values: { ...a.values, outcome_mix_pct: [] } };
    const { rerender, container } = render(<PitchResultComparison a={unavailable} b={b} sourceHref={sourceHref} />);
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(3);
    rerender(<PitchResultComparison a={{ ...a, sourceEntity: "team:NYY" }} b={b} sourceHref={sourceHref} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("labels team records as the pitching side", () => {
    render(<PitchResultComparison a={{ ...a, sourceEntity: "team:NYY" }} b={{ ...b, sourceEntity: "team:BOS" }} sourceHref={sourceHref} />);
    expect(screen.getByText("Teams are the pitching side in these source records.")).toBeInTheDocument();
  });

  it("shows one shared support note for an identical published sampling floor", () => {
    const sharedFloor = "shared sampling noise note";
    render(<PitchResultComparison a={{ ...a, floors: sharedFloor }} b={{ ...b, floors: sharedFloor }} sourceHref={sourceHref} />);
    const notes = document.querySelectorAll<HTMLElement>(".pitch-result-source-note");
    expect(notes).toHaveLength(1);
    expect(notes[0]).toHaveTextContent(`Shared source support note: ${sharedFloor}`);
    expect(notes[0]).toBeVisible();
  });
});
