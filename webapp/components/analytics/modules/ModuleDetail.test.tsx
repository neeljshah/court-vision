import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ModuleDetail } from "./ModuleDetail";
import type { Mod, Out } from "@/app/(analytics)/analytics/m/[id]/page";

const mod: Mod = { id: "blowout_dynamics", title: "Blowout dynamics", one_line: "When a lead becomes permanent.", out_path: "blowout_dynamics.json", chart_path: "blowout_dynamics.png", status: "published", as_of: "2026-09-01" };
const out: Out = { descriptive_only: true };

describe("ModuleDetail", () => {
  it("places authored guidance directly below the chart figure", () => {
    render(<ModuleDetail mod={mod} out={out} subtitle="When a lead becomes permanent." insight={{ how_to_read: "For each (sport, threshold), decided_frac_of_games is how often that gap ever became permanent and decided_clock_median is the typical clinch time; cells below the game floor are masked." }} />);
    const figure = screen.getByRole("img", { name: "Blowout dynamics chart" }).closest("figure");
    const guide = screen.getByRole("heading", { name: "How to read this figure" }).closest("section");
    expect(figure?.compareDocumentPosition(guide!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(guide).toHaveTextContent("decided_frac_of_games");
    expect(guide).toHaveTextContent("decided_clock_median");
  });

  it("does not invent a reading guide", () => {
    render(<ModuleDetail mod={mod} out={out} subtitle="When a lead becomes permanent." insight={null} />);
    expect(screen.queryByRole("heading", { name: "How to read this figure" })).not.toBeInTheDocument();
  });

  it("uses plain language when a published source has no chart", () => {
    render(<ModuleDetail mod={{ ...mod, chart_path: undefined }} out={out} subtitle="When a lead becomes permanent." insight={null} />);
    expect(screen.getByText("This source has no chart. Its cited measurements appear below.")).toBeInTheDocument();
  });

  it("states when a module date is not published", () => {
    render(<ModuleDetail mod={{ ...mod, as_of: null as unknown as string }} out={out} subtitle="When a lead becomes permanent." insight={null} />);
    expect(screen.getAllByText(/date not published/i).length).toBeGreaterThan(0);
  });

  it("uses a data figure instead of an unapproved PNG", () => {
    const unsafe = { ...mod, id: "ctx_team_states", title: "Team states", chart_path: "ctx_team_states.png" };
    render(<ModuleDetail mod={unsafe} out={{ teams: [{ team: "ATL", n_games: 2, front_runner_2h_margin: 1, comeback_2h_margin: 8 }] }} subtitle="Published team measurements." insight={null} />);
    expect(screen.getByTestId("published-data-figure")).toHaveTextContent("ATL");
    expect(screen.queryByRole("img", { name: "Team states chart" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View full size" })).not.toBeInTheDocument();
  });
});
