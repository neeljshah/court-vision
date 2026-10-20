// T4 template lint: every finding page renders the FindingTemplate blocks in order, verdict slots
// carry only packet labels, and the page text holds no banned word and no retracted figure.
// (The retraction route is a redirect stub to /evidence/retractions/, so it is not a T4 page.)
import type { ComponentType } from "react";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { isPacketVerdict, RETRACTED_TOKENS } from "@/lib/packetVerdicts";
import { FINDING_BLOCKS } from "./FindingTemplate";
import { FINDING_SPECS } from "./findingSpecs";
import BookmakerAccuracyPage from "@/app/(analytics)/analytics/findings/bookmaker-accuracy/page";
import EffectiveSampleSizePage from "@/app/(analytics)/analytics/findings/effective-sample-size/page";
import FavoriteLongshotPage from "@/app/(analytics)/analytics/findings/favorite-longshot/page";
import ForecastLifePage from "@/app/(analytics)/analytics/findings/forecast-life/page";
import IngameJoinIntegrityPage from "@/app/(analytics)/analytics/findings/ingame-join-integrity/page";
import LeagueParityPage from "@/app/(analytics)/analytics/findings/league-parity/page";
import LineupSynergyPage from "@/app/(analytics)/analytics/findings/lineup-synergy/page";
import MlbLeaderboardsPage from "@/app/(analytics)/analytics/findings/mlb-leaderboards/page";
import NbaMomentumPage from "@/app/(analytics)/analytics/findings/nba-momentum/page";
import Q4ShiftPage from "@/app/(analytics)/analytics/findings/q4-shift/page";
import ReliabilityPage from "@/app/(analytics)/analytics/findings/reliability/page";
import RimDeterrencePage from "@/app/(analytics)/analytics/findings/rim-deterrence/page";
import ShrinkagePage from "@/app/(analytics)/analytics/findings/shrinkage/page";
import SoccerHomeAdvantagePage from "@/app/(analytics)/analytics/findings/soccer-home-advantage/page";
import TennisPage from "@/app/(analytics)/analytics/findings/tennis/page";
import VerdictFlipsPage from "@/app/(analytics)/analytics/findings/verdict-flips/page";

const pages: Record<string, ComponentType> = {
  "bookmaker-accuracy": BookmakerAccuracyPage, "effective-sample-size": EffectiveSampleSizePage,
  "favorite-longshot": FavoriteLongshotPage, "forecast-life": ForecastLifePage,
  "ingame-join-integrity": IngameJoinIntegrityPage, "league-parity": LeagueParityPage,
  "lineup-synergy": LineupSynergyPage, "mlb-leaderboards": MlbLeaderboardsPage,
  "nba-momentum": NbaMomentumPage, "q4-shift": Q4ShiftPage, reliability: ReliabilityPage,
  "rim-deterrence": RimDeterrencePage, shrinkage: ShrinkagePage,
  "soccer-home-advantage": SoccerHomeAdvantagePage, tennis: TennisPage, "verdict-flips": VerdictFlipsPage,
};

const BANNED = /\bedge\b|\bROI\b|\bprofit|\bbeats?\b|\bmoney\b/i;
const esc = (t: string) => t.replace(/[.+%]/g, (c) => "[" + c + "]");
const retractedRe = (t: string) => new RegExp("(^|[^0-9.])" + esc(t) + "(?![0-9])");

describe("FindingTemplate (T4)", () => {
  it("has a spec for every page and a page for every spec", () => {
    expect(Object.keys(pages).sort()).toEqual(Object.keys(FINDING_SPECS).sort());
  });

  it.each(Object.keys(pages))("%s renders the T4 blocks in order", (slug) => {
    const Page = pages[slug];
    const { container } = render(<Page />);
    const root = container.querySelector('[data-template="T4"]');
    expect(root).not.toBeNull();
    const order = [...root!.querySelectorAll("[data-block]")].map((n) => n.getAttribute("data-block"))
      .filter((b) => (FINDING_BLOCKS as readonly string[]).includes(b!));
    expect(order).toEqual([...FINDING_BLOCKS]);
    expect(root!.querySelector("h1")?.textContent).toBe(FINDING_SPECS[slug].title);

    const status = root!.querySelector('[data-block="status"]')!;
    const verdicts = [...status.querySelectorAll("[data-verdict]")].map((n) => n.getAttribute("data-verdict"));
    expect(verdicts.length).toBeGreaterThan(0);
    for (const v of verdicts) expect(v === "none" || isPacketVerdict(v)).toBe(true);
    expect(status.textContent).toMatch(/n = \S/);
    expect(status.textContent).toMatch(/interval/);
    expect(status.querySelector(".ev-asof")).not.toBeNull();
    expect(status.querySelector(".ev-chip")).not.toBeNull();

    expect(root!.querySelectorAll('[data-block="limitations"] li').length).toBeGreaterThanOrEqual(3);
    expect(root!.querySelectorAll('[data-block="verdict-history"] li').length).toBeGreaterThanOrEqual(1);
    expect(root!.querySelector('[data-block="quoted-on"] [data-testid="quoted-on"]')).not.toBeNull();

    // Banned words: template-owned blocks (the exhibit body quotes generated artifact text verbatim).
    const own = [...root!.querySelectorAll("[data-block]")].filter((n) => n.getAttribute("data-block") !== "evidence")
      .map((n) => n.textContent).join(" ") + (root!.querySelector("h1")?.textContent ?? "");
    expect(own).not.toMatch(BANNED);
    const text = root!.textContent ?? "";
    for (const t of RETRACTED_TOKENS) expect(text).not.toMatch(retractedRe(t));
  });

  it("reads packet verdicts from the artifact where it records one", () => {
    const { container } = render(<SoccerHomeAdvantagePage />);
    expect(container.querySelector('[data-block="status"] [data-verdict="CONFIRMED_LOCAL"]')).not.toBeNull();
    const mlb = render(<MlbLeaderboardsPage />).container;
    expect(mlb.querySelector('[data-block="status"] [data-verdict="REJECT"]')).not.toBeNull();
  });
});
