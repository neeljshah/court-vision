import { describe, expect, it } from "vitest";
import { relatedReading } from "./related";

const entries = [
  { id: "rim", title: "Rim shot chart", kind: "module" as const, sport: "nba", asOf: "2026-07-01", href: "/m/rim/", sources: ["rim"], artifacts: ["rim"] },
  { id: "rim-study", title: "Rim deterrence profile", kind: "analysis" as const, sport: "nba", asOf: null, href: "/r/rim-study/", sources: ["rim"], artifacts: ["rim-study"] },
  { id: "rim-finding", title: "Who bends the shot chart", kind: "finding" as const, sport: "nba", asOf: null, href: "/f/rim-finding/", artifacts: ["rim"] },
  { id: "nba-other", title: "NBA schedule", kind: "module" as const, sport: "nba", asOf: null, href: "/m/nba-other/", sources: ["nba-other"], artifacts: ["nba-other"] },
  { id: "shot", title: "Shot chart context", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/shot/", sources: ["shot"], artifacts: ["shot"] },
];

describe("relatedReading", () => {
  it("prioritizes shared source, artifact, sport, then title words deterministically", () => {
    expect(relatedReading("module", "rim", entries)).toMatchObject([
      { id: "rim-study", purpose: "supporting source" }, { id: "rim-finding", purpose: "prerequisite" }, { id: "nba-other", purpose: "same population" }, { id: "shot", purpose: "prerequisite" },
    ]);
  });
});
