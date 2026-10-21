// One test per page family: the title and description come from the page's data, the
// description stays under 160 characters, descriptive exhibits say so, and the canonical is
// the family's trailing-slash URL. Nothing here claims an edge, ROI or profit.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DESCRIPTION_MAX } from "@/lib/seo/meta";
import { claimMeta, entityMeta, explainerMeta, fillMeta, findingPageMeta, gameMeta, moduleMeta, paperMeta, receiptMeta, researchMeta, stubMeta } from "@/lib/seo/families";
import { BANNED_COPY, RETRACTED_TOKENS } from "@/lib/packetVerdicts";
import type { Metadata } from "next";

const ORIGIN = "https://neeljshah.github.io/court-vision";
beforeEach(() => vi.stubEnv("NEXT_PUBLIC_BASE_PATH", "/court-vision"));
afterEach(() => vi.unstubAllEnvs());

/** The rails every family shares. */
function rails(m: Metadata, route: string) {
  const d = String(m.description);
  expect(String(m.title).length).toBeGreaterThan(0);
  expect(String(m.title)).not.toBe("CourtVision");
  expect(d.length).toBeGreaterThan(0);
  expect(d.length).toBeLessThan(DESCRIPTION_MAX);
  expect(m.alternates?.canonical).toBe(`${ORIGIN}${route}`);
  expect(m.openGraph).toMatchObject({ url: `${ORIGIN}${route}` });
  expect(m.twitter).toMatchObject({ card: "summary_large_image" });
  for (const t of RETRACTED_TOKENS) expect(d).not.toContain(t);
  expect(d).not.toMatch(BANNED_COPY);
  return d;
}

describe("players", () => {
  it("names the entity, the pack, the sport and the as-of; says descriptive", () => {
    const m = entityMeta({ pack: "nba_players", slug: "lebron_james", name: "LeBron James", packLabel: "NBA players", sport: "NBA", asOf: "2026-07-19T03:41:37+00:00" });
    const d = rails(m, "/analytics/players/nba_players/lebron_james/");
    expect(m.title).toBe("LeBron James -- NBA players");
    expect(d).toContain("Descriptive reference card for LeBron James (NBA players, NBA)");
    expect(d).toMatch(/As of 2026-07-19\.$/);
  });
});

describe("m (modules)", () => {
  it("leads with the one_line, carries status and as-of, and survives a long summary", () => {
    const m = moduleMeta({ id: "blowout_dynamics", title: "Blowout Dynamics", summary: "x ".repeat(200), status: "partial", asOf: "2026-09-17", descriptive: true });
    const d = rails(m, "/analytics/m/blowout_dynamics/");
    expect(m.title).toBe("Blowout Dynamics");
    expect(d.startsWith("Descriptive analytics module: x x")).toBe(true);
    expect(d).toMatch(/\.\.\. As of 2026-09-17\.$/);
  });
  it("an empty one_line still yields a module-specific description", () => {
    const d = rails(moduleMeta({ id: "agent_fleet_history", title: "Agent Fleet History", summary: "", status: "ok", asOf: "2026-07-22" }), "/analytics/m/agent_fleet_history/");
    expect(d).toBe("Analytics module Agent Fleet History: measured values with their source artifact, status ok. As of 2026-07-22.");
    // ten manifest one_lines are just the flag "Descriptive only": that is a label, not a summary
    const f = rails(moduleMeta({ id: "nba_form_curves", title: "NBA Form Curves", summary: "Descriptive only", status: "ok" }), "/analytics/m/nba_form_curves/");
    expect(f).toBe("Descriptive analytics module NBA Form Curves: measured values with their source artifact, status ok.");
  });
});

describe("research", () => {
  it("uses the analysis description, novelty and as-of", () => {
    const d = rails(researchMeta({ id: "soccer-scoring", title: "Soccer scoring", description: "Compares published goals.", novelty: "Derived analysis", asOf: "2026-09-01" }), "/analytics/research/soccer-scoring/");
    expect(d).toBe("Compares published goals. Descriptive derived analysis. As of 2026-09-01.");
  });
});

describe("papers", () => {
  it("excerpts the abstract under the limit and closes with the sport and date", () => {
    const m = paperMeta({ slug: "nba-rest-asymmetry", title: "Rest asymmetry", abstract: "Sentence one. ".repeat(30), date: "2026-09-10", sport: "nba" });
    const d = rails(m, "/analytics/papers/nba-rest-asymmetry/");
    expect(m.title).toBe("Rest asymmetry");
    expect(d).toMatch(/\.\.\. NBA research paper, 2026-09-10\.$/);
    expect(m.openGraph).toMatchObject({ type: "article" });
  });
});

describe("evidence claims", () => {
  it("prefers the lede, names the bucket, and flags a pending claim", () => {
    const d = rails(claimMeta({ slug: "a-claim", title: "A claim -- and its subtitle", lede: "The lede.", claim: "The teaser.", bucket: "Calibration", status: "MEASURED" }), "/evidence/a-claim/");
    expect(d).toBe("A claim: The lede. (Calibration.)");
    const p = rails(claimMeta({ slug: "b", title: "B", claim: "Teaser only.", bucket: "", status: "VALIDATION_PENDING" }), "/evidence/b/");
    expect(p).toBe("Validation pending. B: Teaser only.");
  });
});

describe("paper fills", () => {
  it("decodes the KX game, names side, venue, time and status; canonical is the double-encoded href", () => {
    const param = encodeURIComponent("nba|KXNBAGAME-26OCT08ATLSAS|no|2026-10-09T00:51:29.008426Z|0.23");
    const m = fillMeta({ param, sport: "nba", gameId: "KXNBAGAME-26OCT08ATLSAS", side: "no", ts: "2026-10-09T00:51:29.008426Z", book: "kalshi", marketType: "kalshi_ingame_contract", status: "open", stakeUnits: 0.23 });
    // The sitemap's href: the once-encoded directory name encoded again, dots included (lib/paperLinks).
    const d = rails(m, "/paper/nba%257CKXNBAGAME-26OCT08ATLSAS%257Cno%257C2026-10-09T00%253A51%253A29%2E008426Z%257C0%2E23/");
    expect(m.title).toBe("Paper fill: ATL @ SAS, no, 2026-10-09 00:51:29Z");
    expect(d).toBe("NBA paper fill on ATL @ SAS: side no, kalshi_ingame_contract at kalshi, 2026-10-09 00:51:29Z, 0.23 units, status open. Calibration record; paper units only.");
  });
});

describe("receipts", () => {
  it("names the market, checkpoint and packet verdict with its qualifier; no figures", () => {
    const m = receiptMeta({ index: 3, sportMarket: "mlb/moneyline", checkpoint: "pregame", verdict: "MATCHES_CLOSE", src: "scripts/x/last_run_mlb.json" });
    const d = rails(m, "/receipts/3/");
    expect(m.title).toBe("Receipt 3: mlb/moneyline at pregame");
    expect(d).toBe("Ledger row 3: mlb/moneyline at the pregame checkpoint, verdict MATCHES_CLOSE (underpowered). Descriptive model-vs-market calibration; source last_run_mlb.json.");
  });
});

describe("games", () => {
  it("uses slate team names when present, else decodes the id", () => {
    const m = gameMeta({ sport: "mlb", gameId: "401816143", home: "Philadelphia Phillies", away: "New York Mets", tipoff: "2026-07-16T23:00Z", asOf: "2026-07-16T01:45:31Z" });
    const d = rails(m, "/games/mlb/401816143/");
    expect(m.title).toBe("New York Mets @ Philadelphia Phillies -- MLB game");
    expect(d).toBe("New York Mets @ Philadelphia Phillies, MLB on 2026-07-16: pregame probability, market surface and in-game calibration. Paper units only. As of 2026-07-16.");
    // A four-letter KX team blob is ambiguous, so lib/betdesc keeps it raw rather than guess.
    expect(gameMeta({ sport: "mlb", gameId: "KXMLBGAME-26JUL181610SDKC" }).title).toBe("SDKC -- MLB game");
    expect(gameMeta({ sport: "mlb", gameId: "KXMLBGAME-26JUL181510CINCOL" }).title).toBe("CIN @ COL -- MLB game");
  });
});

describe("explainers", () => {
  it("title from the essay, description from its dek", () => {
    const m = explainerMeta({ slug: "what-calibration-means", title: "What calibration means", dek: "A reliability diagram, read slowly." });
    expect(rails(m, "/analytics/explainers/what-calibration-means/")).toBe("Explainer: A reliability diagram, read slowly.");
  });
});

describe("findings", () => {
  it("a finding with packet verdicts names them; one without says descriptive", () => {
    const v = findingPageMeta({ slug: "x", title: "X", dek: "The dek.", verdicts: ["TRAILS_CLOSE", "MATCHES_CLOSE"], asOf: "2026-09-16" });
    expect(rails(v, "/analytics/findings/x/")).toBe("The dek. Verdict: TRAILS_CLOSE, MATCHES_CLOSE (underpowered). As of 2026-09-16.");
    const d = findingPageMeta({ slug: "shrinkage", title: "When the leaderboard regresses", dek: "Published empirical-Bayes movement.", verdicts: [], asOf: null },
      { openGraph: { images: [{ url: "/brand/og-finding-shrinkage.png" }] }, twitter: { images: ["/brand/og-finding-shrinkage.png"] } });
    expect(rails(d, "/analytics/findings/shrinkage/")).toBe("Published empirical-Bayes movement. Descriptive exhibit; no packet verdict.");
    expect(d.openGraph).toMatchObject({ images: [{ url: "/brand/og-finding-shrinkage.png" }] });
  });
});

describe("redirect stubs", () => {
  it("noindex, canonical on the destination, a description naming the retired path", () => {
    const m = stubMeta("/today/", "/desk/", "Desk");
    expect(m.robots).toEqual({ index: false, follow: true });
    expect(m.alternates?.canonical).toBe(`${ORIGIN}/desk/`);
    expect(m.description).toBe("The page /today/ moved to Desk (/desk/).");
  });
});
