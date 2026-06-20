import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { FreshnessBadge } from "../Primitives";
import { freshnessStatus } from "../LiveLinesPanel";
import { api, isUnavailable, type AllHonest, type Catalog } from "@/lib/p5api";
import { FacesPanel } from "../FacesPanel";

// ---------------------------------------------------------------------------
// Honesty-rail tests for LANE F (P6 dashboard). These gate the invariants:
//   * a stale/dead feed must NEVER read green 'fresh'
//   * a backend error degrades to the honest Unavailable sentinel
//   * no rendered component emits a $/pnl/roi/bankroll field (units only)
// ---------------------------------------------------------------------------

const HOUR_MS = 60 * 60 * 1000;

describe("freshnessStatus -- feed-age, not client-poll-age", () => {
  it("returns 'fresh' only when generated_at is within the threshold", () => {
    const recent = new Date(Date.now() - 5_000).toISOString();
    expect(freshnessStatus(recent)).toBe("fresh");
  });

  it("returns 'stale' when generated_at is hours old (dead upstream)", () => {
    const old = new Date(Date.now() - 3 * HOUR_MS).toISOString();
    expect(freshnessStatus(old)).toBe("stale");
  });

  it("returns 'unknown' (never fresh) when generated_at is missing", () => {
    expect(freshnessStatus(null)).toBe("unknown");
    expect(freshnessStatus(undefined)).toBe("unknown");
    expect(freshnessStatus("not-a-date")).toBe("unknown");
  });
});

describe("FreshnessBadge tone -- stale reads amber, not green", () => {
  it("renders amber (not green) for an hours-old feed", () => {
    const old = new Date(Date.now() - 3 * HOUR_MS).toISOString();
    render(<FreshnessBadge asOf={old} status={freshnessStatus(old)} />);
    const pill = screen.getByText("stale");
    // amber tone class set, green tier-a class absent -> dead feed never green
    expect(pill.className).toContain("amber");
    expect(pill.className).not.toContain("tier-a");
  });

  it("renders green only for a genuinely fresh feed", () => {
    const recent = new Date(Date.now() - 5_000).toISOString();
    render(<FreshnessBadge asOf={recent} status={freshnessStatus(recent)} />);
    const pill = screen.getByText("fresh");
    expect(pill.className).toContain("tier-a");
  });

  // Freshness-path rail: a backend that stamps status="ok"/"fresh" on a snapshot
  // whose asOf is actually hours old must NOT read green. The badge re-derives
  // the age locally and demotes the claimed-green to amber (stale-never-green).
  it("demotes a claimed-fresh status to amber when asOf is actually stale", () => {
    const old = new Date(Date.now() - 3 * HOUR_MS).toISOString();
    render(<FreshnessBadge asOf={old} status="ok" />);
    const pill = screen.getByText("ok");
    expect(pill.className).not.toContain("tier-a");
    expect(pill.className).toContain("amber");
  });

  it("keeps green when status=ok AND asOf is genuinely fresh", () => {
    const recent = new Date(Date.now() - 5_000).toISOString();
    render(<FreshnessBadge asOf={recent} status="ok" />);
    const pill = screen.getByText("ok");
    expect(pill.className).toContain("tier-a");
  });
});

describe("getJson -- backend errors degrade to Unavailable", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    vi.restoreAllMocks();
  });

  it("maps a non-ok (500) response to {status:'unavailable'}", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ should: "not be rendered" }),
    }) as unknown as typeof fetch;

    const res = await api.bestbets("nba");
    expect(isUnavailable(res)).toBe(true);
    expect((res as { reason?: string }).reason).toContain("500");
  });

  it("maps a non-JSON (HTML error page) response to Unavailable", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/html" }),
      json: async () => {
        throw new Error("not json");
      },
    }) as unknown as typeof fetch;

    const res = await api.bestbets("nba");
    expect(isUnavailable(res)).toBe(true);
  });
});

describe("no rendered component emits a $/pnl/roi/bankroll field", () => {
  it("source scan of components/p6 is clean of dollar/pnl/roi/bankroll output", () => {
    const testDir = dirname(fileURLToPath(import.meta.url));
    const dir = join(testDir, "..");
    const files = readdirSync(dir).filter((f) => f.endsWith(".tsx"));
    // forbid currency-symbol UI and the banned money field identifiers.
    const banned = /\bpnl\b|\bbankroll\b|\$\{?[a-zA-Z_]*?(pnl|roi|profit|dollars?)\b/i;
    const offenders: string[] = [];
    for (const f of files) {
      const src = readFileSync(join(dir, f), "utf8");
      if (banned.test(src)) offenders.push(f);
    }
    expect(offenders).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// FacesPanel -- HonestyBadge + ViolationList state-machine tests
//
// The four acceptance cases (QA #1/#9/#10):
//   a) null honest + null err  -> neutral 'checking...' badge, NOT red, NOT green
//   b) err='catalog torn'      -> red/unavailable badge surfacing the reason
//   c) honest.ok===true        -> green 'all honest' badge
//   d) honest.ok===false       -> red badge + violation list renders
// ---------------------------------------------------------------------------

// Minimal valid catalog so the panel body doesn't stay in the loading branch
const STUB_CATALOG: Catalog = {
  status: "ok",
  faces: [],
  count: 0,
  edge_claimed: false,
  real_money_enabled: false,
};

const STUB_HONEST_OK: AllHonest = {
  ok: true,
  violations: [],
  n_faces: 2,
};

const STUB_HONEST_FAIL: AllHonest = {
  ok: false,
  violations: [{ face: "prediction", reason: "edge_claimed=true" }],
  n_faces: 2,
};

afterEach(() => vi.restoreAllMocks());

describe("FacesPanel -- HonestyBadge neutral pre-resolve state (QA #1/#9/#10)", () => {
  it("(a) with honest=null AND err=null: badge is neutral 'checking...' -- NOT red, NOT green", () => {
    // Both API calls remain pending forever (never resolve) -> null state
    vi.spyOn(api, "getCatalog").mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, "getAllHonest").mockReturnValue(new Promise(() => {}));

    render(<FacesPanel />);

    const badge = screen.getByText(/checking/i);
    expect(badge).toBeTruthy();
    // Must NOT contain red class names (red-400, red-950)
    expect(badge.className).not.toMatch(/red/);
    // Must NOT contain green tier-a class
    expect(badge.className).not.toMatch(/tier-a/);
    // No violation box in the DOM
    expect(screen.queryByText(/honesty check unavailable/i)).toBeNull();
    expect(screen.queryByText(/honesty check failed/i)).toBeNull();
  });

  it("(b) with err='catalog torn': badge is red/unavailable and surfaces the reason", async () => {
    vi.spyOn(api, "getCatalog").mockResolvedValue({
      status: "unavailable",
      reason: "catalog torn",
    } as unknown as Catalog);
    vi.spyOn(api, "getAllHonest").mockResolvedValue({
      status: "unavailable",
      reason: "catalog torn",
    } as unknown as AllHonest);

    render(<FacesPanel />);

    // After the fetch resolves, the badge must switch to red unavailable
    await waitFor(() =>
      expect(screen.getByText(/honesty check unavailable/i)).toBeTruthy(),
    );
    const badge = screen.getByText(/honesty check unavailable/i);
    expect(badge.className).toMatch(/red/);
    // Reason must surface somewhere in the rendered tree
    expect(screen.getByText(/catalog torn/i)).toBeTruthy();
  });

  it("(c) with honest.ok===true: badge is green 'all honest'", async () => {
    vi.spyOn(api, "getCatalog").mockResolvedValue(STUB_CATALOG);
    vi.spyOn(api, "getAllHonest").mockResolvedValue(STUB_HONEST_OK);

    render(<FacesPanel />);

    await waitFor(() =>
      expect(screen.getByText(/all honest/i)).toBeTruthy(),
    );
    const badge = screen.getByText(/all honest/i);
    expect(badge.className).toMatch(/tier-a/);
    expect(badge.className).not.toMatch(/red/);
  });

  it("(d) with honest.ok===false: badge is red and violation list renders", async () => {
    vi.spyOn(api, "getCatalog").mockResolvedValue(STUB_CATALOG);
    vi.spyOn(api, "getAllHonest").mockResolvedValue(STUB_HONEST_FAIL);

    render(<FacesPanel />);

    // Both the header badge and the violation-box paragraph use "honesty check failed"
    // text (in slightly different casing). Wait until at least one is present.
    await waitFor(() =>
      expect(screen.getAllByText(/honesty check failed/i).length).toBeGreaterThan(0),
    );
    // The badge is a <span> in the panel header -- query by role or by element type
    const badges = screen.getAllByText(/honesty check failed/i);
    // At least one element (the badge span) must carry the red class
    const anyRed = badges.some((el) => el.className.includes("red"));
    expect(anyRed).toBe(true);
    // Violation entry must appear in the list
    expect(screen.getByText(/edge_claimed=true/i)).toBeTruthy();
    expect(screen.getByText(/prediction/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// FacesPanel -- catalog pre-resolve skeleton (ws2-faces-skeleton)
//
// While getCatalog is in-flight (catalog===null, no catErr) the panel must
// render skeleton placeholders rather than a bare 'loading...' string.
// The HonestyBadge must remain in its neutral 'checking...' state because
// getAllHonest is also still pending.
// ---------------------------------------------------------------------------

describe("FacesPanel -- catalog-null state renders skeleton, not 'loading...'", () => {
  it("shows skeleton placeholders (not the literal 'loading...' string) while catalog is pending", () => {
    // Both API calls stay pending forever -> null state for both
    vi.spyOn(api, "getCatalog").mockReturnValue(new Promise(() => {}));
    vi.spyOn(api, "getAllHonest").mockReturnValue(new Promise(() => {}));

    render(<FacesPanel />);

    // The literal bare 'loading...' text must NOT appear
    expect(screen.queryByText("loading...")).toBeNull();

    // The skeleton container must be present with the accessible label
    expect(screen.getByRole("status", { name: /loading faces/i })).toBeTruthy();

    // HonestyBadge must remain neutral -- neither red nor green
    const checkingBadge = screen.getByText(/checking/i);
    expect(checkingBadge).toBeTruthy();
    expect(checkingBadge.className).not.toMatch(/red/);
    expect(checkingBadge.className).not.toMatch(/tier-a/);
  });
});
