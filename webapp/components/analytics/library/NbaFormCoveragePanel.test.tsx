import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildNbaFormCoverage } from "@/lib/analytics/nbaFormCoverage";
import source from "@/public/data/showcase/nba_form_curves.json";
import { NbaFormCoveragePanel } from "./NbaFormCoveragePanel";

const coverage = buildNbaFormCoverage(source);

describe("NBA form cohort support panel", () => {
  it("shows the real source hierarchy with each denominator named", () => {
    const { container } = render(<NbaFormCoveragePanel coverage={coverage} />);
    const retained = screen.getByRole("article", { name: "Retained window coverage" });
    const eligible = screen.getByRole("article", { name: "Eligible mover coverage" });
    expect(retained).toHaveTextContent("76.7% of source player IDs");
    expect(within(retained).getByText("Source player IDs").nextSibling).toHaveTextContent("807");
    expect(within(retained).getByText("IDs with a retained window").nextSibling).toHaveTextContent("619");
    expect(within(retained).getByText("IDs without a retained window").nextSibling).toHaveTextContent("188");
    expect(eligible).toHaveTextContent("90.8% of IDs with a retained window");
    expect(within(eligible).getByText("Eligible mover IDs").nextSibling).toHaveTextContent("562");
    expect(within(eligible).getByText("IDs not mover eligible").nextSibling).toHaveTextContent("57");
    expect(container.querySelectorAll(".nba-form-coverage-track[aria-hidden='true']")).toHaveLength(2);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("explains the window and selected-row limits with provenance", () => {
    render(<NbaFormCoveragePanel coverage={coverage} />);
    expect(screen.getByText(/61,298 pooled, overlapping 10-game windows are not independent/)).toBeInTheDocument();
    expect(screen.getByText(/30 selected mover rows/)).toBeInTheDocument();
    expect(screen.getByText(/2023-24, 2024-25, 2025-26/)).toBeInTheDocument();
    expect(screen.getByText(/Observation start and end dates are not published/)).toBeInTheDocument();
    expect(screen.getByText(/min>=8\/game, window_total_min>=120, >=20 qualifying games/)).toBeInTheDocument();
    expect(screen.getByText(/not a prediction or live streak/)).toBeInTheDocument();
    expect(screen.getByText(/Raw player IDs may split names with accents/)).toBeInTheDocument();
    expect(screen.getByText("input_coverage.unique_players")).toBeInTheDocument();
    expect(screen.getByText("input_coverage.players_with_retained_window")).toBeInTheDocument();
    expect(screen.getByText("input_coverage.movers_eligible")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Inspect the published NBA form source" })).toHaveAttribute("href", "/data/showcase/nba_form_curves.json");
  });

  it("is absent when no coverage was supplied", () => {
    const { container } = render(<NbaFormCoveragePanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it("keeps missing counts unavailable and suppresses inconsistent derivations", () => {
    const invalid = { ...coverage, sourcePlayers: 500, retainedPlayers: 619, consistent: false };
    const { rerender, container } = render(<NbaFormCoveragePanel coverage={invalid} />);
    expect(screen.getByRole("article", { name: "Retained window coverage" })).toHaveTextContent("500");
    expect(screen.getByText(/missing or do not form a consistent hierarchy/)).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable")).toHaveLength(4);
    expect(container.querySelector(".nba-form-coverage-track")).not.toBeInTheDocument();

    rerender(<NbaFormCoveragePanel coverage={{ ...coverage, sourcePlayers: null, retainedPlayers: null,
      eligibleMovers: null, pooledWindows: null, publishedMoverRows: null, seasons: [],
      windowGames: null, floors: null, consistent: false, retainedShare: null,
      eligibleShare: null, excludedBeforeWindow: null, excludedBeforeMover: null }} />);
    expect(screen.getByText(/Unavailable pooled, overlapping windows \(window size unavailable\)/)).toBeInTheDocument();
    expect(screen.getByText(/Pooled seasons: Unavailable/)).toBeInTheDocument();
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument();
  });

  it("shows explicit zero counts without inventing a zero-denominator percentage", () => {
    const zero = buildNbaFormCoverage({ input_coverage: { unique_players: 0,
      players_with_retained_window: 0, movers_eligible: 0, pooled_windows: 0 },
      methodology: { window_games: 10, seasons_pooled: [], floors: "minimum 0" },
      top_movers_risers: [], top_movers_fallers: [] });
    const { container } = render(<NbaFormCoveragePanel coverage={zero} />);
    expect(screen.getByRole("article", { name: "Retained window coverage" })).toHaveTextContent("Source player IDs0");
    expect(screen.getByRole("article", { name: "Eligible mover coverage" })).toHaveTextContent("Eligible mover IDs0");
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(container.querySelector(".nba-form-coverage-track")).not.toBeInTheDocument();
    expect(screen.getByText(/0 selected mover rows/)).toBeInTheDocument();
  });
});
