import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompareExperience } from "./CompareExperience";

const manifest = { entries: [
  { entity: "Alpha", card_path: "atlas/alpha.png", floors: "alpha published floor", status: "complete", key_numbers: { career_pts_per36: 10 } },
  { entity: "Beta", card_path: "atlas/beta.png", floors: "beta published floor", key_numbers: { career_pts_per36: 14 } },
] };
const percentiles = { packs: { nba_players: { n_in_pack: 2, fields: { career_pts_per36: { n_ranked: 2 } }, entities: { alpha: { career_pts_per36: 25 }, beta: { career_pts_per36: 75 } } } } };
const comparables = { packs: { nba_players: { entities: { alpha: { similar: [{ slug: "beta" }] } } } } };
const invalidRankManifest = { entries: [
  { entity: "Alpha", card_path: "atlas/alpha.png", key_numbers: { null_raw: null, zero_raw: 0, nan_raw: NaN, infinite_raw: Infinity, out_of_range: 8 } },
  { entity: "Beta", card_path: "atlas/beta.png", key_numbers: { null_raw: 4, zero_raw: 2, nan_raw: 4, infinite_raw: 4, out_of_range: 4 } },
] };
const invalidRankPercentiles = { packs: { nba_players: { n_in_pack: 2, fields: {
  null_raw: { n_ranked: 2 }, zero_raw: { n_ranked: 2 }, nan_raw: { n_ranked: 2 }, infinite_raw: { n_ranked: 2 }, out_of_range: { n_ranked: 2 },
}, entities: { alpha: { null_raw: 50, zero_raw: 0, nan_raw: 50, infinite_raw: 50, out_of_range: 101 }, beta: { null_raw: 50, zero_raw: 50, nan_raw: NaN, infinite_raw: Infinity, out_of_range: -1 } } } } };
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
const pitchManifest = { entries: [
  { entity: "pitch_type:FF", card_path: "atlas/ff.png", as_of: "2025-09-28", key_numbers: { n_pitches: 100, count_leverage_pct: { pitcher_ahead: 30, even: 40, pitcher_behind: 30 } } },
  { entity: "pitch_type:SC", card_path: "atlas/sc.png", as_of: "2025-09-28", key_numbers: { n_pitches: 7, count_leverage_pct: { pitcher_ahead: 0, even: 42.9, pitcher_behind: 57.1 } } },
] };
const pitchPercentiles = { packs: { mlb_pitch: { n_in_pack: 2, fields: { n_pitches: { n_ranked: 2 } }, entities: { ff: { n_pitches: 90 }, sc: { n_pitches: 10 } } } } };
const mixedPitchManifest = { entries: [
  { entity: "pitch_type:FF", card_path: "atlas/ff.png", key_numbers: { n_pitches: 100, count_leverage_pct: { pitcher_ahead: 30, even: 40, pitcher_behind: 30 } } },
  { entity: "team:NYY", card_path: "atlas/nyy.png", key_numbers: { n_pitches: 200 } },
] };

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
    expect(screen.getAllByText("Ranked among 2 profiles").length).toBeGreaterThan(0);
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

  it("renders ranks only for finite raw values and published 0-100 percentiles", async () => {
    vi.mocked(fetch).mockImplementation((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("atlas_nba_manifest") ? invalidRankManifest : url.includes("percentiles") ? invalidRankPercentiles : comparables } as Response));
    render(<CompareExperience />);
    expect(await screen.findByText("0th percentile")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "0th percentile visual bar" })).toBeInTheDocument();
    expect(screen.getAllByText("Ranked among 2 profiles")).toHaveLength(3);
    expect(screen.getAllByText("Not ranked").length).toBeGreaterThanOrEqual(7);
    expect(screen.queryByText("101st percentile")).not.toBeInTheDocument();
    expect(screen.queryByText("-1st percentile")).not.toBeInTheDocument();
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
    const evidence = screen.getAllByText("Published evidence");
    fireEvent.click(evidence[0]);
    fireEvent.click(evidence[1]);
    expect(screen.getByText(/alpha published floor/)).toBeInTheDocument();
    expect(screen.getByText(/beta published floor/)).toBeInTheDocument();
    expect(screen.getByText("Status:")).toBeInTheDocument();
    expect(screen.getByText("complete")).toBeInTheDocument();
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

  it("mounts recorded count context only for the MLB pitch-type pack", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&a=ff&b=sc");
    vi.mocked(fetch).mockImplementation((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("atlas_mlb_pitch_manifest") ? pitchManifest : url.includes("percentiles") ? pitchPercentiles : comparables } as Response));
    render(<CompareExperience />);
    expect(await screen.findByRole("heading", { name: "Recorded count context" })).toBeInTheDocument();
    expect(screen.getByText("0.0%")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Published raw values" })).toBeInTheDocument();
    expect(screen.queryByText("90th percentile")).not.toBeInTheDocument();
    expect(screen.getByText(/Source percentiles mix pitch types, teams, and count states/)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "MLB pitch atlas" })).toBeInTheDocument();
  });

  it("keeps MLB atlas headers but blocks mixed-family comparisons", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&a=ff&b=nyy");
    vi.mocked(fetch).mockImplementation((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("atlas_mlb_pitch_manifest") ? mixedPitchManifest : url.includes("percentiles") ? pitchPercentiles : comparables } as Response));
    render(<CompareExperience />);
    expect(await screen.findByText(/Choose two pitch types, two teams, or two count states/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "pitch type FF" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "team NYY" })).toBeInTheDocument();
    expect(screen.queryByText("Published evidence")).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Published raw values" })).not.toBeInTheDocument();
  });
});
