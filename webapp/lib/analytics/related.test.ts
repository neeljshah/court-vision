import { describe, expect, it } from "vitest";
import { relatedReading } from "./related";

const entries = [
  { id: "rim", title: "Rim shot chart", kind: "module" as const, sport: "nba", asOf: "2026-07-01", href: "/m/rim/", sources: ["rim"], artifacts: ["rim"], population: "nba players" },
  { id: "rim-study", title: "Rim deterrence profile", kind: "analysis" as const, sport: "nba", asOf: null, href: "/r/rim-study/", sources: ["rim"], artifacts: ["rim-study"], population: "nba players" },
  { id: "rim-finding", title: "Who bends the shot chart", kind: "finding" as const, sport: "nba", asOf: null, href: "/f/rim-finding/", artifacts: ["rim"], population: "nba players" },
  { id: "nba-other", title: "NBA schedule", kind: "module" as const, sport: "nba", asOf: null, href: "/m/nba-other/", sources: ["nba-other"], artifacts: ["nba-other"], population: "nba teams" },
  { id: "shot", title: "Shot chart context", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/shot/", sources: ["shot"], artifacts: ["shot"], population: "mlb pitch types" },
];

describe("relatedReading", () => {
  it("prioritizes source evidence, authored relationships, population, then sport deterministically", () => {
    expect(relatedReading("module", "rim", entries)).toMatchObject([
      { id: "rim-study", purpose: "supporting source" }, { id: "rim-finding", purpose: "supporting source" }, { id: "nba-other", purpose: "same sport" },
    ]);
  });

  it("labels MLB pitch velocity and batter contact as the same sport, not the same population", () => {
    const velocity = { id: "mlb-velocity-shape", title: "Pitch Velocity Shape", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/velocity/", population: "mlb pitch types" };
    const contact = { id: "mlb-batter-p90-minus-mean-exit-velocity", title: "Batter Contact", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/contact/", population: "mlb batters" };
    expect(relatedReading("analysis", "mlb-velocity-shape", [velocity, contact])).toMatchObject([{ id: "mlb-batter-p90-minus-mean-exit-velocity", purpose: "same sport" }]);
  });

  it("accepts identical population identifiers and never makes title overlap a prerequisite", () => {
    const first = { id: "first", title: "Shared language", kind: "analysis" as const, sport: "nba", asOf: null, href: "/r/first/", population: "nba players" };
    const samePopulation = { id: "same", title: "Different measure", kind: "analysis" as const, sport: "nba", asOf: null, href: "/r/same/", population: "nba players" };
    const titleOnly = { id: "title", title: "Shared language", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/title/", population: "mlb batters" };
    const links = relatedReading("analysis", "first", [first, samePopulation, titleOnly]);
    expect(links).toMatchObject([{ id: "same", purpose: "same population" }]);
    expect(links.find(link => link.id === "title")).toBeUndefined();
  });
});
