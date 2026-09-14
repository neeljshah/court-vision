import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ComparisonEntity } from "@/lib/analytics/comparisonData";
import { PitchCountComparison } from "./PitchCountComparison";

const a: ComparisonEntity = {
  slug: "ff", sourceEntity: "pitch_type:FF", name: "pitch_type FF", asOf: "2025-09-28", floors: "all published pitch types retained", values: {
    n_pitches: 220235, count_leverage_pct: { pitcher_ahead: 27.6, even: 43.3, pitcher_behind: 29.2 },
  }, percentiles: {},
};
const b: ComparisonEntity = {
  slug: "sc", sourceEntity: "pitch_type:SC", name: "pitch_type SC", asOf: "2025-09-28", floors: "smallest category n=7 has high sampling noise", values: {
    n_pitches: 7, count_leverage_pct: { pitcher_ahead: 0, even: 42.9 },
  }, percentiles: {},
};

describe("PitchCountComparison", () => {
  it("shows source shares including a true zero, partial missing value, and smallest-category support", () => {
    render(<PitchCountComparison a={a} b={b} sourceHref="/data/showcase/atlas_mlb_pitch_manifest.json" />);
    expect(screen.getByRole("heading", { name: "Recorded count context" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Published pitch-type count context shares" })).toBeInTheDocument();
    expect(screen.getByText("27.6%")).toBeInTheDocument();
    expect(screen.getByText("0.0%")).toBeInTheDocument();
    expect(screen.getByText("Not reported")).toBeInTheDocument();
    expect(screen.getByText(/rounded totals can differ from 100%/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Count context color legend" })).toHaveTextContent("Pitcher ahead");
    expect(screen.getByRole("list", { name: "Count context color legend" })).toHaveTextContent("Even count");
    expect(screen.getByRole("list", { name: "Count context color legend" })).toHaveTextContent("Pitcher behind");
    expect(screen.getByText(/pitch_type SC \(n=7\)/)).toBeInTheDocument();
    expect(screen.getByText(/pitch_type SC has an incomplete published distribution/)).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.getByRole("img", { name: /pitch_type FF: Pitcher ahead 27.6%/ })).toBeInTheDocument();
    expect(screen.getByText(/strikes > balls/)).toBeInTheDocument();
  });

  it("does not render for entities outside the public pitch-type shape", () => {
    const { container } = render(<PitchCountComparison a={{ ...a, sourceEntity: "team:NYY" }} b={b} sourceHref="/data/showcase/atlas_mlb_pitch_manifest.json" />);
    expect(container).toBeEmptyDOMElement();
  });
});
