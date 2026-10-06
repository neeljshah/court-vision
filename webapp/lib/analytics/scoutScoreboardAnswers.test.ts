import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import scoreboard from "../../public/data/showcase/cross_sport_scoreboard.json";
import forecaster from "../../public/data/showcase/forecaster/cross_sport_scoreboard.json";
import siteManifest from "../../public/data/showcase/site_manifest.json";
import insight from "../../public/data/insights/cross_sport_scoreboard.json";
import systemHonesty from "../../public/data/ask/system-honesty.json";
import served from "../../public/data/ask/corpus.json";
import { resolveQuestion } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus.server";

const question = "Across sports, does the model beat the market at any game state?";
const clarification = "Some underpowered rows have confidence intervals that exclude zero.";
const repo = join(process.cwd(), "..");

describe("cross-sport scoreboard Scout answer", () => {
  it("preserves source counterexamples to equating UNDERPOWERED with a CI spanning zero", () => {
    const counterexamples = scoreboard.rows.filter(row => row.verdict === "UNDERPOWERED"
      && (row.paired_delta_95ci[0] > 0 || row.paired_delta_95ci[1] < 0));
    expect(counterexamples).toHaveLength(6);
    expect(counterexamples.filter(row => row.sport === "mlb_ingame")).toHaveLength(4);
    expect(counterexamples.filter(row => row.sport === "soccer_intl")).toHaveLength(2);
    expect(scoreboard.edge_claimed).toBe(false);
    expect(scoreboard.n_rows).toBe(17);
  });

  it("serves the corrected direct answer with its bucket, date, and source synchronized", () => {
    const bucket = systemHonesty.entries.find(entry => entry.q === question);
    const published = served.entries.find(entry => entry.q === question);
    const result = resolveQuestion(question, loadScoutCorpus());
    expect(result).toMatchObject({ kind: "direct", entry: { q: question } });
    expect(result?.entry?.a).toEqual(bucket?.a);
    expect(published?.a).toEqual(bucket?.a);
    expect(published?.alt_phrasings).toEqual(bucket?.alt_phrasings);
    expect(published?.tags).toEqual(bucket?.tags);
    expect(result?.entry?.a).toMatchObject({
      status: "ok", as_of: "2026-07-22",
      source_artifact: "webapp/public/data/showcase/cross_sport_scoreboard.json",
    });
    const answer = result?.entry?.a.answer || "";
    expect(answer).not.toContain("underpowered (confidence interval spans zero)");
    expect(answer).toContain(clarification);
    expect(answer).toContain("paired delta of -0.0084");
    expect(answer).toContain("provisional pending more data");
  });

  it("keeps the public note and producer copy consistent without the false equivalence", () => {
    const producer = readFileSync(join(repo, "scripts/platformkit/analytics_showcase/cross_sport_scoreboard.py"), "utf8");
    const noteSection = producer.slice(producer.indexOf('"honest_note":'), producer.indexOf("OUT_DIR.mkdir"));
    const note = [...noteSection.matchAll(/"([^"\n]*)"/g)].slice(1).map(match => match[1]).join("");
    const output = JSON.parse(readFileSync(join(repo, "scripts/platformkit/analytics_showcase/out/cross_sport_scoreboard.json"), "utf8"));
    expect(note).toBe(scoreboard.honest_note);
    expect(output.honest_note).toBe(scoreboard.honest_note);
    const outputManifest = JSON.parse(readFileSync(join(repo, "scripts/platformkit/analytics_showcase/out/site_manifest.json"), "utf8"));
    expect(outputManifest.modules.find((module: { id: string; one_line: string }) => module.id === "cross_sport_scoreboard")?.one_line).toBe(scoreboard.honest_note);
    expect(forecaster.honest_note).toBe(scoreboard.honest_note);
    expect(siteManifest.modules.find(module => module.id === "cross_sport_scoreboard")?.one_line).toBe(scoreboard.honest_note);
    expect(note).not.toContain("UNDERPOWERED (CI spans zero)");
    expect(note).toContain(clarification);
    expect(insight.what_it_means).not.toContain("UNDERPOWERED (their confidence interval spans zero)");
    expect(insight.what_it_means).toContain(clarification);
  });
});
