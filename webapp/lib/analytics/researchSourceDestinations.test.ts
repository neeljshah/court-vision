import { describe, expect, it } from "vitest";
import { resolveResearchSourceDestination } from "./researchSourceDestinations";

describe("research source destinations", () => {
  it("resolves published modules to their module page", () => {
    expect(resolveResearchSourceDestination("ctx_team_states")).toEqual({ kind: "module", href: "/analytics/m/ctx_team_states" });
  });

  it("resolves atlas manifests to their published pack anchors", () => {
    expect(resolveResearchSourceDestination("atlas_nba_teams_manifest")).toEqual({ kind: "atlas", href: "/analytics/players#nba_teams" });
    expect(resolveResearchSourceDestination("atlas_nba_manifest")).toEqual({ kind: "atlas", href: "/analytics/players#nba_players" });
  });

  it("falls back to source JSON without fabricating a module route", () => {
    const destination = resolveResearchSourceDestination("unlisted_snapshot");
    expect(destination).toEqual({ kind: "json", href: "/data/showcase/unlisted_snapshot.json" });
    expect(destination.href).not.toContain("/analytics/m/");
    expect(resolveResearchSourceDestination("atlas_nba_manifest").href).not.toContain("/analytics/m/");
  });
});
