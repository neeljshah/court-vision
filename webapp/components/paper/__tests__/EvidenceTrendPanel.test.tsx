// EvidenceTrendPanel.test.tsx -- empty/short/normal states. Mocks fetchHonest's
// underlying fetch so no real disk I/O / network.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { CLV_UNAVAILABLE } from "@/lib/clvUnavailable";
import { render, screen, waitFor } from "@testing-library/react";
import { EvidenceTrendPanel } from "@/components/paper/EvidenceTrendPanel";

// recharts' ResponsiveContainer (used by Sparkline) needs ResizeObserver -- jsdom
// has none; a minimal no-op stub is enough for these render-only assertions.
// Direct assignment (not vi.stubGlobal) so afterEach's unstubAllGlobals -- which
// must clear the per-test fetch stubs -- doesn't strip it after the first test.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as { ResizeObserver?: unknown }).ResizeObserver = ResizeObserverStub;

function mockFetchOnce(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok,
      status: ok ? 200 : 503,
      headers: { get: () => "application/json" },
      json: async () => body,
    }),
  );
}

describe("EvidenceTrendPanel", () => {
  it("renders only the site-wide CLV sentence, no trend figure", () => {
    render(<EvidenceTrendPanel />);
    const el = screen.getByTestId("evidence-trend-panel");
    expect(el).toHaveTextContent(CLV_UNAVAILABLE);
    expect(el.textContent).not.toMatch(/[+-]\d+\.\d{2}%/);
  });
});
