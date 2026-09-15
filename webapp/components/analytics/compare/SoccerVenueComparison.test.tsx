import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ComparisonEntity } from "@/lib/analytics/comparisonData";
import { SoccerVenueComparison } from "./SoccerVenueComparison";

const floor = "ppg_home_l10: n_prior_home>=10 | ppg_away_l10: n_prior_away>=10 | clean_sheet_rate_home: n_prior_home>=10 | clean_sheet_rate_away: n_prior_away>=10 (window=trailing10_asof_corpus_end; a metric a team doesn't clear shows n/a, never fabricated)";
const a: ComparisonEntity = { slug: "alpha", sourceEntity: "club:alpha", name: "Alpha FC", floors: floor, asOf: "2026-07-18T17:21:08.108324+00:00", status: "complete", values: { ppg_home_l10: 2, ppg_away_l10: 1, clean_sheet_rate_home: .4, clean_sheet_rate_away: .1 }, percentiles: {} };
const b: ComparisonEntity = { slug: "beta", sourceEntity: "club:beta", name: "Beta FC", floors: floor, asOf: a.asOf, status: "complete", values: { ppg_home_l10: 0, ppg_away_l10: .3, clean_sheet_rate_home: 0, clean_sheet_rate_away: .2 }, percentiles: {} };
const sourceHref = "/data/showcase/atlas_soccer_manifest.json";

describe("SoccerVenueComparison", () => {
  it("shows separate zero-origin venue measures with signed descriptive gaps", () => {
    render(<SoccerVenueComparison a={a} b={b} sourceHref={sourceHref} />);
    expect(screen.getByRole("heading", { name: "Home and away form" })).toBeInTheDocument();
    expect(screen.getByText("0-3 points per game scale")).toBeInTheDocument();
    expect(screen.getByText("0-100% scale")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Published home and away form values" })).toBeInTheDocument();
    expect(screen.getAllByText("Home minus away: +1.0 points per game")).toHaveLength(2);
    expect(screen.getAllByText("Home minus away: +30.0 percentage points")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Beta FC Points per game Home: 0.0" }).querySelector("i")).toHaveStyle({ width: "0%" });
    expect(screen.getByRole("img", { name: "Alpha FC Clean-sheet rate Home: 40.0%" }).querySelector("i")).toHaveStyle({ width: "40%" });
    expect(screen.getByText("Claim computation snapshot: 2026-07-18")).toBeVisible();
    expect(screen.getByRole("link", { name: "Raw soccer atlas manifest" })).toHaveAttribute("href", sourceHref);
  });

  it("distinguishes missing from invalid venue values and preserves distinct source floors", () => {
    const differentFloor = `${floor} | secondary published rule`;
    render(<SoccerVenueComparison a={{ ...a, values: { ...a.values, ppg_home_l10: NaN, clean_sheet_rate_away: undefined } }} b={{ ...b, floors: differentFloor, values: { ...b.values, clean_sheet_rate_home: 1.2 } }} sourceHref={sourceHref} />);
    expect(screen.getAllByText("Not published")).toHaveLength(1);
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.getAllByText("Home minus away: Not published")).toHaveLength(2);
    expect(screen.getAllByText("Home minus away: Unavailable")).toHaveLength(4);
    const details = document.querySelector("details");
    expect(details).toHaveTextContent(`Alpha FC: ${floor}`);
    expect(details).toHaveTextContent(`Beta FC: ${differentFloor}`);
    expect(details).toHaveTextContent("Points per game awards 3 points for a win, 1 for a draw, and 0 for a loss.");
  });
});
