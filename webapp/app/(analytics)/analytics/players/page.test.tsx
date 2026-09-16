import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getMlbPitchAtlasCohorts } from "@/lib/analytics/atlasResearchCohorts";
import EntitiesIndexPage from "./page";

type Manifest = { entries: Array<{ entity: string; card_path: string; key_numbers: Record<string, unknown>; as_of?: string }> };

function mlbPitchEntries() {
  const raw = readFileSync(join(process.cwd(), "public", "data", "showcase", "atlas_mlb_pitch_manifest.json"), "utf8");
  return (JSON.parse(raw) as Manifest).entries;
}

function calibrationEntries() {
  const raw = readFileSync(join(process.cwd(), "public", "data", "showcase", "atlas_calibration_manifest.json"), "utf8");
  return (JSON.parse(raw) as Manifest).entries;
}

describe("EntitiesIndexPage", () => {
  it("renders separate data-derived MLB pitch, team, and count-state sections", () => {
    render(<EntitiesIndexPage />);
    for (const cohort of getMlbPitchAtlasCohorts(mlbPitchEntries())) {
      const heading = screen.getByRole("heading", { name: cohort.title });
      const section = heading.closest("section");
      expect(section).not.toBeNull();
      expect(within(section as HTMLElement).getByText(new RegExp(`${cohort.entries.length.toLocaleString()} cards`))).toBeInTheDocument();
    }
  });

  it("separates calibration checkpoints and probability bands with data-derived counts", () => {
    render(<EntitiesIndexPage />);
    const entries = calibrationEntries();
    for (const [cardType, headingName] of [["time_checkpoint", "Calibration checkpoints"], ["prob_band", "Probability-band calibration"]] as const) {
      const heading = screen.getByRole("heading", { name: headingName });
      const section = heading.closest("section");
      const count = entries.filter((entry) => (entry as { card_type?: string }).card_type === cardType).length;
      expect(section).not.toBeNull();
      expect(within(section as HTMLElement).getByText(new RegExp(`${count.toLocaleString()} cards`))).toBeInTheDocument();
    }
  });

  it("renders all published probability-band measurements without checkpoint columns", () => {
    render(<EntitiesIndexPage />);
    const bandSection = screen.getByRole("heading", { name: "Probability-band calibration" }).closest("section") as HTMLElement;
    const checkpointSection = screen.getByRole("heading", { name: "Calibration checkpoints" }).closest("section") as HTMLElement;
    const entries = calibrationEntries().filter((entry) => (entry as { card_type?: string }).card_type === "prob_band");
    const bandRows = within(bandSection).getAllByRole("row").filter((row) =>
      within(row).queryByRole("link")?.getAttribute("href")?.includes("/analytics/players/calibration/"),
    );

    expect(bandRows).toHaveLength(entries.length);
    for (const label of ["Published observations", "Observed outcome mean, overall", "Calibration band reference", "Time buckets with data"]) {
      expect(within(bandSection).getAllByRole("columnheader", { name: label }).length).toBeGreaterThan(0);
      expect(within(checkpointSection).queryAllByRole("columnheader", { name: label }).length).toBe(label === "Published observations" ? 2 : 0);
    }
    for (const entry of entries) {
      const row = within(bandSection).getByRole("row", { name: new RegExp(entry.entity.replace(/_/g, " "), "i") });
      expect(within(row).queryByText("--")).not.toBeInTheDocument();
      expect(within(row).getByRole("link")).toHaveAttribute("href", expect.stringContaining("/analytics/players/calibration/"));
    }
  });
});
