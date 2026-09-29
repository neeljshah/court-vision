import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { observationPeriod, ResearchSourceContext, sourceHref } from "./ResearchSourceContext";
import loadBearingSource from "@/public/data/showcase/novel_load_bearing_index.json";

afterEach(() => vi.unstubAllGlobals());

describe("ResearchSourceContext", () => {
  it("keeps row windows distinct from source coverage beside their snapshot dates", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve({ ok: true, json: async () => url.includes("nba_q4_shift")
      ? { observation_window: { seasons: "2024-25, 2025-26 present in this cache" } }
      : { seasons: { "2024_25": {}, "2025_26": {} } } })));
    render(<ResearchSourceContext fields={[
      { key: "shift", label: "Q4 shift", unit: "number", sourceId: "nba_q4_shift" },
      { key: "delta", label: "Net rating delta", unit: "number", sourceId: "on_off_showcase" },
    ]} sources={[
      { id: "nba_q4_shift", asOf: "2026-07-24", fields: ["shift"], rowWindows: { shift: ["2025-26"] } },
      { id: "on_off_showcase", asOf: "not recorded", fields: ["delta"], rowWindows: { delta: ["2025-26"] } },
    ]} />);
    const context = screen.getByLabelText("Source context");
    await waitFor(() => expect(within(context).getByText("Source coverage: 2024-25, 2025-26 present in this cache")).toBeInTheDocument());
    expect(within(context).getByText("Source coverage: 2024-25, 2025-26")).toBeInTheDocument();
    expect(within(context).getByText("Row window: Q4 shift: 2025-26")).toBeInTheDocument();
    expect(within(context).getByText("Row window: Net rating delta: 2025-26")).toBeInTheDocument();
    expect(within(context).getByText("Snapshot date: 2026-07-24")).toBeInTheDocument();
    expect(within(context).getByText("Feeds: Q4 shift")).toBeInTheDocument();
    expect(within(context).getByRole("link", { name: "nba_q4_shift" })).toHaveAttribute("href", "/analytics/m/nba_q4_shift");
    expect(within(context).getByRole("link", { name: "on_off_showcase" })).toHaveAttribute("href", "/analytics/m/on_off_showcase");
  });

  it("reports an unrecorded period when the published module has no window", () => {
    expect(observationPeriod({ label: "No window" })).toBeNull();
  });

  it("preserves the published estimator windows separately without inventing shared coverage", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => loadBearingSource }));
    render(<ResearchSourceContext fields={[
      { key: "delta_a", label: "Fragility delta, estimator A", unit: "pp", sourceId: "novel_load_bearing_index" },
      { key: "delta_b", label: "Fragility delta, estimator B", unit: "pp", sourceId: "novel_load_bearing_index" },
    ]} sources={[{ id: "novel_load_bearing_index", asOf: "not published" }]} />);
    const context = screen.getByLabelText("Source context");
    await waitFor(() => expect(within(context).getByText(`Source as of, Estimator A: ${loadBearingSource.as_of.estimator_a}`)).toBeVisible());
    expect(within(context).getByText(`Source as of, Estimator B: ${loadBearingSource.as_of.estimator_b}`)).toBeVisible();
    expect(within(context).getByText("Source coverage: not recorded")).toBeVisible();
    expect(within(context).getByText("Snapshot date: not published")).toBeVisible();
    expect(within(context).getByText("Row window: not recorded")).toBeVisible();
    expect(within(context).getByText("Feeds: Fragility delta, estimator A, Fragility delta, estimator B")).toBeVisible();
    expect(observationPeriod(loadBearingSource)).toBeNull();
  });

  it("keeps explicit observation coverage and unknown as-of labels distinct", async () => {
    const document = {
      observation_window: { start: "2025-01-01", end: "2025-12-31" },
      as_of: { source_checkpoint: "2026-02-01", empty: " ", absent: null, numeric: 2026, nested: { start: "2020" }, " ": "2026-01-01" },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => document }));
    render(<ResearchSourceContext fields={[]} sources={[{ id: "test-source", asOf: "2026-03-01" }]} />);
    const context = screen.getByLabelText("Source context");
    await waitFor(() => expect(within(context).getByText("Source as of, source_checkpoint: 2026-02-01")).toBeVisible());
    expect(within(context).getByText("Source coverage: 2025-01-01 to 2025-12-31")).toBeVisible();
    expect(within(context).getByText("Snapshot date: 2026-03-01")).toBeVisible();
    expect(within(context).getAllByText(/^Source as of,/)).toHaveLength(1);
    expect(observationPeriod({ as_of: document.as_of, seasons: { "2024_25": {} } })).toBe("2024-25");
  });

  it("does not infer coverage or named details from scalar or malformed as-of metadata", async () => {
    for (const as_of of ["2026-01-01", ["2024-25", "2025-26"], null, { empty: "", numeric: 2026 }]) {
      expect(observationPeriod({ as_of })).toBeNull();
    }
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({
      observation_window: { seasons: "Fixture season" }, as_of: ["2024-25", "2025-26"],
    }) }));
    render(<ResearchSourceContext fields={[]} sources={[{ id: "test-source", asOf: "not recorded" }]} />);
    await waitFor(() => expect(screen.getByText("Source coverage: Fixture season")).toBeVisible());
    expect(screen.queryByText(/^Source as of,/)).not.toBeInTheDocument();
  });

});

it("uses real atlas pack and module routes", () => {
  expect(sourceHref("atlas_nba_teams_manifest")).toBe("/analytics/players#nba_teams");
  expect(sourceHref("ctx_team_states")).toBe("/analytics/m/ctx_team_states");
});
