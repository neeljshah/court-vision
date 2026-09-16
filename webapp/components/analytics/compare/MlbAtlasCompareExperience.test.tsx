import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CompareExperience } from "./CompareExperience";

const comparables = { packs: {} };
const pitchManifest = { entries: [
  { entity: "pitch_type:FF", card_path: "atlas/ff.png", as_of: "2025-09-28", key_numbers: { n_pitches: 100, count_leverage_pct: { pitcher_ahead: 30, even: 40, pitcher_behind: 30 } } },
  { entity: "pitch_type:SC", card_path: "atlas/sc.png", as_of: "2025-09-28", key_numbers: { n_pitches: 7, count_leverage_pct: { pitcher_ahead: 0, even: 42.9, pitcher_behind: 57.1 } } },
] };
const pitchPercentiles = { packs: { mlb_pitch: { n_in_pack: 2, fields: { n_pitches: { n_ranked: 2 } }, entities: { ff: { n_pitches: 90 }, sc: { n_pitches: 10 } } } } };
const mixedPitchManifest = { entries: [
  { entity: "pitch_type:FF", card_path: "atlas/ff.png", key_numbers: { n_pitches: 100, count_leverage_pct: { pitcher_ahead: 30, even: 40, pitcher_behind: 30 } } },
  { entity: "team:NYY", card_path: "atlas/nyy.png", key_numbers: { n_pitches: 200 } },
] };
const familyPitchManifest = { entries: [
  ...pitchManifest.entries,
  { entity: "team:NYY", card_path: "atlas/nyy.png", key_numbers: { n_pitches: 200 } },
  { entity: "team:BOS", card_path: "atlas/bos.png", key_numbers: { n_pitches: 180 } },
  { entity: "count:0-0", card_path: "atlas/count00.png", key_numbers: { n_pitches: 90 } },
  { entity: "count:1-2", card_path: "atlas/count12.png", key_numbers: { n_pitches: 80 } },
] };
const familyPitchPercentiles = { packs: { mlb_pitch: { n_in_pack: 6, fields: { n_pitches: { n_ranked: 6 } }, entities: { ff: { n_pitches: 90 }, sc: { n_pitches: 10 }, nyy: { n_pitches: 80 }, bos: { n_pitches: 60 }, count00: { n_pitches: 50 }, count12: { n_pitches: 40 } } } } };
const datalistValues = (id: string) => Array.from(document.querySelectorAll(`#${id} option`)).map((option) => option.getAttribute("value"));
const mockFamilyFetch = () => vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, _init?: RequestInit) => { const url = String(input); return Promise.resolve({ ok: true, json: async () => url.includes("atlas_mlb_pitch_manifest") ? familyPitchManifest : url.includes("percentiles") ? familyPitchPercentiles : comparables } as Response); });

describe("MLB atlas comparison controls", () => {
  beforeEach(() => { window.history.replaceState(null, "", "/analytics/compare"); vi.stubGlobal("fetch", vi.fn()); });

  it("shows count context for same-family pitch types without percentile claims", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&a=ff&b=sc");
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, _init?: RequestInit) => { const url = String(input); return Promise.resolve({ ok: true, json: async () => url.includes("atlas_mlb_pitch_manifest") ? pitchManifest : url.includes("percentiles") ? pitchPercentiles : comparables } as Response); });
    render(<CompareExperience />);
    expect(await screen.findByRole("heading", { name: "Recorded count context" })).toBeInTheDocument();
    expect(screen.getByText("0.0%")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Published raw values" })).toBeInTheDocument();
    expect(screen.queryByText("90th percentile")).not.toBeInTheDocument();
    expect(screen.getByText(/Source percentiles mix pitch types, teams, and count states/)).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "MLB pitch atlas" })).toBeInTheDocument();
    expect(window.location.search).not.toContain("family=");
  });

  it("restores incomplete family links and filters sharable record selections", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&family=team");
    mockFamilyFetch(); render(<CompareExperience />);
    const family = await screen.findByLabelText("MLB atlas record type");
    await waitFor(() => expect(screen.getByRole("option", { name: "Pitch types (2)" })).toBeInTheDocument());
    expect(family).toHaveValue("team");
    expect(screen.getByRole("option", { name: "Teams (2)" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Count states (2)" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Profile A"), { target: { value: "team NYY" } });
    await waitFor(() => expect(window.location.search).toBe("?pack=mlb_pitch&family=team&a=nyy"));
    expect(datalistValues("compare-entities-a")).toEqual(["team NYY", "team BOS"]);
    expect(datalistValues("compare-entities-b")).toEqual(["team BOS"]);
    fireEvent.change(family, { target: { value: "team" } });
    expect(screen.getByLabelText("Profile A")).toHaveValue("team NYY");
    fireEvent.change(screen.getByLabelText("Profile B"), { target: { value: "team BOS" } });
    await waitFor(() => expect(window.location.search).toBe("?pack=mlb_pitch&family=team&a=nyy&b=bos"));
  });

  it("keeps the active family and clears only after a new family choice", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&a=ff&b=sc");
    mockFamilyFetch(); render(<CompareExperience />);
    expect(await screen.findByRole("heading", { name: "pitch type FF" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("MLB atlas record type"), { target: { value: "pitch_type" } });
    expect(window.location.search).toBe("?pack=mlb_pitch&a=ff&b=sc");
    fireEvent.change(screen.getByLabelText("MLB atlas record type"), { target: { value: "count" } });
    await waitFor(() => expect(window.location.search).toBe("?pack=mlb_pitch&family=count"));
  });

  it("restores partial and contradictory MLB links honestly", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&family=count");
    mockFamilyFetch(); render(<CompareExperience />);
    await screen.findByRole("option", { name: "Pitch types (2)" });
    window.history.pushState(null, "", "/analytics/compare?pack=mlb_pitch&a=nyy");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(screen.getByLabelText("Profile A")).toHaveValue("team NYY"));
    expect(screen.getByLabelText("Profile B")).toHaveValue("");
    window.history.pushState(null, "", "/analytics/compare?pack=mlb_pitch&b=bos");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(screen.getByLabelText("Profile A")).toHaveValue(""));
    expect(screen.getByLabelText("Profile B")).toHaveValue("team BOS");
    window.history.pushState(null, "", "/analytics/compare?pack=mlb_pitch&family=pitch_type&a=nyy&b=bos");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(screen.getByLabelText("MLB atlas record type")).toHaveValue("team"));
    await waitFor(() => expect(window.location.search).toBe("?pack=mlb_pitch&a=nyy&b=bos"));
  });

  it("serializes a cleared MLB input without restoring its old profile", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&family=team&a=nyy&b=bos");
    mockFamilyFetch(); render(<CompareExperience />);
    const aInput = await screen.findByLabelText("Profile A");
    await waitFor(() => expect(aInput).toHaveValue("team NYY"));
    fireEvent.change(aInput, { target: { value: "" } });
    await waitFor(() => expect(window.location.search).toBe("?pack=mlb_pitch&family=team&b=bos"));
  });

  it("keeps mixed legacy headers visible while withholding the comparison", async () => {
    window.history.replaceState(null, "", "/analytics/compare?pack=mlb_pitch&a=ff&b=nyy");
    mockFamilyFetch(); render(<CompareExperience />);
    await waitFor(() => expect(screen.getByText(/Choose two pitch types, two teams, or two count states/)).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "pitch type FF" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "team NYY" })).toBeInTheDocument();
    expect(screen.getByLabelText("MLB atlas record type")).toHaveValue("");
    expect(window.location.search).toBe("?pack=mlb_pitch&a=ff&b=nyy");
    expect(screen.queryByRole("table", { name: "Published raw values" })).not.toBeInTheDocument();
  });
});
