import type { ComponentType } from "react";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { findingsIndex } from "@/lib/analytics/findingsIndex";
import FindingsLayout from "./layout";
import BookmakerAccuracyPage from "./bookmaker-accuracy/page";
import EffectiveSampleSizePage from "./effective-sample-size/page";
import FavoriteLongshotPage from "./favorite-longshot/page";
import ForecastLifePage from "./forecast-life/page";
import IngameJoinIntegrityPage from "./ingame-join-integrity/page";
import LeagueParityPage from "./league-parity/page";
import LineupSynergyPage from "./lineup-synergy/page";
import MlbLeaderboardsPage from "./mlb-leaderboards/page";
import NbaMomentumPage from "./nba-momentum/page";
import Q4ShiftPage from "./q4-shift/page";
import ReliabilityPage from "./reliability/page";
import RetractionPage from "./retraction/page";
import RimDeterrencePage from "./rim-deterrence/page";
import ShrinkagePage from "./shrinkage/page";
import SoccerHomeAdvantagePage from "./soccer-home-advantage/page";
import TennisPage from "./tennis/page";
import VerdictFlipsPage from "./verdict-flips/page";

const pages: Record<string, ComponentType> = {
  "bookmaker-accuracy": BookmakerAccuracyPage,
  "effective-sample-size": EffectiveSampleSizePage,
  "favorite-longshot": FavoriteLongshotPage,
  "forecast-life": ForecastLifePage,
  "ingame-join-integrity": IngameJoinIntegrityPage,
  "league-parity": LeagueParityPage,
  "lineup-synergy": LineupSynergyPage,
  "mlb-leaderboards": MlbLeaderboardsPage,
  "nba-momentum": NbaMomentumPage,
  "q4-shift": Q4ShiftPage,
  reliability: ReliabilityPage,
  retraction: RetractionPage,
  "rim-deterrence": RimDeterrencePage,
  shrinkage: ShrinkagePage,
  "soccer-home-advantage": SoccerHomeAdvantagePage,
  tennis: TennisPage,
  "verdict-flips": VerdictFlipsPage,
};

it.each(findingsIndex)("renders index links before and after $slug", ({ slug }) => {
  const Page = pages[slug];
  const { container } = render(<FindingsLayout><Page /></FindingsLayout>);
  const heading = screen.getByRole("heading", { level: 1 });
  const links = screen.getAllByRole("link", { name: "Findings" });
  expect(links).toHaveLength(2);
  expect(links[0].compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(heading.compareDocumentPosition(links[1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(container.textContent).toContain(heading.textContent);
});
