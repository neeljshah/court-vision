import { render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { JoinedFindings } from "./JoinedFindings";
import { joinedFindingTarget } from "@/lib/analytics/related";

describe("JoinedFindings", () => {
  it("sends a joined artifact to the analysis that uses its source", () => {
    render(<JoinedFindings pack="nba_teams" coverage={{ n_in_pack: 30, schedule_fatigue_tax: 30 }} items={[{
      key: "schedule_fatigue_tax", label: "Schedule Fatigue Tax", value: "Observed value", source_artifact: "scripts/platformkit/analytics_showcase/out/novel_schedule_fatigue_tax.json", confound: "Raw descriptive rows.",
    }]} />);
    expect(screen.getByRole("link", { name: "Read analysis" })).toHaveAttribute("href", expect.stringContaining("/analytics/research/"));
  });

  it("does not invent a target when the artifact is not in the public manifest", () => {
    render(<JoinedFindings pack="nba_teams" coverage={{ n_in_pack: 30 }} items={[{
      key: "unknown", label: "Unknown", value: "Observed value", source_artifact: "out/not_published.json", confound: "No published source.",
    }]} />);
    expect(screen.queryByRole("link", { name: /Read (analysis|source module)/ })).not.toBeInTheDocument();
  });

  it("resolves every published entity join to an analysis before falling back to a module", () => {
    const joins = JSON.parse(readFileSync(join(process.cwd(), "public", "data", "showcase", "entity_joins.json"), "utf8")) as { packs: Record<string, { entities: Record<string, { items: { source_artifact: string }[] }> }> };
    const items = Object.values(joins.packs).flatMap((pack) => Object.values(pack.entities).flatMap((entity) => entity.items));
    const targets = items.map((item) => joinedFindingTarget(item.source_artifact));
    expect(targets).toHaveLength(items.length);
    expect(targets.every((target) => target?.kind === "analysis")).toBe(true);
  });
});
