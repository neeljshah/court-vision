import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { analysisDestinations } from "./analysisDestinations";
import { resolveQuestion } from "./askSearch";
import { loadScoutCorpus } from "./scoutCorpus.server";

const corpus = loadScoutCorpus();

describe("Scout reading-room answers", () => {
  it("gives every inspector its exact answer and registered destination", () => {
    for (const destination of analysisDestinations) {
      const result = resolveQuestion(destination.title, corpus);
      expect(result, destination.title).toMatchObject({ kind: "direct", entry: { bucket: "public-inspector", a: { explore_path: destination.route } } });
    }
  });

  it("gives every published explainer a cited answer and destination", () => {
    const explainers = corpus.filter(entry => entry.bucket === "public-explainer");
    expect(explainers.length).toBeGreaterThan(0);
    expect(explainers.every(entry => /^\/analytics\/explainers\/[a-z0-9-]+\/$/.test(entry.a.explore_path || ""))).toBe(true);
  });

  it("derives published support from the cited artifact, not an authored constant", () => {
    const answerFor = (id: string) => corpus.find(entry => entry.bucket === "public-inspector" && entry.a.explore_path === `/analytics/${id}`)?.a.answer || "";
    const artifact = (name: string) => JSON.parse(readFileSync(join(process.cwd(), "public", "data", "showcase", `${name}.json`), "utf8"));
    const rows = (value: number) => value.toLocaleString("en-US");

    const stability = artifact("calibration_stability");
    expect(answerFor("calibration")).toContain(`MLB: ${rows(stability.sports.mlb.n_rows)} forecast observations; International soccer: ${rows(stability.sports.soccer_intl.n_rows)} forecast observations`);
    expect(answerFor("calibration")).toContain(`Date status: ${stability.as_of}`);

    const anatomy = artifact("residual_anatomy");
    expect(answerFor("residual-anatomy")).toContain(`MLB: ${rows(anatomy.sports.mlb.n_records)} forecast observations`);

    const blowout = artifact("blowout_dynamics");
    expect(answerFor("blowout-timing")).toContain(`MLB: ${rows(blowout.sports.mlb.n_games_usable)} games`);

    // a rows-shaped artifact keeps one entry per population instead of collapsing to one bucket
    const transfer = artifact("kernel_transfer");
    const comparability = answerFor("cross-sport-comparability");
    expect(comparability).toContain(`MLB moneyline ingame: ${rows(transfer.rows[0].n)} rows`);
    expect(comparability).toContain(`MLB totals margin: ${rows(transfer.rows[1].n)} rows`);
    expect(comparability).toContain(`International soccer moneyline ingame: ${rows(transfer.rows[2].n)} rows`);

    // the withdrawn revision 1 counts cannot survive in any inspector answer
    for (const destination of analysisDestinations) {
      expect(answerFor(destination.id), destination.id).not.toContain("78,986");
      expect(answerFor(destination.id), destination.id).not.toContain("9,003");
    }
  });

  it("uses each paper abstract's first sentence without a mechanical prefix", () => {
    const papers = corpus.filter(entry => entry.bucket === "public-paper");
    expect(papers.length).toBeGreaterThan(0);
    expect(papers.every(entry => !entry.a.answer.includes("It measures"))).toBe(true);
  });
});
