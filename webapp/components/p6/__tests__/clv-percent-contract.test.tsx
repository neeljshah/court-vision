import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";
import type { ClvScoreboard as Clv } from "@/lib/p5api";
import { ClvScoreboard } from "../ClvScoreboard";

afterEach(cleanup);

// Public demo-data/api_paper_clv.json values are already percentages.
// Render assertions guard against treating percent-valued fields as fractions.
const PUBLIC_CLV: Clv = {
  n_bets: 1233,
  pct_beat_close: 36.3341,
  mean_clv_pct: 4.368363,
  median_clv_pct: -3.182161,
  basis: "true_close",
  n_proxy: 264,
  clv_is_proxy: true,
  by_sport: {
    mlb: { n: 1115, pct_beat_close: 34.4395, mean_clv_pct: 3.421528 },
    soccer_intl: { n: 4, pct_beat_close: 100, mean_clv_pct: 26.011333 },
  },
};

describe("ClvScoreboard renders only the site-wide CLV sentence", () => {
  it.each([PUBLIC_CLV, null, { status: "unavailable" as const, reason: "offline" }])(
    "shows no CLV figure (%#)", (clv) => {
      render(<ClvScoreboard clv={clv as Clv | null} />);
      expect(screen.getByTestId("clv-scoreboard-unavailable")).toHaveTextContent(CLV_UNAVAILABLE);
      for (const v of ["36.3%", "+4.4%", "-3.2%", "+26.0%"]) expect(screen.queryByText(v)).toBeNull();
    });
});
