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

  it("does not call MLB team or count readings the same population as pitch types", () => {
    const pitch = { id: "pitch", title: "Pitch type shape", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/pitch/", population: "mlb_pitch_types" };
    const team = { id: "team", title: "Team totals", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/team/", population: "mlb_teams" };
    const count = { id: "count", title: "Count state", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/count/", population: "mlb_count_states" };
    const links = relatedReading("analysis", "pitch", [pitch, team, count]);
    expect(links).toMatchObject([{ id: "count", purpose: "same sport" }, { id: "team", purpose: "same sport" }]);
  });

  it("labels two readings from one source file without claiming one population", () => {
    const first = { id: "first", title: "First result", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/first/", sources: ["shared"], population: "analysis:first" };
    const second = { id: "second", title: "Second result", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/second/", sources: ["shared"], population: "analysis:second" };
    expect(relatedReading("analysis", "first", [first, second])).toMatchObject([{ id: "second", purpose: "same source file" }]);
  });

  it("uses same entity type only when the sport matches but population ids differ", () => {
    const team = { id: "team", title: "Team profile", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/team/", population: "mlb_team_profile", entityType: "team" };
    const roster = { id: "roster", title: "Team roster", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/roster/", population: "mlb_team_roster", entityType: "team" };
    const pitch = { id: "pitch", title: "Pitch type", kind: "analysis" as const, sport: "mlb", asOf: null, href: "/r/pitch/", population: "mlb_pitch_types", entityType: "pitch type" };
    expect(relatedReading("analysis", "team", [team, roster, pitch])).toMatchObject([
      { id: "roster", purpose: "same entity type" }, { id: "pitch", purpose: "same sport" },
    ]);
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
