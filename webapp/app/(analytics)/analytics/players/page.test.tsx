import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
  it("filters naturally after remount and restores calibration groups when cleared", () => {
    const first = render(<EntitiesIndexPage />);
    first.unmount();
    render(<EntitiesIndexPage />);

    const search = screen.getByRole("searchbox", { name: "Filter entities by name" });
    const checkpoints = screen.getByRole("heading", { name: "Calibration checkpoints" }).closest("section") as HTMLElement;
    const bands = screen.getByRole("heading", { name: "Probability-band calibration" }).closest("section") as HTMLElement;
    const jokicRow = screen.getByRole("link", { name: /^Nikola Jokic$/i }).closest("tr") as HTMLElement;
    const bandRow = bands.querySelector("tr[data-name]") as HTMLElement;

    fireEvent.input(search, { target: { value: "jokic" } });
    expect(jokicRow).toBeVisible();
    expect(checkpoints).not.toBeVisible();
    expect(bands).not.toBeVisible();

    fireEvent.input(search, { target: { value: "" } });
    expect(checkpoints).toBeVisible();
    expect(bands).toBeVisible();
    expect(jokicRow).toBeVisible();
    expect(bandRow).toBeVisible();

    fireEvent.input(search, { target: { value: "mlb inning 1" } });
    expect(checkpoints).toBeVisible();
    expect(bands).not.toBeVisible();
    expect(screen.getByRole("row", { name: /^mlb inning 1\s/i })).toBeVisible();

    fireEvent.input(search, { target: { value: "" } });
    expect(checkpoints).toBeVisible();
    expect(bands).toBeVisible();
  });

  it("labels the data-derived pitch atlas total without calling every card a pitch type", () => {
    render(<EntitiesIndexPage />);
    const count = mlbPitchEntries().length.toLocaleString();
    expect(screen.getByRole("link", { name: new RegExp(`MLB pitch atlas cards\\s*${count}`) })).toBeInTheDocument();
  });

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
    for (const [entity, value] of [["mlb band .2-.4", "0.3"], ["mlb band .4-.6", "0.5"]]) {
      const row = within(bandSection).getByRole("row", { name: new RegExp(entity.replace(/\./g, "\\."), "i") });
      expect(within(row).getByText(value)).toBeInTheDocument();
    }
  });
});
