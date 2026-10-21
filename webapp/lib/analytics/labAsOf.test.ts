import { describe, expect, it } from "vitest";
import { getLabData } from "./labData";
import { sourceAsOf } from "./labHelpers";

const datasets = getLabData().datasets;
const find = (id: string) => datasets.find(dataset => dataset.id === id)!;
const unique = (id: string, key: "sport" | "population" | "observationWindow") => Array.from(new Set(find(id).rows.map(row => row.definition?.[key])));

describe("sourceAsOf", () => {
  it("reads the first published generation stamp and names its field", () => {
    expect(sourceAsOf({ as_of: "2026-04-12" })).toEqual({ date: "2026-04-12", field: "as_of" });
    expect(sourceAsOf({ generated_at: "2026-07-25T04:25:58.801043+00:00" })).toEqual({ date: "2026-07-25", field: "generated_at" });
    expect(sourceAsOf({ built_at: "2026-01-02 03:04:05" })).toEqual({ date: "2026-01-02", field: "built_at" });
    expect(sourceAsOf({ as_of: "2026-04-12", generated_at: "2026-07-25T00:00:00Z" })).toEqual({ date: "2026-04-12", field: "as_of" });
  });
  it("never invents a date from a period label, an invalid day, or a missing field", () => {
    expect(sourceAsOf({ as_of: { estimator_a: "2024-25" }, generated_at: "2026-07-25T04:12:47Z" })).toEqual({ date: "2026-07-25", field: "generated_at" });
    expect(sourceAsOf({ as_of: "2025-26 regular season (through 2026-04-12)" })).toBeUndefined();
    expect(sourceAsOf({ as_of: "2026-02-30" })).toBeUndefined();
    expect(sourceAsOf({ status: "ok" })).toBeUndefined();
    expect(sourceAsOf(null)).toBeUndefined();
    expect(sourceAsOf([])).toBeUndefined();
  });
});

describe("lab dataset as-of stamps", () => {
  it.each([
    ["pitch-profiles", undefined],
    ["nba-consistency", { date: "2026-04-12", field: "as_of" }],
    ["lineup-synergy", { date: "2026-07-25", field: "generated_at" }],
    ["rim-deterrence", { date: "2026-07-25", field: "generated_at" }],
    ["soccer-home-advantage", { date: "2026-07-25", field: "generated_at" }],
    ["tennis-atp_career-clay", undefined],
    ["line-half-life", { date: "2026-07-25", field: "as_of" }],
    ["live-clock", { date: "2026-09-17", field: "as_of" }],
    ["load-bearing", undefined],
    ["market-foresight", { date: "2026-09-17", field: "as_of" }],
    ["overreaction-gap", undefined],
    ["schedule-fatigue", undefined],
  ])("%s carries exactly the stamp its source JSON publishes", (id, expected) => {
    expect(find(id).publishedAsOf).toEqual(expected);
  });
  it("leaves every tennis view unstamped because the shared source publishes no stamp", () => {
    const tennis = datasets.filter(dataset => dataset.id.startsWith("tennis-"));
    expect(tennis).toHaveLength(8);
    expect(tennis.every(dataset => dataset.publishedAsOf === undefined)).toBe(true);
  });
});

describe("published cohort definitions", () => {
  it("fills sport, population and window from the source JSON where it publishes them", () => {
    expect(unique("pitch-profiles", "sport")).toEqual(["MLB"]);
    expect(unique("pitch-profiles", "population")).toEqual(["693,037 pitches"]);
    expect(unique("pitch-profiles", "observationWindow")).toEqual(["2025 Statcast pull (season named by the source path; exact dates not published)"]);
    expect(unique("nba-consistency", "sport")).toEqual(["NBA"]);
    expect(unique("nba-consistency", "population")).toEqual(["579 players meeting the floor of 807 source players; games at or above 10 minutes; at least 15 qualifying appearances"]);
    expect(unique("nba-consistency", "observationWindow")).toEqual(["2023-24, 2024-25, 2025-26 pooled; as of 2026-04-12"]);
    expect(unique("lineup-synergy", "population")).toEqual(["102 qualified five-man lineups (all five members qualify for individual on/off)"]);
    expect(unique("lineup-synergy", "observationWindow")).toEqual(["2024-25"]);
    expect(unique("rim-deterrence", "population")).toEqual(["370 qualified players; 500 on-court minute floor", "387 qualified players; 500 on-court minute floor"]);
    expect(unique("rim-deterrence", "observationWindow")).toEqual(["2025-26 (complete NBA season)", "2024-25 (complete NBA season)"]);
    expect(unique("tennis-atp_career-clay", "sport")).toEqual(["Tennis"]);
    expect(unique("tennis-atp_career-clay", "population")).toEqual(["1,261 players in the ATP career snapshot; floor clay_n>=25 AND hard_n>=25"]);
    expect(unique("tennis-atp_recent_form-grass", "population")).toEqual(["663 players in the ATP recent form snapshot; floor grass_n>=15"]);
    expect(unique("load-bearing", "population")).toEqual(["30 teams (one published row per team)"]);
    expect(unique("load-bearing", "observationWindow")).toEqual(["Estimator A: 2024-25 (Elo end-of-season) x 2024_25 on/off slice; Estimator B: 2025-26 regular season (through 2026-04-12)"]);
    expect(unique("overreaction-gap", "sport")).toEqual(["INTERNATIONAL SOCCER", "MLB"]);
    expect(unique("schedule-fatigue", "population")).toEqual(["90 published team-seasons"]);
  });
  it("keeps a field unpublished when no source file carries it", () => {
    expect(unique("lineup-synergy", "sport")).toEqual([undefined]);
    expect(unique("load-bearing", "sport")).toEqual([undefined]);
    expect(unique("schedule-fatigue", "sport")).toEqual([undefined]);
    expect(unique("tennis-atp_career-clay", "observationWindow")).toEqual([undefined]);
    expect(unique("live-clock", "observationWindow")).toEqual([undefined]);
    expect(unique("market-foresight", "population")).toEqual([undefined]);
    expect(unique("market-foresight", "observationWindow")).toEqual([undefined]);
    expect(unique("overreaction-gap", "population")).toEqual([undefined]);
    expect(unique("overreaction-gap", "observationWindow")).toEqual([undefined]);
    expect(unique("schedule-fatigue", "observationWindow")).toEqual([undefined]);
  });
});
