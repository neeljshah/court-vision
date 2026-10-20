import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RecordsClvStrip } from "../RecordsClvStrip";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";

// RecordsClvStrip renders only the site-wide CLV Unavailable sentence: no
// closing-line-value reading exists (JOB_EVIDENCE_PACKET s4/s5).
describe("RecordsClvStrip", () => {
  it.each([
    null,
    { status: "unavailable" as const, reason: "offline" },
    { n_bets: 1233, pct_beat_close: 36.3341, mean_clv_pct: 4.368363, by_sport: null, clv_is_proxy: true },
  ])("renders the sentence and no CLV figure (%#)", (clv) => {
    render(<RecordsClvStrip clv={clv} />);
    const strip = screen.getByTestId("records-clv-strip");
    expect(strip).toHaveTextContent(CLV_UNAVAILABLE);
    expect(strip.textContent ?? "").not.toMatch(/[+-]\d+\.\d%|36\.3|\$\s?\d/);
  });
});
