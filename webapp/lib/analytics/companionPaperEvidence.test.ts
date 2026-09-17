// Guards the three companion papers against the artifacts they cite: the effective-support
// paper, the closing-reference-movement paper and the cross-sport transfer paper. Each
// assertion reads the number out of the showcase artifact and then requires the paper's
// sentence to match it, so a paper cannot drift away from its own evidence.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { scanRenderedText } from "../../scripts/check-analytics-copy.mjs";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, validatePaper, type Paper, type PaperBlock } from "./papers";

function readJson(folder: string, name: string): any {
  return JSON.parse(readFileSync(join(process.cwd(), "public", "data", folder, `${name}.json`), "utf8"));
}
const paper = (slug: string) => readJson("papers", slug) as Paper;
const artifact = (name: string) => readJson("showcase", name);
const words = (value: Paper) => paperStrings(value).join(" ");

const DEPENDENCE = paper("repeated-observations-and-effective-support");
const MOVEMENT = paper("closing-reference-movement-measured");
const TRANSFER = paper("what-carries-across-sports");
const COMPANIONS = [DEPENDENCE, MOVEMENT, TRANSFER];

const dependenceText = words(DEPENDENCE);
const movementText = words(MOVEMENT);
const transferText = words(TRANSFER);

const statusCallouts = (value: Paper) =>
  value.sections
    .flatMap(section => section.blocks)
    .filter((block): block is Extract<PaperBlock, { type: "callout" }> => block.type === "callout" && block.label === "Status");

describe("repeated-observations-and-effective-support", () => {
  const ledger = artifact("ess_ledger");
  const autocorrelation = artifact("residual_autocorrelation");

  it("reads infl_anchor as an interval-width factor, not a row-count inflation", () => {
    const mlb = ledger.corpora.find((row: any) => row.sport === "mlb");
    const soccer = ledger.corpora.find((row: any) => row.sport === "soccer_intl");
    expect(ledger.formula).toContain("CI inflation = sqrt(n_rows / ESS)");
    expect(mlb.infl_anchor).toBe(18.7);
    expect(mlb.infl_anchor).toBeCloseTo(Math.sqrt(mlb.n_rows / mlb.ess_anchor), 1);
    expect(soccer.infl_anchor).toBe(13.3);

    expect(dependenceText).toContain("an estimated 18.7-fold interval-width increase under the game-count heuristic");
    expect(dependenceText).toContain("an estimated 13.3-fold interval-width increase");
    expect(dependenceText).toContain("an estimated 10.2-fold interval-width increase");
    expect(dependenceText).not.toMatch(/inflation of the raw row count/i);
    expect(dependenceText).not.toMatch(/\d+(\.\d+)?x inflation/i);

    // ess_ledger was not rebuilt on the segment-clean corpus, so its counts are still the joined
    // ones and the paper has to disclose that rather than quietly mixing revisions.
    expect(ledger.generated_at).toBe("2026-07-25T11:12:42.584390+00:00");
    expect(mlb.n_rows).toBe(78986);
    expect(mlb.n_games).toBe(227);
    expect(dependenceText).toContain("ess_ledger.json was not regenerated");
  });

  it("separates the 178 MLB series from the usable per-side counts", () => {
    const mlb = autocorrelation.sports.mlb;
    expect(mlb.n_files).toBe(178);
    expect(mlb.n_series).toBe(178);
    expect(mlb.n_records).toBe(27351);
    expect(mlb.model.n_games).toBe(173);
    expect(mlb.market.n_games).toBe(173);
    expect(mlb.model.skipped.low_n + mlb.model.skipped.flat).toBe(mlb.n_series - mlb.model.n_games);
    expect(mlb.market.skipped.low_n + mlb.market.skipped.flat).toBe(mlb.n_series - mlb.market.n_games);

    expect(dependenceText).toContain(`${mlb.model.n_games} series survive the floors on the model side`);
    expect(dependenceText).toContain(`${mlb.market.n_games} on the market side`);
    expect(dependenceText).toContain(`over the ${mlb.model.n_games} series usable on that side`);
    expect(dependenceText).not.toMatch(/227 usable series/);
    expect(dependenceText).not.toMatch(/178 usable series/);
    // the two artifacts now describe different corpora, so the paper must carry both counts
    expect(dependenceText).toContain(`${mlb.n_series} segment-clean MLB series`);
    expect(dependenceText).toContain("27,351");
  });

  it("merges the revision-2 corpus into the paper's single status callout", () => {
    const callouts = statusCallouts(DEPENDENCE);
    expect(callouts).toHaveLength(1);
    const text = callouts[0].text;
    expect(text).toContain("126 of the 227");
    expect(text).toContain("27,076 of 78,986");
    expect(text).toContain("27,351");
    expect(text).toContain("4,265");
    expect(text).toContain("2026-09-16");
    expect(text).toMatch(/withdrawn/);
    expect(text).toMatch(/population change/i);
    expect(text).not.toMatch(/improvement in the forecaster/i);
  });

  it("drops the universal ESS ceiling and the subtraction-creates-autocorrelation claim", () => {
    expect(dependenceText).not.toMatch(/never higher than the game count/i);
    expect(dependenceText).not.toMatch(/only push the true ESS lower/i);
    expect(dependenceText).toContain("neither figure is published as a bound");
    expect(dependenceText).toContain("does not by itself create or change that serial dependence");
  });
});

describe("closing-reference-movement-measured", () => {
  const premium = artifact("novel_market_foresight_premium");

  it("matches the ten MLB skill signs the artifact records", () => {
    const checkpoints = premium.results.mlb.checkpoints as Array<{ market_skill: number; model_skill: number }>;
    expect(checkpoints).toHaveLength(10);
    expect(checkpoints.filter(row => row.market_skill > 0)).toHaveLength(10);
    expect(checkpoints.filter(row => row.model_skill < 0)).toHaveLength(10);

    expect(movementText).toContain("Reference skill is positive at all ten MLB checkpoints; model skill is negative at all ten");
    expect(movementText).toContain("Market skill is positive in all ten rows and model skill negative in all ten");
    expect(movementText).not.toMatch(/Market skill and model skill both trail a naive baseline/i);
  });

  it("keeps each instrument's observation window separate", () => {
    const halfLife = artifact("novel_line_half_life");
    const absorption = artifact("micro_absorption");
    expect(halfLife.observation_window.per_sport.mlb).toEqual({ start: "2026-06-18", end: "2026-07-17", days: 30, files: 30 });
    expect(halfLife.observation_window.per_sport.tennis.days).toBe(15);
    expect(absorption.observation_window.per_sport).toEqual(halfLife.observation_window.per_sport);
    // The other two artifacts publish no window at all, so nothing may be pooled onto one calendar.
    expect(premium.observation_window).toBeUndefined();
    expect(artifact("market_overreaction").observation_window).toBeUndefined();

    expect(movementText).toContain("The four instruments do not share an observation window");
    expect(movementText).not.toMatch(/drawn from a single scraped-line-history window/i);
  });

  it("promises no finer checkpoint view than the four published buckets", () => {
    expect(movementText).not.toMatch(/finer per-checkpoint grain/i);
    expect(movementText).toContain("no finer checkpoint view of that movement is published");
  });
});

describe("what-carries-across-sports", () => {
  const scoreboard = artifact("cross_sport_scoreboard");
  const mlbIngame = scoreboard.rows.filter((row: any) => row.sport === "mlb_ingame");

  it("counts 7 underpowered MLB rows, not 9", () => {
    expect(mlbIngame).toHaveLength(10);
    const underpowered = mlbIngame.filter((row: any) => row.verdict === "UNDERPOWERED").length;
    const sharper = mlbIngame.filter((row: any) => row.verdict === "MODEL_SHARPER_PROVISIONAL").length;
    expect(underpowered).toBe(7);
    expect(sharper).toBe(3);

    const totals = artifact("kernel_transfer").rows.find((row: any) => row.market.startsWith("totals_margin"));
    expect(totals.verdict).toContain("MODEL_SHARPER_PROVISIONAL: 3, UNDERPOWERED: 7");

    expect(transferText).toContain(`split ${underpowered} UNDERPOWERED to ${sharper} MODEL_SHARPER_PROVISIONAL`);
    expect(transferText).not.toMatch(/9 of the 10 mlb_ingame/);
  });

  it("explains that a support rule can coexist with an interval excluding zero", () => {
    const withheld = scoreboard.rows.filter(
      (row: any) => row.verdict === "UNDERPOWERED" && (row.paired_delta_95ci[0] > 0 || row.paired_delta_95ci[1] < 0),
    );
    expect(withheld.length).toBeGreaterThan(0);
    expect(scoreboard.method).toContain("copied verbatim from its source artifact");

    expect(transferText).toContain("A verdict in this file is not a reading of the interval printed beside it");
    expect(transferText).toContain("the support rule that produced each label lives in that upstream benchmark");
    expect(transferText).not.toMatch(/The file does not document the rule/i);
    expect(transferText).not.toMatch(/well below the n>=30 floor brier_skill_scores\.json applies to itself/);
  });

  it("offers no sample-size explanation for the two-sport sign match", () => {
    expect(artifact("kernel_transfer").reliability_transfer_summary).toContain("n=2 sports is not enough");
    expect(transferText).toContain("This paper offers no explanation for either the sign match or the magnitude difference");
    expect(transferText).not.toMatch(/support n as the deciding factor/i);
    expect(transferText).not.toMatch(/support corpus size as part of why/i);
  });
});

describe("the three companion papers as a set", () => {
  it("quarantines the MLB corpus in a status callout on every one of them", () => {
    for (const value of COMPANIONS) {
      const callouts = statusCallouts(value);
      expect(callouts).toHaveLength(1);
      const text = callouts[0].text;
      expect(text).toMatch(/126 of (the )?227/);
      expect(text).toContain("27,076 of 78,986");
      expect(text).toContain("2026-09-16");
      expect(text).toMatch(/withdrawn pending/);
    }
  });

  it("stays valid, ASCII and free of prohibited vocabulary", () => {
    const artifacts = publishedArtifacts();
    for (const value of COMPANIONS) {
      expect(validatePaper(value, artifacts)).toBeNull();
      expect(scanRenderedText(words(value))).toEqual([]);
    }
  });
});
