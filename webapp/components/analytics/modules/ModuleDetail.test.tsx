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
});
