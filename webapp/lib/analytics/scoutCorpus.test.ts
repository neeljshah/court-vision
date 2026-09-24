import { describe, expect, it } from "vitest";
import { resolveEntityIntent } from "./askEntityIntent";
import { resolveQuestion } from "./askSearch";
import { getResearchAnalyses } from "./researchData";
import { loadScoutCorpus, loadScoutSourcesForTest } from "./scoutCorpus.server";
import { buildScoutCorpus, scoutCorpusExpectedCount, type ScoutSources } from "./scoutCorpus";
import calibrationMarket from "../../public/data/ask/calibration-market.json";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";

const corpus = loadScoutCorpus();
const sources = loadScoutSourcesForTest();
const entityCount = Object.values(sources.manifests).reduce((total, manifest) => total + manifest.entries.length, 0);

describe("loadScoutCorpus", () => {
  it("keeps curated answers and expands all public entity and module records", () => {
    expect(corpus.length).toBe(scoutCorpusExpectedCount(sources));
    expect(corpus.some((entry) => entry.q === "How does forecast calibration compare with the closing reference?")).toBe(true);
    expect(corpus.filter((entry) => entry.bucket === "public-entity-profile")).toHaveLength(entityCount);
    expect(corpus.filter((entry) => entry.bucket === "public-analytics-module")).toHaveLength(sources.siteManifest.modules.length);
    expect(corpus.filter((entry) => entry.bucket === "public-derived-analysis")).toHaveLength(getResearchAnalyses().length);
  });

  it("marks both curated full-season Brier answers as withdrawn corrections", () => {
    const answers = corpus.filter((entry) => /full-season.*backtest/i.test(entry.q));
    expect(answers).toHaveLength(2);
    for (const entry of answers) {
      expect(entry.a.answer).toContain("Correction published 2026-09-14");
      expect(entry.a.answer).toContain("withdrawn");
      expect(entry.a.as_of).toBe("2026-09-14");
      expect(entry.a.source_artifact).toBe("docs/JOB_EVIDENCE_PACKET.md");
    }
  });

  it("retrieves the corrected pregame comparisons with their measured uncertainty", () => {
    const evidence = "docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md";
    const cases = [
      { question: "How does forecast calibration compare with the closing reference?", bucketQuestion: "Does the model actually beat the market comparison market?", scope: "three recomputed pregame comparisons", interval: "[-0.0042, +0.0168]" },
      { question: "How close is the model to the NBA closing line?", scope: "372 held-out NBA moneyline games", interval: "[-0.0042, +0.0168]" },
      { question: "How does the model do against the MLB moneyline close?", scope: "13,992 held-out games", interval: "[+0.0028, +0.0051]" },
      { question: "Does the model match the market on soccer?", scope: "7,558 held-out matches", interval: "[+0.0059, +0.0092]" },
    ];
    for (const { question, bucketQuestion, scope, interval } of cases) {
      const result = resolveQuestion(question, corpus);
      expect(result, question).toMatchObject({ kind: "direct", entry: { q: question, a: { status: "ok", source_artifact: evidence, as_of: "2026-09-24" } } });
      if (result?.kind !== "direct" || !result.entry) throw new Error(`No direct answer for ${question}`);
      expect(result.entry.a.answer).toContain(scope);
      expect(result.entry.a.answer).toContain(interval);
      expect(result.entry.a.answer).toContain("proportionally devigged");
      const sourceEntry = calibrationMarket.entries.find((entry) => entry.q === (bucketQuestion || question));
      expect(sourceEntry?.a).toEqual(result.entry.a);
    }
    const nba = resolveQuestion("How close is the model to the NBA closing line?", corpus);
    expect(nba?.entry?.a.answer).toContain("capture time is unverified");
    expect(nba?.entry?.a.answer).toContain("too small to establish parity");
  });

  it("retrieves a derived formula with its source and denominator limits", () => {
    const result = resolveQuestion("Which historical matchups run high or close?", corpus);
    expect(result).toMatchObject({ kind: "direct", entry: { bucket: "public-derived-analysis", a: { status: "ok", source_artifact: "webapp/public/data/showcase/nba_matchup_grid.json" } } });
    if (result?.kind === "direct" && result.entry) {
      expect(result.entry.a.answer).toContain("meeting-weighted");
      expect(result.entry.a.answer).toContain("not forecasts");
      expect(result.entry.a.explore_path).toBe("/analytics/research/nba-matchup-profile-contrast/");
      expect(result.followUps).toContain("What does the Nba Matchup Grid analytics module cover?");
      expect(result.followUps).not.toContain("Explain the analysis: Calibration support concentration");
      expect(result.followUps.some((question) => /tennis/i.test(question))).toBe(false);
    }
  });

  it("builds named entity profiles with metrics, source, and as-of scope", () => {
    const ohtani = corpus.find((entry) => entry.q === "What public metrics are available for Shohei Ohtani?");
    expect(ohtani).toMatchObject({
      a: {
        source_artifact: "webapp/public/data/showcase/atlas_mlb_batters_manifest.json",
        as_of: "2025-09-28",
      },
    });
    expect(ohtani?.a.answer).toContain("average exit velocity:");
    expect(ohtani?.a.answer).toContain("mph");
    expect(ohtani?.a.answer).toContain("not a current projection or live feed");
    expect(ohtani?.a.explore_path).toBe("/analytics/players/mlb_batters/shohei_ohtani");
    expect(ohtani?.entity).toEqual({ name: "Shohei Ohtani", pack: "mlb_batters", slug: "shohei_ohtani" });
  });

  it("adds one Atlas identity record to every generated entity profile", () => {
    const identities = corpus.flatMap((entry) => entry.entity ? [entry.entity] : []);
    expect(identities).toHaveLength(entityCount);
    expect(new Set(identities.map((entity) => `${entity.pack}:${entity.slug}`)).size).toBe(entityCount);
  });

  it("gives every generated profile and module a validated reading destination", () => {
    const profiles = corpus.filter((entry) => entry.bucket === "public-entity-profile");
    const modules = corpus.filter((entry) => entry.bucket === "public-analytics-module");
    expect(profiles.every((entry) => /^\/analytics\/players\/[a-z_]+\/[a-z0-9_]+$/.test(entry.a.explore_path || ""))).toBe(true);
    expect(modules.every((entry) => /^\/analytics\/m\/[a-z0-9_]+$/.test(entry.a.explore_path || ""))).toBe(true);
  });

  it("grounds player, unknown-person, and latest-data questions", () => {
    expect(resolveQuestion("How is Jokic's playmaking?", corpus)).toMatchObject({ kind: "direct", entry: { a: { status: "ok" } } });
    expect(resolveQuestion("What public profile is available for Wembanyama?", corpus)).toMatchObject({ kind: "direct", entry: { a: { status: "ok" } } });
    expect(resolveQuestion("Tell me about Ohtani", corpus)).toMatchObject({ kind: "direct", entry: { q: "What public metrics are available for Shohei Ohtani?" } });
    expect(resolveQuestion("What is Unknown Person's NBA profile?", corpus)?.kind).not.toBe("direct");
    expect(resolveQuestion("What are Ohtani's latest stats?", corpus)).toMatchObject({ kind: "direct", entry: { a: { status: "no_data" } } });
  });

  it("resolves published Atlas names without promoting aliases into comparisons", () => {
    const atlasEntities = corpus.flatMap((entry) => entry.entity ? [entry.entity] : []);
    const stephen = { name: "Stephen Curry", pack: "nba_players", slug: "stephen_curry" };
    const seth = { name: "Seth Curry", pack: "nba_players", slug: "seth_curry" };
    const jokic = { name: "Nikola Jokic", pack: "nba_players", slug: "nikola_jokic" };
    const giannis = { name: "Giannis Antetokounmpo", pack: "nba_players", slug: "giannis_antetokounmpo" };

    expect(resolveEntityIntent("Stephen Curry", atlasEntities)).toMatchObject({ entities: [stephen], candidates: [], isComparison: false });
    expect(resolveEntityIntent("Compare Stephen Curry and Seth Curry", atlasEntities)).toMatchObject({ entities: [stephen, seth], candidates: [], isComparison: true });
    expect(resolveEntityIntent("Compare Nikola Jokic and Giannis Antetokounmpo", atlasEntities)).toMatchObject({ entities: [jokic, giannis], candidates: [], isComparison: true });
    expect(resolveEntityIntent("Nikola", atlasEntities)).toMatchObject({ entities: [], isComparison: false });
    expect(resolveEntityIntent("Nikola", atlasEntities).candidates.map((entity) => entity.slug)).toEqual(expect.arrayContaining([
      "nikola_jokic", "nikola_jovic", "nikola_vucevic",
    ]));
    expect(resolveEntityIntent("Curry", atlasEntities).candidates).toEqual([stephen, seth]);
    expect(resolveEntityIntent("pitch velocity", atlasEntities)).toMatchObject({ entities: [], candidates: [], isComparison: false });

    expect(resolveQuestion("Nikola", corpus)).toMatchObject({ entry: null, kind: "none" });
    expect(resolveQuestion("Curry", corpus)).toMatchObject({ entry: null, kind: "none" });
  });

  it("carries the published pitch-type coverage limits for both SC and FF", () => {
    const floors = sources.manifests.atlas_mlb_pitch_manifest.entries.find(entry => entry.entity === "pitch_type:SC")?.floors;
    expect(typeof floors).toBe("string");
    for (const code of ["SC", "FF"]) {
      const profile = corpus.find(entry => entry.q === `What public metrics are available for pitch type ${code}?`);
      expect(profile?.a.answer).toContain(`Published pitch-type coverage and limits: ${floors}`);
    }
    const sc = corpus.find(entry => entry.q === "What public metrics are available for pitch type SC?");
    const ff = corpus.find(entry => entry.q === "What public metrics are available for pitch type FF?");
    expect(sc?.a.answer).toContain("median velocity: 85.6 mph; recorded pitches: 7 pitches");
    expect(ff?.a.answer).toContain("recorded pitches: 220235 pitches");
  });

  it("does not invent or spill pitch-type limits for absent, blank, malformed, or non-type floors", () => {
    const entry = (entity: string, floors?: unknown) => ({ entity, card_path: `cards/${entity}.png`, key_numbers: { velo_p50: 90, n_pitches: 10 }, as_of: "2025-09-28", floors: floors as string });
    const custom: ScoutSources = {
      curated: { entries: [] },
      manifests: {
        atlas_mlb_pitch_manifest: { entries: [entry("pitch_type:AA"), entry("pitch_type:BB", "   "), entry("pitch_type:CC", { note: "malformed" }), entry("team:NYY", "team note")] },
        atlas_mlb_batters_manifest: { entries: [entry("pitch_type:DD", "wrong pack note")] },
      },
      siteManifest: { modules: [] }, inspectorArtifacts: [], explainers: [], papers: [],
    };
    const profiles = buildScoutCorpus(custom).filter(record => record.bucket === "public-entity-profile");
    expect(profiles).toHaveLength(5);
    expect(profiles.every(profile => !profile.a.answer.includes("Published pitch-type coverage and limits:"))).toBe(true);
    expect(profiles.every(profile => !profile.a.answer.includes("1000"))).toBe(true);
  });

  it("retrieves soccer scoring form with its prior-match scope and exact analysis link", () => {
    const result = resolveQuestion("Explain the analysis: Soccer form: attack and defense", corpus);
    expect(result).toMatchObject({ kind: "direct", entry: { a: {
      source_artifact: "webapp/public/data/showcase/atlas_soccer_manifest.json",
      explore_path: "/analytics/research/soccer-trailing-attack-defense/",
    } } });
    expect(result).not.toBeNull();
    if (!result) throw new Error("null result");
    if (result.kind === "direct") {
      expect(result.entry?.a.answer).toContain("gf_l10");
      expect(result.entry?.a.answer).toContain("ga_l10");
      expect(result.entry?.a.answer).toMatch(/prior matches/i);
    }
  });

  it("resolves published tennis profiles with or without their ATP qualifier", () => {
    const atlasEntities = corpus.flatMap((entry) => entry.entity ? [entry.entity] : []);
    const sinner = atlasEntities.find((entity) => entity.slug === "jannik_sinner_atp")!;
    const alcaraz = atlasEntities.find((entity) => entity.slug === "carlos_alcaraz_atp")!;
    const djokovic = atlasEntities.find((entity) => entity.slug === "novak_djokovic_atp")!;
    const zverevs = atlasEntities.filter((entity) => entity.pack === "tennis" && /zverev/i.test(entity.name));

    expect(resolveEntityIntent("Sinner vs Alcaraz", atlasEntities)).toMatchObject({
      entities: [sinner, alcaraz], candidates: [], isComparison: true,
    });
    expect(resolveQuestion("Sinner vs Alcaraz", corpus)?.compareOffer).toEqual({
      label: "Compare Jannik Sinner (ATP) and Carlos Alcaraz (ATP)",
      href: "/analytics/compare?pack=tennis&a=jannik_sinner_atp&b=carlos_alcaraz_atp",
    });
    expect(resolveEntityIntent("Novak Djokovic", atlasEntities).entities).toEqual([djokovic]);
    expect(resolveEntityIntent("Novak Djokovic (ATP)", atlasEntities).entities).toEqual([djokovic]);
    expect(zverevs).toHaveLength(2);
    expect(resolveEntityIntent("Zverev", atlasEntities)).toMatchObject({
      entities: [], candidates: zverevs, isComparison: false,
    });
    expect(resolveEntityIntent("Alexander Zverev", atlasEntities).entities).toEqual([zverevs[0]]);
  });

  it("does not answer a named entity directly when the query adds conflicting scope", () => {
    const queries = [
      "Tell me about Ohtani basketball rebounds",
      "What public metrics are available for Jokic soccer",
      "How is Jokic baseball pitching?",
      "What public metrics are available for pitch type CH NBA",
      "What is Ohtani model calibration?",
    ];
    for (const query of queries) expect(resolveQuestion(query, corpus)?.kind).not.toBe("direct");
  });

  it("keeps follow-ups tied to entity-specific context", () => {
    const result = resolveQuestion("Tell me about Stephen Curry", corpus);
    expect(result?.followUps).not.toContain("What public metrics are available for AJ Lawson?");
  });

  it("does not treat the documented Live-Clock metric as a live-data request", () => {
    expect(resolveQuestion("What is Live-Clock Fraction?", corpus)).toMatchObject({
      kind: "direct",
      entry: { q: "What is the Live-Clock Fraction?", a: { status: "ok" } },
    });
    expect(resolveQuestion("What does the Novel Live Clock Fraction analytics module cover?", corpus)).toMatchObject({
      kind: "direct",
      entry: { q: "What does the Novel Live Clock Fraction analytics module cover?", a: { status: "ok" } },
    });
    expect(resolveQuestion("What is the latest Live-Clock Fraction?", corpus)).toMatchObject({
      kind: "direct",
      entry: { a: { status: "no_data" } },
    });
  });
});

it("keeps every Scout corpus string outside the prohibited vocabulary", () => {
  const values = (value: unknown): string[] => typeof value === "string" ? [value] : Array.isArray(value) ? value.flatMap(values) : value && typeof value === "object" ? Object.values(value).flatMap(values) : [];
  for (const value of values(corpus)) {
    PROHIBITED_TOKEN_RE.lastIndex = 0;
    expect(PROHIBITED_TOKEN_RE.test(value), value).toBe(false);
  }
});


it("routes every derived analysis to its exact source and interactive page", () => {
  for (const entry of corpus.filter(record => record.bucket === "public-derived-analysis")) {
    const result = resolveQuestion(entry.q, corpus);
    expect(result, entry.q).toMatchObject({ kind: "direct", entry: { q: entry.q, a: { source_artifact: entry.a.source_artifact, explore_path: entry.a.explore_path } } });
    expect(entry.a.explore_path).toMatch(/^\/analytics\/research\/[a-z0-9-]+\/$/);
  }
});
