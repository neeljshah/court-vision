import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import nbaSnapshot from "@/public/demo-data/api_predict_nba.json";
import soccerIntlSnapshot from "@/public/demo-data/api_predict_soccer_intl.json";

const getPredict = vi.fn();
const bestbets = vi.fn();

vi.mock("@/lib/api", () => ({
  HONEST_DISCLAIMER: "honest disclaimer",
  api: {
    getPredict: (...args: unknown[]) => getPredict(...args),
    bestbets: (...args: unknown[]) => bestbets(...args),
  },
  isUnavailable: (value: { status?: string }) => value.status === "unavailable",
}));

vi.mock("@/lib/board", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/board")>()),
  fetchSlate: vi.fn().mockResolvedValue(null),
}));

vi.mock("../SlateAgeBar", () => ({
  SlateAgeBar: ({ generatedAt }: { generatedAt: string | null }) => (
    <span data-testid="slate-age">{generatedAt}</span>
  ),
}));

afterEach(() => {
  getPredict.mockReset();
  bestbets.mockReset();
  vi.unstubAllEnvs();
  vi.resetModules();
});

function emptyEnvelope(sport: string, overrides = {}) {
  return { status: "ok", sport, generated_at: null, predictions: [], ...overrides };
}

async function importGames(snapshot: boolean) {
  vi.stubEnv("NEXT_PUBLIC_DATA_MODE", snapshot ? "snapshot" : "");
  vi.resetModules();
  const [{ default: GamesPage }, { SlateCards }] = await Promise.all([
    import("../page"),
    import("../SlateCards"),
  ]);
  return { GamesPage, SlateCards };
}

const record = {
  sport: "mlb",
  game_id: "published-game",
  home: "Home",
  away: "Away",
  tipoff: "2026-07-26T16:10Z",
  pregame_probs: { home_ml: 0.6, away_ml: 0.4 },
  markets: [],
  leak_guard: { in_sample: false },
  produced_at: null,
};

describe("Games snapshot labels", () => {
  it("labels the page and empty slate as a published snapshot", async () => {
    getPredict.mockImplementation((sport: string) => Promise.resolve(emptyEnvelope(sport)));
    bestbets.mockResolvedValue({ status: "unavailable", reason: "no best bets" });
    const { GamesPage, SlateCards } = await importGames(true);

    const page = render(await GamesPage());
    expect(screen.getByText("published snapshot")).toBeInTheDocument();
    page.unmount();

    render(<SlateCards />);
    await waitFor(() =>
      expect(screen.getByText("0 snapshot games")).toBeInTheDocument(),
    );
    expect(screen.getAllByText(/no games in published snapshot/i)).not.toHaveLength(0);
  });

  it("keeps live labels in normal mode", async () => {
    getPredict.mockImplementation((sport: string) => Promise.resolve(emptyEnvelope(sport)));
    bestbets.mockResolvedValue({ status: "unavailable", reason: "no best bets" });
    const { GamesPage, SlateCards } = await importGames(false);

    const page = render(await GamesPage());
    expect(screen.getByText("today's slate")).toBeInTheDocument();
    page.unmount();

    render(<SlateCards />);
    await waitFor(() => expect(screen.getByText("0 live games")).toBeInTheDocument());
    expect(screen.getAllByText(/no games live now/i)).not.toHaveLength(0);
  });

  it("keeps published NBA and soccer-intl withholding notes and timestamps verbatim", async () => {
    getPredict.mockImplementation((sport: string) =>
      Promise.resolve(
        sport === "nba"
          ? nbaSnapshot
          : sport === "soccer_intl"
            ? soccerIntlSnapshot
          : emptyEnvelope(sport),
      ),
    );
    bestbets.mockResolvedValue({ status: "unavailable", reason: "no best bets" });
    const { SlateCards } = await importGames(true);

    render(<SlateCards />);
    await waitFor(() =>
      expect(screen.getByText(nbaSnapshot.note)).toBeInTheDocument(),
    );
    expect(screen.getByText(soccerIntlSnapshot.note)).toBeInTheDocument();
    expect(screen.getAllByTestId("slate-age").map((node) => node.textContent)).toContain(
      nbaSnapshot.generated_at,
    );
    expect(screen.getAllByTestId("slate-age").map((node) => node.textContent)).toContain(
      soccerIntlSnapshot.generated_at,
    );
  });

  it("renders a transport unavailable response as an error", async () => {
    getPredict.mockImplementation((sport: string) =>
      Promise.resolve(
        sport === "nba"
          ? { status: "unavailable", reason: "transport unavailable" }
          : emptyEnvelope(sport),
      ),
    );
    bestbets.mockResolvedValue({ status: "unavailable", reason: "no best bets" });
    const { SlateCards } = await importGames(true);

    render(<SlateCards />);
    await waitFor(() => expect(screen.getByText("transport unavailable")).toBeInTheDocument());
  });

  it("links only published snapshot details and fails closed without a manifest", async () => {
    const unlistedRecord = { ...record, game_id: "unlisted-game" };
    getPredict.mockImplementation((sport: string) =>
      Promise.resolve(sport === "mlb" ? emptyEnvelope(sport, { predictions: [record, unlistedRecord] }) : emptyEnvelope(sport)),
    );
    bestbets.mockResolvedValue({ status: "unavailable", reason: "no best bets" });
    const { SlateCards } = await importGames(true);
    const { rerender } = render(
      <SlateCards publishedGames={[{ sport: "mlb", game_id: "published-game" }]} />,
    );

    await waitFor(() =>
      expect(screen.getByRole("link", { name: /away at home/i })).toHaveAttribute(
        "href",
        "/games/mlb/published-game",
      ),
    );
    expect(screen.getAllByRole("link", { name: /away at home/i })).toHaveLength(1);
    expect(screen.getByText("Detail not published in this snapshot")).toBeInTheDocument();

    rerender(<SlateCards />);
    expect(screen.queryByRole("link", { name: /away at home/i })).toBeNull();
    expect(screen.getAllByText("Detail not published in this snapshot")).toHaveLength(2);

    rerender(<SlateCards publishedGames={[]} />);
    expect(screen.queryByRole("link", { name: /away at home/i })).toBeNull();
  });
});
