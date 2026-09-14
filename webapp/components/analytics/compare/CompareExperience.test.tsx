import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompareExperience } from "./CompareExperience";

const manifest = { entries: [
  { entity: "Alpha", card_path: "atlas/alpha.png", key_numbers: { career_pts_per36: 10 } },
  { entity: "Beta", card_path: "atlas/beta.png", key_numbers: { career_pts_per36: 14 } },
] };
const percentiles = { packs: { nba_players: { n_in_pack: 2, fields: { career_pts_per36: { n_ranked: 2 } }, entities: { alpha: { career_pts_per36: 25 }, beta: { career_pts_per36: 75 } } } } };
const comparables = { packs: { nba_players: { entities: { alpha: { similar: [{ slug: "beta" }] } } } } };
const tennisManifest = { entries: [
  { entity: "Alpha (ATP)", card_path: "atlas/alpha.png", as_of: "2026-07-19", floors: "hard_n>=30", key_numbers: { hard_wr_career: .69, clay_wr_career: .74 } },
  { entity: "Beta (ATP)", card_path: "atlas/beta.png", as_of: "2026-07-19", floors: "hard_n>=30", key_numbers: { hard_wr_career: .5 } },
] };
const tennisPercentiles = { packs: { tennis: { n_in_pack: 2, fields: { hard_wr_career: { n_ranked: 2 }, clay_wr_career: { n_ranked: 1 } }, entities: { alpha: { hard_wr_career: 75, clay_wr_career: 80 }, beta: { hard_wr_career: 25 } } } } };
const destinationManifest = { entries: [
  { entity: "Gamma", card_path: "atlas/gamma.png", key_numbers: { career_pts_per36: 15 } },
  { entity: "Delta", card_path: "atlas/delta.png", key_numbers: { career_pts_per36: 11 } },
] };
const destinationPercentiles = { packs: { nba_players: { n_in_pack: 2, fields: { career_pts_per36: { n_ranked: 2 } }, entities: { gamma: { career_pts_per36: 80 }, delta: { career_pts_per36: 20 } } } } };

describe("CompareExperience controls", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/analytics/compare");
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      json: async () => url.includes("atlas_tennis_manifest") ? tennisManifest : url.includes("atlas_nba_manifest") ? manifest : url.includes("percentiles") ? percentiles : comparables,
    })));
  });

  it("loads a same-pack pair, exposes its rank, swaps it, and writes shareable state", async () => {
    render(<CompareExperience />);
    const a = await screen.findByLabelText("Profile A");
    const b = screen.getByLabelText("Profile B");
    await waitFor(() => expect(a).toHaveValue("Alpha"));
    expect(b).toHaveValue("Beta");
    expect(screen.getByText("25th percentile")).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveAccessibleName("Published values and within-pack percentile ranks");
    expect(screen.getByRole("img", { name: "25th percentile visual bar" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Where these profiles separate" })).toBeInTheDocument();
    expect(screen.getByText("1 shared axes")).toBeInTheDocument();
    expect(screen.getByText(/Higher means a higher raw measured value, never better/)).toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toContain("pack=nba_players"));
    expect(window.location.search).toContain("a=alpha");
    expect(window.location.search).toContain("b=beta");

    fireEvent.change(a, { target: { value: "alpha" } });
    await waitFor(() => expect(a).toHaveValue("alpha"));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.change(a, { target: { value: "Alpha" } });

    fireEvent.click(screen.getByRole("button", { name: "Swap profile A and profile B" }));
    await waitFor(() => expect(a).toHaveValue("Beta"));
    expect(b).toHaveValue("Alpha");
    expect(window.location.search).toContain("a=beta");
    expect(window.location.search).toContain("b=alpha");
  });

  it("offers sport-first entry tabs and switches the active sport", async () => {
    render(<CompareExperience />);
    await screen.findByLabelText("Profile A");
    const soccer = screen.getByRole("button", { name: "Soccer" });
    expect(screen.getByRole("button", { name: "NBA" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(soccer);
    expect(soccer).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(window.location.search).toContain("pack=soccer"));
  });

  it("supports retry after a failed load and rejects an unmatched typed profile", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementationOnce(() => Promise.reject(new Error("offline")));
    render(<CompareExperience />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    const a = await screen.findByLabelText("Profile A");
    await waitFor(() => expect(a).toHaveValue("Alpha"));
    fireEvent.change(a, { target: { value: "No Such Profile" } });
    expect(screen.getByRole("status")).toHaveTextContent("Choose a published profile");
    expect(screen.queryByText("25th percentile")).not.toBeInTheDocument();
  });

  it("keeps the loaded pair and share URL when the active sport is selected again", async () => {
    render(<CompareExperience />);
    const a = await screen.findByLabelText("Profile A");
    await waitFor(() => expect(a).toHaveValue("Alpha"));
    fireEvent.click(screen.getByRole("button", { name: "NBA" }));
    expect(screen.getByLabelText("Profile A")).toHaveValue("Alpha");
    expect(screen.getByLabelText("Profile B")).toHaveValue("Beta");
    expect(screen.getByRole("heading", { name: "Where these profiles separate" })).toBeInTheDocument();
    expect(window.location.search).toContain("pack=nba_players");
    expect(window.location.search).toContain("a=alpha");
    expect(window.location.search).toContain("b=beta");
  });

  it("restores a tennis surface deep link without serializing the default pack, updates it, and removes it outside tennis", async () => {
    window.history.replaceState({ next: true }, "", "/analytics/compare?pack=tennis&a=alpha&b=beta&surface=clay");
    vi.mocked(fetch).mockImplementation((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("atlas_tennis_manifest") ? tennisManifest : url.includes("percentiles") ? tennisPercentiles : comparables } as Response));
    render(<CompareExperience />);
    expect(await screen.findByRole("heading", { name: "Recorded surface history" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clay" })).toHaveAttribute("aria-pressed", "true");
    expect(window.location.search).toContain("pack=tennis");
    expect(window.location.search).toContain("surface=clay");
    fireEvent.click(screen.getByRole("button", { name: "Grass" }));
    await waitFor(() => expect(window.location.search).toContain("surface=grass"));
    fireEvent.click(screen.getByRole("button", { name: "Swap profile A and profile B" }));
    await waitFor(() => expect(screen.getByLabelText("Profile A")).toHaveValue("Beta (ATP)"));
    window.history.pushState({ next: true }, "", "/analytics/compare?pack=tennis&a=alpha&b=beta&surface=clay");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(screen.getByRole("button", { name: "Clay" })).toHaveAttribute("aria-pressed", "true"));
    await waitFor(() => expect(screen.getByLabelText("Profile A")).toHaveValue("Alpha (ATP)"));
    fireEvent.click(screen.getByRole("button", { name: "NBA" }));
    await waitFor(() => expect(window.location.search).not.toContain("surface="));
    expect(window.history.state).toEqual({ next: true });
  });

  it("keeps a cross-pack popstate pair in the URL while its destination pack is pending or rejected, then restores it on retry", async () => {
    let rejectDestination: (error: Error) => void = () => undefined;
    let destinationAttempt = 0;
    const pendingDestination = new Promise<Response>((_, reject) => { rejectDestination = reject; });
    window.history.replaceState(null, "", "/analytics/compare?pack=tennis&a=alpha&b=beta&surface=hard");
    vi.mocked(fetch).mockImplementation((url: string) => {
      if (url.includes("atlas_tennis_manifest")) return Promise.resolve({ ok: true, json: async () => tennisManifest } as Response);
      if (url.includes("atlas_nba_manifest")) {
        destinationAttempt += 1;
        return destinationAttempt === 1 ? pendingDestination : Promise.resolve({ ok: true, json: async () => destinationManifest } as Response);
      }
      if (url.includes("percentiles")) return Promise.resolve({ ok: true, json: async () => destinationAttempt ? destinationPercentiles : tennisPercentiles } as Response);
      return Promise.resolve({ ok: true, json: async () => comparables } as Response);
    });
    render(<CompareExperience />);
    expect(await screen.findByRole("heading", { name: "Recorded surface history" })).toBeInTheDocument();
    window.history.pushState(null, "", "/analytics/compare?pack=nba_players&a=gamma&b=delta");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(window.location.search).toBe("?pack=nba_players&a=gamma&b=delta"));
    expect(screen.queryByRole("heading", { name: "Recorded surface history" })).not.toBeInTheDocument();
    rejectDestination(new Error("offline"));
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
    expect(window.location.search).toBe("?pack=nba_players&a=gamma&b=delta");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByLabelText("Profile A")).toHaveValue("Gamma"));
    expect(screen.getByLabelText("Profile B")).toHaveValue("Delta");
  });
});
