// Locks the tennis paper to tennis_showcase.json and tennis_grain_and_myths.json: the
// brier_delta sign convention (base minus prior), the fold totals that are a subset of the
// joined states, the tour attribution the two blocks disagree on, and the exact verdict
// each altitude and travel claim carries.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, validatePaper, type Paper, type PaperBlock } from "./papers";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";

type Direction = {
  n_train_states: number; n_test_states: number;
  brier_base: number; brier_prior: number; brier_delta: number; dm_p: number; prior_beats_base: boolean;
};
type Fold = { fold: number; n_test: number; brier_h0: number; brier_h1: number; dm_p: number };
type Tour = {
  n_states_joined: number; pooled_brier_h0_blind: number; pooled_brier_h1_surface: number;
  pooled_delta_h1_minus_h0: number; sign_holds_ge_2of3: boolean; n_folds: Fold[];
};
type Showcase = {
  pregame_prior_cross_corpus: { vs_close: string; coverage: Record<string, number>; directions: Record<string, Direction> };
  ingame_surface_context: { verdict: string; vs_close: string; tours: Record<string, Tour> };
};
type Claim = { hypothesis: string; verdict: string; n: number; effect: number; corpus: string };
type Myths = { generated_at: string; stories: { key: string; claims: Claim[] }[] };
type TableBlock = Extract<PaperBlock, { type: "table" }>;
type TextBlock = Extract<PaperBlock, { type: "p" | "callout" | "math" }>;

const read = <T,>(...parts: string[]): T =>
  JSON.parse(readFileSync(join(process.cwd(), "public", "data", ...parts), "utf8")) as T;

const paper = read<Paper>("papers", "tennis-forecasts-held-to-the-reference.json");
const showcase = read<Showcase>("showcase", "tennis_showcase.json");
const myths = read<Myths>("showcase", "tennis_grain_and_myths.json");

const blocks = paper.sections.flatMap(section => section.blocks);
const prose = paperStrings(paper).join("\n");

const table = (caption: string): TableBlock => {
  const found = blocks.find(block => block.type === "table" && block.caption.includes(caption));
  if (!found) throw new Error(`no table captioned ${caption}`);
  return found as TableBlock;
};
const text = (needle: string): string => {
  const found = blocks.find(block =>
    (block.type === "p" || block.type === "callout" || block.type === "math") && block.text.includes(needle));
  if (!found) throw new Error(`no block containing ${needle}`);
  return (found as TextBlock).text;
};
const claim = (hypothesis: string): Claim => {
  const found = myths.stories.flatMap(story => story.claims).find(entry => entry.hypothesis === hypothesis);
  if (!found) throw new Error(`no claim ${hypothesis}`);
  return found;
};

describe("tennis paper evidence", () => {
  it("defines brier_delta as base minus prior, the direction the artifact publishes", () => {
    for (const direction of Object.values(showcase.pregame_prior_cross_corpus.directions)) {
      expect(direction.brier_delta).toBeCloseTo(direction.brier_base - direction.brier_prior, 3);
      expect(direction.brier_delta).not.toBeCloseTo(direction.brier_prior - direction.brier_base, 3);
      expect(direction.brier_delta).toBeGreaterThan(0);
      expect(direction.prior_beats_base).toBe(true);
    }
    expect(text("Brier(model) =")).toContain("brier_delta (pregame test) = brier_base - brier_prior");
    expect(table("Pregame cross-corpus held-out Brier").columns).toContain("Brier delta (base minus prior)");
    expect(paper.abstract).toContain("brier_delta 0.01005, published as base minus prior");
    expect(text("brier_prior comes in below brier_base")).toContain("brier_delta 0.01005, base minus prior");
    // the reversed definition may not survive anywhere in the paper
    expect(prose).not.toContain("brier_prior - brier_base");
    expect(prose).not.toContain("prior minus base");
  });

  it("copies both pregame directions into Table 1 exactly", () => {
    const rows = table("Pregame cross-corpus held-out Brier").rows;
    expect(rows).toHaveLength(2);
    for (const [name, test, train, base, prior, delta, dm] of rows) {
      const direction = showcase.pregame_prior_cross_corpus.directions[name];
      expect(direction, name).toBeTruthy();
      expect([test, train]).toEqual([String(direction.n_test_states), String(direction.n_train_states)]);
      expect(Number(base)).toBe(direction.brier_base);
      expect(Number(prior)).toBe(direction.brier_prior);
      expect(Number(delta)).toBe(direction.brier_delta);
      expect(Number(dm)).toBe(direction.dm_p);
    }
  });

  it("separates the joined states from the fold-test totals and flags the tour attribution", () => {
    const atp = showcase.ingame_surface_context.tours.atp;
    const wta = showcase.ingame_surface_context.tours.wta;
    const atpFolds = atp.n_folds.reduce((sum, fold) => sum + fold.n_test, 0);
    const wtaFolds = wta.n_folds.reduce((sum, fold) => sum + fold.n_test, 0);
    expect([atp.n_states_joined, wta.n_states_joined]).toEqual([40516, 14559]);
    expect([atpFolds, wtaFolds]).toEqual([26340, 7937]);
    expect(atpFolds).toBeLessThan(atp.n_states_joined);
    expect(wtaFolds).toBeLessThan(wta.n_states_joined);
    expect(table("Surface-specific (H1) versus surface-blind (H0)").note)
      .toContain("the three folds sum to 26340 of ATP's 40516 joined states and 7937 of WTA's 14559");

    // the same 40516 is the WTA test side in one block and the ATP joined set in the other
    expect(showcase.pregame_prior_cross_corpus.directions.atp_train_wta_test.n_test_states).toBe(atp.n_states_joined);
    expect(showcase.pregame_prior_cross_corpus.directions.wta_train_atp_test.n_test_states).toBe(wta.n_states_joined);
    const flag = text("They are not usable as tour labels");
    expect(flag).toContain("the pregame block puts 40516 states on the WTA test side while the in-game block puts the same 40516 on ATP");
    expect(flag).toContain("The artifact does not reconcile that");
  });

  it("states the per-tour uncertainty rather than claiming the challenger simply loses", () => {
    const atp = showcase.ingame_surface_context.tours.atp;
    const wta = showcase.ingame_surface_context.tours.wta;
    // no ATP fold separates the two models; two of three WTA folds do
    expect(atp.n_folds.filter(fold => fold.dm_p < 0.05)).toHaveLength(0);
    expect(wta.n_folds.filter(fold => fold.dm_p < 0.05)).toHaveLength(2);
    expect(atp.pooled_delta_h1_minus_h0).toBeCloseTo(atp.pooled_brier_h1_surface - atp.pooled_brier_h0_blind, 6);
    expect(wta.pooled_delta_h1_minus_h0).toBeCloseTo(wta.pooled_brier_h1_surface - wta.pooled_brier_h0_blind, 6);

    const measured = text("The two tours carry very different uncertainty");
    for (const fold of atp.n_folds) expect(measured).toContain(String(fold.dm_p));
    for (const fold of wta.n_folds) expect(measured).toContain(String(fold.dm_p));
    expect(measured).toContain("separate the two models in no fold");
    expect(measured).toContain("reach conventional significance in two of three folds");
    expect(measured).toContain(showcase.ingame_surface_context.verdict);
    expect(prose).not.toContain("this challenger loses");
    expect(prose).not.toMatch(/indistinguishable/i);
  });

  it("gives altitude its REPLICATED rows and leaves travel confirmed locally only", () => {
    const altitude = claim("altitude_effect_on_serve_ace_rate");
    const slices = myths.stories.flatMap(story => story.claims)
      .filter(entry => entry.hypothesis.startsWith("altitude_effect_on_serve_ace_rate__replication"));
    const travel = claim("long_travel_effect_on_win_prob_partial");
    expect(altitude.verdict).toBe("CONFIRMED_LOCAL");
    expect(slices.map(entry => entry.verdict)).toEqual(["REPLICATED", "REPLICATED"]);
    expect(travel.verdict).toBe("CONFIRMED_LOCAL");
    expect(myths.stories.flatMap(story => story.claims)
      .filter(entry => entry.hypothesis.startsWith("long_travel") && entry.verdict === "REPLICATED")).toHaveLength(0);

    const contrast = text("Not everything in this file is null");
    expect(contrast).toContain(`CONFIRMED_LOCAL, n=${altitude.n}, effect ${altitude.effect}`);
    expect(contrast).toContain("two further rows whose verdict field reads REPLICATED");
    expect(contrast).toContain(`CONFIRMED_LOCAL, n=${travel.n}, effect ${travel.effect}`);
    expect(contrast).toContain("carries no replication row");
    for (const slice of slices) expect(contrast).toContain(`n=${slice.n}, effect ${slice.effect}`);
    expect(paper.abstract).toContain("altitude is CONFIRMED_LOCAL with two further rows whose verdict reads REPLICATED");
    expect(paper.abstract).toContain("long travel is CONFIRMED_LOCAL with no replication row");
    expect(prose).not.toContain("Altitude and travel effects, by contrast, are confirmed and independently replicated");
  });

  it("copies every momentum and tiebreak verdict from its claim object", () => {
    const rows = table("Preregistered momentum and tiebreak tests").rows;
    for (const [hypothesis, verdict, n, effect, corpus] of rows) {
      const source = claim(hypothesis);
      expect([verdict, n, effect, corpus]).toEqual([source.verdict, String(source.n), String(source.effect), source.corpus]);
    }
    expect(rows.filter(row => row[1] === "NULL_LOCAL")).toHaveLength(5);
  });

  it("keeps vs_close UNPROVEN in both blocks", () => {
    for (const block of [showcase.pregame_prior_cross_corpus, showcase.ingame_surface_context]) {
      expect(block.vs_close).toContain("UNPROVEN");
    }
    expect(prose).toContain("vs_close is explicitly UNPROVEN in both");
  });

  it("passes the paper validator and its forbidden-vocabulary scan", () => {
    expect(validatePaper(paper, publishedArtifacts())).toBeNull();
    for (const value of paperStrings(paper)) expect(PROHIBITED_TOKEN_RE.test(value)).toBe(false);
  });
});
