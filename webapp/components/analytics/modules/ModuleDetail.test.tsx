import { render, screen, within } from "@testing-library/react";
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

  it("preserves module source dates and labelled coverage in figures and Scout receipts", () => {
    const insight = { cited: [{ field: "games", value: 20, path: mod.out_path }] };
    const { rerender } = render(<ModuleDetail mod={mod} out={{ ...out, as_of: mod.as_of }} subtitle="Published measurements." insight={insight} />);
    expect(screen.getByRole("button", { name: /Source as of 2026-09-01/ })).toBeInTheDocument();
    expect(screen.getByText("Source as of 2026-09-01", { selector: "figcaption span" })).toBeInTheDocument();
    rerender(<ModuleDetail mod={{ ...mod, as_of: "2025-26 regular season (through 2026-04-12)" }} out={out} subtitle="Published measurements." insight={insight} />);
    expect(screen.getByRole("button", { name: /Observation window 2025-26 regular season/ })).toBeInTheDocument();
    expect(screen.getByText("Observation window 2025-26 regular season (through 2026-04-12)", { selector: "figcaption span" })).toBeInTheDocument();
  });

  it("uses artifact fields when the manifest date came from generation", () => {
    const { rerender } = render(<ModuleDetail mod={mod} out={{ generated_at: "2026-09-01" }} subtitle="Published measurements." insight={null} />);
    expect(screen.getByText("Snapshot generated 2026-09-01", { selector: "figcaption span" })).toBeInTheDocument();
    rerender(<ModuleDetail mod={mod} out={{ as_of: "2026-07-19", generated_at: "2026-09-01" }} subtitle="Published measurements." insight={null} />);
    expect(screen.getByText("Source as of 2026-07-19", { selector: "figcaption span" })).toBeInTheDocument();
    expect(screen.queryByText(/Snapshot generated/)).not.toBeInTheDocument();
  });

  it("uses a data figure instead of an unapproved PNG", () => {
    const unsafe = { ...mod, id: "ctx_team_states", title: "Team states", chart_path: "ctx_team_states.png" };
    render(<ModuleDetail mod={unsafe} out={{ teams: [{ team: "ATL", n_games: 2, front_runner_2h_margin: 1, comeback_2h_margin: 8 }] }} subtitle="Published team measurements." insight={null} />);
    expect(screen.getByTestId("published-data-figure")).toHaveTextContent("ATL");
    expect(screen.queryByRole("img", { name: "Team states chart" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "View full size" })).not.toBeInTheDocument();
  });

  it("mounts the integrity notice only for affected artifacts", () => {
    const { rerender } = render(<ModuleDetail mod={{ ...mod, id: "state_conditioned_calibration" }} out={out} subtitle="Published state measurements." insight={null} />);
    expect(screen.getAllByRole("complementary", { name: "Data integrity" })[0]).toHaveTextContent("state_conditioned_calibration");
    rerender(<ModuleDetail mod={{ ...mod, id: "novel_rest_asymmetry" }} out={out} subtitle="Rest differential frequencies." insight={null} />);
    expect(screen.queryByRole("complementary", { name: "Data integrity" })).not.toBeInTheDocument();
  });

  it("mounts paper backlinks in the existing related reading area", () => {
    render(<ModuleDetail mod={mod} out={out} subtitle="When a lead becomes permanent." insight={null} />);
    const papers = screen.getAllByRole("link").filter((link) => /\/analytics\/papers\//.test(link.getAttribute("href") || ""));
    expect(papers.length).toBeGreaterThan(0);
  });

  it("labels module tables and keeps the Scout continuation reachable", () => {
    const unsafe = { ...mod, id: "ctx_team_states", title: "Team states", chart_path: "ctx_team_states.png" };
    render(<ModuleDetail mod={unsafe} out={{ teams: [{ team: "ATL", n_games: 2 }] }} subtitle="Published team measurements." insight={{ cited: [{ field: "teams.0.team", value: "ATL", path: "ctx_team_states.json" }] }} />);
    expect(screen.getByRole("region", { name: "Published replacement measurements (scrollable table)" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("region", { name: "Published module receipts (scrollable table)" })).toHaveAttribute("tabindex", "0");
    const receipts = screen.getByRole("table", { name: "Published module receipts" });
    expect(within(receipts).getByRole("rowheader", { name: "teams.0.team" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Continue reading" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ask Scout about this module" }).getAttribute("href")).toMatch(/^\/analytics\/ask\/?\?q=Team%20states$/);
  });
});
