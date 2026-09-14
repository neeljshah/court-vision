import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompareExperience } from "./CompareExperience";

const manifest = { entries: [
  { entity: "Alpha", card_path: "atlas/alpha.png", key_numbers: { career_pts_per36: 10 } },
  { entity: "Beta", card_path: "atlas/beta.png", key_numbers: { career_pts_per36: 14 } },
] };
const percentiles = { packs: { nba_players: { n_in_pack: 2, fields: { career_pts_per36: { n_ranked: 2 } }, entities: { alpha: { career_pts_per36: 25 }, beta: { career_pts_per36: 75 } } } } };
const comparables = { packs: { nba_players: { entities: { alpha: { similar: [{ slug: "beta" }] } } } } };

describe("CompareExperience controls", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/analytics/compare");
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({
      ok: true,
      json: async () => url.includes("atlas_nba_manifest") ? manifest : url.includes("percentiles") ? percentiles : comparables,
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
});
