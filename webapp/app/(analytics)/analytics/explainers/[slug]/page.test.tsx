import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getResearchAnalyses } from "@/lib/analytics/researchData";
import ExplainerPage from "./page";

type Destination = { href: string; label: string };
type Essay = {
  slug: string;
  inspector?: Destination;
  next?: Destination[];
};
type SiteManifest = { modules: Array<{ id: string }> };

function readEssays(): Essay[] {
  const raw = readFileSync(
    join(process.cwd(), "public", "data", "explainers", "explainers.json"),
    "utf8"
  );
  return (JSON.parse(raw) as { essays: Essay[] }).essays;
}

function canonicalRoute(href: string): string {
  return href.endsWith("/") ? href : `${href}/`;
}

describe("ExplainerPage", () => {
  it("renders a new guide with inspector, destination, and source links", () => {
    render(<ExplainerPage params={{ slug: "reading-an-atlas-analysis" }} />);

    expect(screen.getByRole("link", { name: "Open the MLB pitch type atlas analysis" })).toHaveAttribute("href", expect.stringContaining("/analytics/research/mlb-pitch-type-atlas-measurements"));
    expect(screen.getByRole("link", { name: "Pitch sequencing" })).toHaveAttribute("href", expect.stringContaining("/analytics/pitch-sequencing"));

    const sources = screen.getByText("Sources").parentElement;
    expect(sources).not.toBeNull();
    expect(
      within(sources as HTMLElement).getAllByRole("link").map((link) => link.getAttribute("href"))
    ).toEqual([
      `${process.env.NEXT_PUBLIC_BASE_PATH || ""}/data/showcase/atlas_mlb_pitch_manifest.json`,
      `${process.env.NEXT_PUBLIC_BASE_PATH || ""}/data/showcase/atlas_mlb_pitch_manifest.json`,
    ]);
  });

  it("keeps every authored destination on a generated public route", () => {
    const manifestRaw = readFileSync(
      join(process.cwd(), "public", "data", "showcase", "site_manifest.json"),
      "utf8"
    );
    const manifest = JSON.parse(manifestRaw) as SiteManifest;
    const fixedRoutes = new Set([
      "/analytics/calibration/",
      "/analytics/score-decomposition/",
      "/analytics/observation-dependence/",
      "/analytics/findings/effective-sample-size/",
      "/analytics/browse/",
      "/analytics/pitch-sequencing/",
    ]);
    const researchRoutes = new Set(
      getResearchAnalyses().map((analysis) => `/analytics/research/${analysis.id}/`)
    );
    const moduleRoutes = new Set(
      manifest.modules.map((entry) => `/analytics/m/${entry.id}/`)
    );
    const destinations = readEssays().flatMap((essay) => [
      ...(essay.inspector ? [essay.inspector] : []),
      ...(essay.next || []),
    ]);

    expect(destinations.length).toBeGreaterThan(0);
    for (const destination of destinations) {
      const href = canonicalRoute(destination.href);
      expect(
        fixedRoutes.has(href) || researchRoutes.has(href) || moduleRoutes.has(href),
        destination.href
      ).toBe(true);
    }
  });
});
