import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompareExperience } from "./CompareExperience";

const manifest = { entries: [
  { entity: "Alpha", card_path: "atlas/alpha.png", key_numbers: { career_pts_per36: 10 } },
  { entity: "Beta", card_path: "atlas/beta.png", key_numbers: { career_pts_per36: 14 } },
] };
const tennisManifest = { entries: [
  { entity: "Alpha (ATP)", card_path: "atlas/alpha.png", key_numbers: { hard_wr_career: 0.6 } },
  { entity: "Beta (ATP)", card_path: "atlas/beta.png", key_numbers: { hard_wr_career: 0.5 } },
] };
const percentiles = { packs: {
  nba_players: { n_in_pack: 2, fields: { career_pts_per36: { n_ranked: 2 } }, entities: { alpha: { career_pts_per36: 25 }, beta: { career_pts_per36: 75 } } },
  tennis: { n_in_pack: 2, fields: { hard_wr_career: { n_ranked: 2 } }, entities: { alpha: { hard_wr_career: 75 }, beta: { hard_wr_career: 25 } } },
  calibration: { n_in_pack: 2, fields: { career_pts_per36: { n_ranked: 2 } }, entities: { alpha: { career_pts_per36: 25 }, beta: { career_pts_per36: 75 } } },
} };

const swap = () => screen.getByRole("button", { name: "Swap profile A and profile B" });
const results = () => screen.queryByRole("table", { name: "Published values and within-pack percentile ranks" });
const profiles = () => [screen.getByLabelText("Profile A"), screen.getByLabelText("Profile B")];

describe("non-MLB comparison selection clearing", () => {
  beforeEach(() => {
    window.history.replaceState({ source: "test" }, "", "/analytics/compare?pack=nba_players&a=alpha&b=beta#details");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => Promise.resolve({
      ok: true,
      json: async () => String(input).includes("manifest") ? String(input).includes("tennis") ? tennisManifest : manifest : String(input).includes("percentiles") ? percentiles : { packs: {} },
    } as Response)));
  });

  it.each(["A", "B"])("clears %s in state and URL, then survives remount and popstate", async (slot) => {
    const view = render(<CompareExperience />);
    await waitFor(() => expect(results()).toBeInTheDocument());
    const index = slot === "A" ? 0 : 1;
    fireEvent.change(profiles()[index], { target: { value: "" } });
    const params = new URLSearchParams(window.location.search);
    expect(params.get(slot.toLowerCase())).toBe("");
    expect(params.get(slot === "A" ? "b" : "a")).toBe(slot === "A" ? "beta" : "alpha");
    expect(window.location.hash).toBe("#details");
    expect(window.history.state).toEqual({ source: "test" });
    expect(profiles()[index]).toHaveValue("");
    expect(swap()).toBeDisabled();
    expect(results()).not.toBeInTheDocument();
    view.unmount();
    render(<CompareExperience />);
    await waitFor(() => expect(profiles()[1 - index]).toHaveValue(slot === "A" ? "Beta" : "Alpha"));
    expect(profiles()[index]).toHaveValue("");
    expect(swap()).toBeDisabled();
    const clearedUrl = window.location.href;
    window.history.pushState({ source: "pop" }, "", "/analytics/compare?pack=nba_players&a=alpha&b=beta#details");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(profiles()[index]).toHaveValue(slot === "A" ? "Alpha" : "Beta"));
    window.history.pushState({ source: "pop" }, "", clearedUrl);
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(profiles()[index]).toHaveValue(""));
    expect(results()).not.toBeInTheDocument();
  });

  it("keeps both explicit empty slots clear, then restores a pair on reselect and swap", async () => {
    const view = render(<CompareExperience />);
    await waitFor(() => expect(results()).toBeInTheDocument());
    fireEvent.change(profiles()[0], { target: { value: "" } });
    fireEvent.change(profiles()[1], { target: { value: "" } });
    expect(window.location.search).toBe("?pack=nba_players&a=&b=");
    expect(swap()).toBeDisabled();
    expect(results()).not.toBeInTheDocument();
    view.unmount();
    render(<CompareExperience />);
    await waitFor(() => expect(profiles()[0]).toHaveValue(""));
    expect(profiles()[1]).toHaveValue("");
    expect(swap()).toBeDisabled();
    fireEvent.change(profiles()[0], { target: { value: "Alpha" } });
    expect(swap()).toBeDisabled();
    fireEvent.change(profiles()[1], { target: { value: "Beta" } });
    await waitFor(() => expect(results()).toBeInTheDocument());
    expect(window.location.search).toBe("?pack=nba_players&a=alpha&b=beta");
    fireEvent.click(swap());
    expect(window.location.search).toBe("?pack=nba_players&a=beta&b=alpha");
  });

  it.each(["A", "B"])("serializes the partial swap when %s is reselected as its counterpart", async (slot) => {
    render(<CompareExperience />);
    await waitFor(() => expect(results()).toBeInTheDocument());
    const index = slot === "A" ? 0 : 1;
    fireEvent.change(profiles()[index], { target: { value: "" } });
    fireEvent.change(profiles()[index], { target: { value: slot === "A" ? "Beta" : "Alpha" } });
    expect(profiles()[0]).toHaveValue(slot === "A" ? "Beta" : "");
    expect(profiles()[1]).toHaveValue(slot === "A" ? "" : "Alpha");
    expect(window.location.search).toBe(slot === "A" ? "?pack=nba_players&a=beta&b=" : "?pack=nba_players&a=&b=alpha");
    expect(swap()).toBeDisabled();
    expect(results()).not.toBeInTheDocument();
  });

  it.each(["A", "B"])("does not restore a stale counterpart after clearing %s again", async (slot) => {
    render(<CompareExperience />);
    await waitFor(() => expect(results()).toBeInTheDocument());
    const index = slot === "A" ? 0 : 1;
    fireEvent.change(profiles()[index], { target: { value: "" } });
    fireEvent.change(profiles()[index], { target: { value: slot === "A" ? "Beta" : "Alpha" } });
    fireEvent.change(profiles()[index], { target: { value: "" } });
    expect(profiles()[0]).toHaveValue("");
    expect(profiles()[1]).toHaveValue("");
    expect(window.location.search).toBe("?pack=nba_players&a=&b=");
    expect(swap()).toBeDisabled();
  });

  it.each(["A", "B"])("preserves the untouched URL selection when %s is cleared before the manifest loads", async (slot) => {
    let resolveManifest: (value: Response) => void = () => undefined;
    const pendingManifest = new Promise<Response>((resolve) => { resolveManifest = resolve; });
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => String(input).includes("manifest") ? pendingManifest : Promise.resolve({
      ok: true, json: async () => String(input).includes("percentiles") ? percentiles : { packs: {} },
    } as Response));
    render(<CompareExperience />);
    const index = slot === "A" ? 0 : 1;
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());
    fireEvent.change(profiles()[index], { target: { value: "Partial" } });
    fireEvent.change(profiles()[index], { target: { value: "" } });
    expect(window.location.search).toBe(slot === "A" ? "?pack=nba_players&a=&b=beta" : "?pack=nba_players&a=alpha&b=");
    resolveManifest({ ok: true, json: async () => manifest } as Response);
    await waitFor(() => expect(profiles()[1 - index]).toHaveValue(slot === "A" ? "Beta" : "Alpha"));
    expect(profiles()[index]).toHaveValue("");
    expect(swap()).toBeDisabled();
  });

  it("keeps the committed URL while a nonempty unmatched query is typed", async () => {
    render(<CompareExperience />);
    await waitFor(() => expect(results()).toBeInTheDocument());
    fireEvent.change(profiles()[0], { target: { value: "Al" } });
    expect(window.location.search).toBe("?pack=nba_players&a=alpha&b=beta");
    expect(results()).not.toBeInTheDocument();
    fireEvent.change(profiles()[0], { target: { value: "Alpha" } });
    expect(results()).toBeInTheDocument();
  });

  it.each(["?pack=nba_players", "?pack=nba_players&a=", "?pack=nba_players&b="])("distinguishes omitted defaults from explicit clearing: %s", async (search) => {
    window.history.replaceState(null, "", `/analytics/compare${search}`);
    render(<CompareExperience />);
    await waitFor(() => expect(profiles()[search.includes("a=") ? 1 : 0]).toHaveValue(search.includes("a=") ? "Beta" : "Alpha"));
    if (search.includes("a=")) expect(profiles()[0]).toHaveValue("");
    else if (search.includes("b=")) expect(profiles()[1]).toHaveValue("");
    else expect(results()).toBeInTheDocument();
  });

  it.each(["tennis", "calibration"])("preserves %s context when clearing a slot", async (pack) => {
    const surface = pack === "tennis" ? "&surface=clay" : "";
    window.history.replaceState(null, "", `/analytics/compare?pack=${pack}&a=alpha&b=beta${surface}`);
    render(<CompareExperience />);
    await waitFor(() => expect(profiles()[0]).toHaveValue(pack === "tennis" ? "Alpha (ATP)" : "Alpha"));
    fireEvent.change(profiles()[0], { target: { value: "" } });
    expect(window.location.search).toBe(`?pack=${pack}&a=&b=beta${surface}`);
    expect(profiles()[0]).toHaveValue("");
    expect(swap()).toBeDisabled();
  });
});
