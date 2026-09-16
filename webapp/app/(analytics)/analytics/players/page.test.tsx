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
});
