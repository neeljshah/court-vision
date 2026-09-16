import { readFileSync } from "node:fs";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { RawManifest } from "@/lib/analytics/comparisonData";
import { CompareExperience } from "./CompareExperience";

const published = JSON.parse(readFileSync("public/data/showcase/atlas_soccer_manifest.json", "utf8")) as RawManifest;
const soccer = { entries: published.entries!.filter((entry) => ["Barcelona", "Liverpool"].includes(entry.entity)) };
const nba = { entries: [
  { entity: "Alpha", card_path: "atlas/alpha.png", key_numbers: { career_pts_per36: 10 } },
  { entity: "Beta", card_path: "atlas/beta.png", key_numbers: { career_pts_per36: 14 } },
] };
const metadata = { packs: {} };

describe("Soccer comparison navigation", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/analytics/compare/?pack=soccer&a=barcelona&b=liverpool");
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({ ok: true, json: async () =>
      url.includes("atlas_soccer_manifest") ? soccer : url.includes("atlas_nba_manifest") ? nba : metadata,
    })));
  });

  it("loads published venue values from a shared pair URL and keeps them attached to the club when swapped", async () => {
    const view = render(<CompareExperience />);
    const panel = await screen.findByRole("region", { name: "Home and away form" });
    expect(screen.getByLabelText("Profile A")).toHaveValue("Barcelona");
    expect(screen.getByLabelText("Profile B")).toHaveValue("Liverpool");
    expect(within(panel).getByRole("img", { name: /Barcelona.*Home.*3\.0/ })).toBeInTheDocument();
    expect(within(panel).getByRole("img", { name: /Liverpool.*Away.*1\.1/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Swap profile A and profile B" }));
    await waitFor(() => expect(window.location.search).toContain("a=liverpool&b=barcelona"));
    expect(screen.getByLabelText("Profile A")).toHaveValue("Liverpool");
    expect(within(panel).getByRole("img", { name: /Barcelona.*Home.*3\.0/ })).toBeInTheDocument();
    view.unmount();
    render(<CompareExperience />);
    await screen.findByRole("region", { name: "Home and away form" });
    expect(screen.getByLabelText("Profile A")).toHaveValue("Liverpool");
    expect(screen.getByLabelText("Profile B")).toHaveValue("Barcelona");
  });

  it("removes the soccer venue view when selecting another sport", async () => {
    render(<CompareExperience />);
    await screen.findByRole("region", { name: "Home and away form" });
    fireEvent.click(screen.getByRole("button", { name: "Basketball" }));
    await waitFor(() => expect(screen.getByLabelText("Profile A")).toHaveValue("Alpha"));
    expect(screen.queryByRole("region", { name: "Home and away form" })).not.toBeInTheDocument();
    expect(window.location.search).toContain("pack=nba_players");
    expect(window.location.search).not.toContain("barcelona");
  });
});
