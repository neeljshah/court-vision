import { afterEach, describe, expect, it, vi } from "vitest";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { api, type ClvScoreboard as Clv, type QuantClv } from "@/lib/p5api";
import { ClvFeedbackPanel } from "../ClvFeedbackPanel";
import { PaperHistory } from "../PaperHistory";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Percent units from public/demo-data/api_paper_clv.json and api_quant_clv.json.
const PUBLIC_CLV: Clv = {
  n_bets: 1233,
  pct_beat_close: 36.3341,
  mean_clv_pct: 4.368363,
  clv_is_proxy: true,
  by_sport: {
    soccer_intl: { n: 4, pct_beat_close: 100, mean_clv_pct: 26.011333 },
  },
};

function stat(label: string, selector: "div" | "span"): HTMLElement {
  const container = screen.getByText(label, { selector }).parentElement;
  if (!container) throw new Error(`Missing stat container for ${label}`);
  return container;
}

function renderFeedback(summary: Clv = PUBLIC_CLV) {
  const payload: QuantClv = {
    status: "ok",
    clv: { ...summary, by_sport: summary.by_sport ?? {}, vs_close_proven: false },
    edge_claimed: false,
    real_money_enabled: false,
  };
  vi.spyOn(api, "getQuantClv").mockResolvedValue(payload);
  vi.spyOn(api, "getImproveTimeline").mockResolvedValue({
    status: "ok", cycles: [], n_promoted: 0, enabled: false, edge_claimed: false,
  });
  render(<ClvFeedbackPanel />);
}

function renderHistory(summary: Clv = PUBLIC_CLV) {
  vi.spyOn(api, "getPaperTrail").mockResolvedValue({ status: "ok", count: 0, trail: [] });
  vi.spyOn(api, "getPaperClv").mockResolvedValue(summary);
  render(<PaperHistory />);
}

describe("CLV summary consumers render only the site-wide sentence", () => {
  it.each([PUBLIC_CLV, { ...PUBLIC_CLV, n_bets: 0, pct_beat_close: null, mean_clv_pct: null }])(
    "ClvFeedbackPanel shows no CLV figure (%#)", async (summary) => {
      renderFeedback(summary);
      expect(await screen.findByTestId("clv-feedback-unavailable")).toHaveTextContent(CLV_UNAVAILABLE);
      expect(screen.queryByText("+4.37%")).toBeNull();
      expect(screen.queryByText("+26.01%")).toBeNull();
    });

  it("PaperHistory shows no CLV summary figure", async () => {
    renderHistory();
    expect(await screen.findByTestId("paper-history-clv-unavailable")).toHaveTextContent(CLV_UNAVAILABLE);
    expect(screen.queryByText("+4.4%")).toBeNull();
    expect(screen.queryByText("36.3%")).toBeNull();
  });
});
