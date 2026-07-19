import { describe, it, expect } from "vitest";
import {
  humanizeMatchup,
  describeBet,
  describeBetShort,
  isProp,
} from "../betdesc";

describe("humanizeMatchup -- KX tickers never leak", () => {
  it("decodes a real MLB KX ticker to AWAY @ HOME", () => {
    expect(humanizeMatchup("KXMLBGAME-26JUL181510CINCOL")).toBe("CIN @ COL");
  });

  it("decodes a KXWCGAME ticker the same way", () => {
    // KX<LEAGUE>GAME-<YY><MON><DD><HHMM><AWAY3><HOME3>
    expect(humanizeMatchup("KXWCGAME-26JUL181000ARGFRA")).toBe("ARG @ FRA");
  });

  it("salvages trailing 6 letters when the date/time part is unknown", () => {
    expect(humanizeMatchup("KXNBAGAME-WEIRDPREFIXNYKBOS")).toBe("NYK @ BOS");
  });

  it("falls back to 'Kalshi market' when no team codes parse", () => {
    expect(humanizeMatchup("KXNBA-2026-NYK")).toBe("Kalshi market");
  });

  it("NEVER returns a raw KX ticker", () => {
    for (const t of [
      "KXMLBGAME-26JUL181510CINCOL",
      "KXNBA-2026-NYK",
      "KXWEIRD",
    ]) {
      expect(humanizeMatchup(t).startsWith("KX")).toBe(false);
    }
  });

  it("passes non-KX matchups through unchanged", () => {
    expect(humanizeMatchup("NYK @ SAS")).toBe("NYK @ SAS");
    expect(humanizeMatchup("BOS vs MIA")).toBe("BOS vs MIA");
  });

  it("extracts the matchup segment from a composite id", () => {
    expect(humanizeMatchup("mlb|CIN @ COL|1710000000")).toBe("CIN @ COL");
    // composite where the matchup slot holds a KX ticker
    expect(humanizeMatchup("mlb|KXMLBGAME-26JUL181510CINCOL|t")).toBe("CIN @ COL");
  });

  it("handles null / empty honestly", () => {
    expect(humanizeMatchup(null)).toBe("");
    expect(humanizeMatchup("")).toBe("");
  });
});

describe("describeBet -- props", () => {
  const prop = {
    market_type: "prop",
    prop_player: "Ildemaro Vargas",
    prop_stat: "hits",
    prop_side: "under",
    line: 0.5,
    side: "away",
    matchup: "CIN @ COL",
  };

  it("renders the full prop description", () => {
    expect(describeBet(prop)).toBe("Ildemaro Vargas UNDER 0.5 Hits");
  });

  it("abbreviates the player to last name in short form", () => {
    expect(describeBetShort(prop)).toBe("Vargas UNDER 0.5 Hits");
  });

  it("title-cases multi-word stats", () => {
    expect(
      describeBet({ market_type: "prop", prop_player: "A B", prop_stat: "total_bases", prop_side: "over", line: 1.5 }),
    ).toBe("A B OVER 1.5 Total Bases");
  });

  it("detects props by prop_player even without market_type", () => {
    expect(isProp({ prop_player: "X Y" })).toBe(true);
  });
});

describe("describeBet -- moneyline names the team from the matchup", () => {
  it("home side -> team after the @", () => {
    expect(describeBet({ market_type: "moneyline", side: "home", matchup: "CIN @ COL" })).toBe("COL ML");
  });

  it("away side -> team before the @", () => {
    expect(describeBet({ market_type: "moneyline", side: "away", matchup: "CIN @ COL" })).toBe("CIN ML");
  });

  it("win_home market_type encodes the side", () => {
    expect(describeBet({ market_type: "win_home", side: "", matchup: "NYK vs SAS" })).toBe("SAS ML");
  });

  it("falls back to the side label when no matchup is derivable", () => {
    expect(describeBet({ market_type: "moneyline", side: "home" })).toBe("HOME ML");
  });

  it("uses a team abbrev side directly", () => {
    expect(describeBet({ market_type: "h2h", side: "LAL", matchup: "LAL @ BOS" })).toBe("LAL ML");
  });
});

describe("describeBet -- totals and spread", () => {
  it("totals -> OVER line", () => {
    expect(describeBet({ market_type: "total", side: "over", line: 8.5 })).toBe("OVER 8.5");
  });

  it("spread -> team + signed line", () => {
    expect(describeBet({ market_type: "spread", side: "home", line: -1.5, matchup: "CIN @ COL" })).toBe("COL -1.5");
  });

  it("spread with positive line keeps the +", () => {
    expect(describeBet({ market_type: "spread", side: "away", line: 3.5, matchup: "CIN @ COL" })).toBe("CIN +3.5");
  });
});

describe("describeBet -- never renders an opaque 'prop away'", () => {
  it("unknown market falls back to a joined human label", () => {
    expect(describeBet({ market_type: "moneyline", side: "away", matchup: "CIN @ COL" })).not.toBe("moneyline away");
  });
});

describe("derivative composite markets + short team blobs (2026-07-19)", () => {
  it("decodes TOTAL-series tickers with an HHMM block", () => {
    expect(humanizeMatchup("KXMLBTOTAL-26JUL191335TEXATL")).toBe("TEX @ ATL");
  });
  it("shows the raw blob for ambiguous 5-letter team codes, never 'Kalshi market'", () => {
    expect(humanizeMatchup("KXWNBAGAME-26JUL19LADAL")).toBe("LADAL");
  });
  it("renders a composite total market as OVER <line>, not a moneyline", () => {
    expect(
      describeBet({ market: "total_10.5_over", side: "home",
                    matchup: "KXMLBTOTAL-26JUL191335TEXATL" } as never),
    ).toBe("OVER 10.5");
  });
  it("renders a composite spread market with the covering team", () => {
    expect(
      describeBet({ market: "spread_1.5_home", side: "home",
                    matchup: "KXMLBGAME-26JUL191335TEXATL" } as never),
    ).toBe("ATL -1.5");
  });
});
