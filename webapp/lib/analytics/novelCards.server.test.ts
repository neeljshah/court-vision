import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { estimatorWindows, formatNovelSnapshot, getNovelCards } from "./novelCards.server";

const showcase = join(process.cwd(), "public", "data", "showcase");
const readJson = <T,>(file: string): T => JSON.parse(readFileSync(join(showcase, file), "utf8")) as T;
type Row = Record<string, unknown>;
const row = (value: unknown): Row => value && typeof value === "object" && !Array.isArray(value) ? value as Row : {};

describe("getNovelCards", () => {
  it("returns one complete card for every published index entry", () => {
    const index = readJson<{ stats: Array<{ module: string }> }>("novel_stats_index.json");
    const cards = getNovelCards();

    expect(cards).toHaveLength(index.stats.length);
    for (const card of cards) {
      expect(card.lead).not.toBe("");
      expect(card.denominator).not.toBe("");
      expect(card.result).not.toBe("");
    }
  });

  it("reads the three newest leads from their own artifact panels", () => {
    const cards = getNovelCards();
    const rest = readJson<Row>("novel_rest_asymmetry.json");
    const starter = readJson<Row>("novel_starter_rest_absorption.json");
    const pitch = readJson<Row>("novel_pitch_repeat_excess.json");
    const restContrast = (row(rest.panels).contrast_vs_equal_rest as Row[]).find((item) => item.cell === "home +2 or more") || {};
    const starterCells = row(row(starter.panels).rest_buckets).cells as Row[];
    const pitchOverall = (row(row(pitch.panels).overall).cells as Row[])[0];

    expect(cards.find((card) => card.id === "novel_rest_asymmetry")?.lead).toBe(String(restContrast.delta_vs_equal));
    expect(cards.find((card) => card.id === "novel_starter_rest_absorption")?.lead).toBe(starterCells.filter((cell) => ["4", "5", "6 or more"].includes(String(cell.cell))).map((cell) => String(cell.win_frequency)).join(" / "));
    expect(cards.find((card) => card.id === "novel_pitch_repeat_excess")?.lead).toBe(String(pitchOverall.excess));
  });

  it("keeps mock source, generated, index, and estimator-window provenance distinct", () => {
    const fixtures = [
      { as_of: "2025-04-15" }, { generated_at: "2026-09-15" }, {},
      { as_of: { elo: "2024-25 regular season", rolling_model: "2025-01-01 to 2025-04-01" } },
    ];
    expect(fixtures.map((artifact) => formatNovelSnapshot(artifact, "2026-09-16T08:00:00Z"))).toEqual([
      "Source as of 2025-04-15",
      "Snapshot generated 2026-09-15",
      "Index generated 2026-09-16",
      "Index generated 2026-09-16",
    ]);
    expect(estimatorWindows(fixtures[3])).toEqual([
      ["Elo", "Observation window 2024-25 regular season"],
      ["Rolling Model", "Observation window 2025-01-01 to 2025-04-01"],
    ]);
  });

  it("marks malformed and missing mock date provenance unavailable", () => {
    expect([
      formatNovelSnapshot({ as_of: "not-a-date" }, "2026-09-16"),
      formatNovelSnapshot({}, "not-a-date"),
    ]).toEqual(["Date not published.", "Date not published."]);
  });
});
