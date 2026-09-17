import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { loadStarterRestAbsorption, StarterRestAbsorptionPanel } from "./StarterRestAbsorptionPanel";

const artifact = loadStarterRestAbsorption();
const captions = [
  `1. Win frequency by days of rest -- ${artifact.panels.rest_buckets.n_starts.toLocaleString("en-US")} team-starts`,
  `2. Contrast against standard ${artifact.panels.rest_buckets.cells.find(cell => cell.cell === "4")?.cell} days of rest -- ${artifact.panels.rest_buckets.n_starts.toLocaleString("en-US")} team-starts`,
  `3. Observed frequency minus reference forecast by forecast band -- ${artifact.panels.by_forecast_band.n_starts.toLocaleString("en-US")} team-starts`,
  `4. Season stability of the short-rest minus long-rest gradient -- ${artifact.panels.rest_buckets.n_starts.toLocaleString("en-US")} team-starts`,
  `5. Doubleheader nightcap against first game -- ${artifact.panels.doubleheader_nightcap.n_games.toLocaleString("en-US")} games`,
];

describe("StarterRestAbsorptionPanel", () => {
  it("renders the five published figures with their artifact counts", () => {
    render(<StarterRestAbsorptionPanel />);
    expect(screen.getAllByRole("figure")).toHaveLength(captions.length);
    for (const caption of captions) expect(screen.getByText(caption)).toBeInTheDocument();
  });

  it("renders the honest-null verdict exactly once", () => {
    render(<StarterRestAbsorptionPanel />);
    expect(screen.getAllByText(artifact.verdict)).toHaveLength(1);
  });

  it("keeps a masked cell's count and prints the artifact mask rule", () => {
    const cell = { ...artifact.panels.rest_buckets.cells[0], masked: true, mask_reason: null };
    const maskedArtifact = {
      ...artifact,
      panels: { ...artifact.panels, rest_buckets: { ...artifact.panels.rest_buckets, cells: [cell, ...artifact.panels.rest_buckets.cells.slice(1)] } },
    };
    render(<StarterRestAbsorptionPanel artifact={maskedArtifact} />);
    const firstFigure = screen.getByText(captions[0]).closest("figure") as HTMLElement;
    expect(within(firstFigure).getByText(artifact.method.mask_rule)).toBeInTheDocument();
    expect(firstFigure).toHaveTextContent(cell.n_starts.toLocaleString("en-US"));
  });

  it("lists the label cross-check and its published count in the checks disclosure", () => {
    render(<StarterRestAbsorptionPanel />);
    const checks = screen.getByText("Checks").closest("details") as HTMLElement;
    expect(checks).toHaveTextContent(artifact.checks.label_crosscheck_source);
    expect(checks).toHaveTextContent(artifact.checks.label_crosscheck_n.toLocaleString("en-US"));
  });

  it("makes every published table scroll region focusable", () => {
    render(<StarterRestAbsorptionPanel />);
    const regions = screen.getAllByRole("region", { name: /scrollable table/ });
    expect(regions).toHaveLength(captions.length);
    for (const region of regions) expect(region).toHaveAttribute("tabindex", "0");
    expect(new Set(regions.map(region => region.getAttribute("aria-label"))).size).toBe(captions.length);
    expect(screen.getAllByText("Scroll horizontally for all columns")).toHaveLength(captions.length);
  });
});
