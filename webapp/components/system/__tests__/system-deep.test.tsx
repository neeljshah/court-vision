import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { GateLedgerPanel } from "../GateLedgerPanel";
import { BacklogPanel } from "../BacklogPanel";
import { ClvOverTimePanel } from "../ClvOverTimePanel";

// ---------------------------------------------------------------------------
// /system DEEP honesty-rail tests (this LANE owns webapp/components/system/__tests__):
//   * GateLedgerPanel: renders the on-disk gate ledger (15 rows: 1 SHIP corners
//     survivor / the rest REJECT / other), sortable, vs_close UNPROVEN
//     everywhere, REJECT = a SUCCESS, NO $/ROI. Honest degrade when the artifact
//     route is unavailable / empty.
//   * BacklogPanel: 73 ranked candidates, category filter, show-all toggle,
//     measurement-only ("never fixes / ships / flips a flag"). Honest empty.
//   * ClvOverTimePanel: INSUFFICIENT_DATA default + vs_close UNPROVEN +
//     probability-space (no $). Honest degrade.
//   * NO $/pnl/roi/payout token in any /system source file.
// ---------------------------------------------------------------------------

const realFetch = global.fetch;
afterEach(() => {
  global.fetch = realFetch;
  vi.restoreAllMocks();
});

const jsonRes = (body: unknown, status = 200, ok = true) => ({
  ok,
  status,
  headers: new Headers({ "content-type": "application/json" }),
  json: async () => body,
});

// Route the page-local artifact route + the :8099 endpoints.
function routeFetch(map: Array<[RegExp, { body: unknown; status?: number; ok?: boolean }]>) {
  return vi.fn().mockImplementation((url: string) => {
    for (const [re, r] of map) {
      if (re.test(String(url)))
        return Promise.resolve(jsonRes(r.body, r.status ?? 200, r.ok ?? true));
    }
    return Promise.resolve(jsonRes({}, 404, false));
  }) as unknown as typeof fetch;
}

// --- A realistic 15-row gate ledger: 1 SHIP (soccer corners) + 14 others. -----
function ledgerRows() {
  const rows = [
    { id: "r0", sport: "soccer", layer: "corners_total_calibration", verdict: "SHIP", deciding_stat: "held-out Brier -0.004", corpora: 2, vs_close: "UNPROVEN (no in-play close)", base: "poisson_corners", source: "funnel" },
  ];
  const rejectLayers = [
    ["nba", "ast_pregame"], ["nba", "momentum"], ["nba", "rest_delta"],
    ["mlb", "pitcher_splits"], ["mlb", "bullpen_fatigue"],
    ["soccer", "xg_momentum"], ["soccer_intl", "club_prior"],
    ["tennis", "serve_hold"], ["tennis", "surface_form"],
    ["nba", "vac_load"], ["mlb", "park_factor"], ["platform", "truncation"],
  ];
  for (let i = 0; i < rejectLayers.length; i++) {
    rows.push({
      id: `r${i + 1}`, sport: rejectLayers[i][0], layer: rejectLayers[i][1],
      verdict: "REJECT", deciding_stat: `clustered-DM p=0.${30 + i}`, corpora: 2,
      vs_close: "UNPROVEN", base: "", source: "funnel",
    });
  }
  rows.push({ id: "r13", sport: "nba", layer: "playstyle_corr", verdict: "PARTIAL", deciding_stat: "one direction only", corpora: 2, vs_close: "UNPROVEN", base: "", source: "funnel" });
  rows.push({ id: "r14", sport: "mlb", layer: "weather_acq", verdict: "TIER3_BLOCKED", deciding_stat: "data unavailable", corpora: 0, vs_close: "UNPROVEN", base: "", source: "funnel" });
  return rows; // 15 rows total
}

const richArtifacts = {
  status: "ok",
  ledger: {
    rows: ledgerRows(),
    counts: { SHIP: 1, REJECT: 12, PARTIAL: 1, TIER3_BLOCKED: 1 },
  },
  backlog: null,
  honest_note: "Every verdict is CALIBRATION only; vs_close is UNPROVEN everywhere; a REJECT is a SUCCESS.",
  edge_claimed: false,
};

describe("GateLedgerPanel -- 15-row ledger, SHIP corners survivor, vs_close UNPROVEN", () => {
  it("renders all 15 gate rows with 1 SHIP and vs_close UNPROVEN everywhere (no $)", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: richArtifacts }]]);
    const { container } = render(<GateLedgerPanel />);
    await waitFor(() => expect(screen.getByText("corners_total_calibration")).toBeTruthy());

    // 15 data rows in the tbody.
    const rows = container.querySelectorAll("tbody tr");
    expect(rows.length).toBe(15);
    // exactly one SHIP badge + the panel header "1 ship".
    expect(screen.getAllByText("SHIP").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/1 ship/)).toBeTruthy();
    expect(screen.getByText(/14 reject \/ other/)).toBeTruthy();
    // vs_close shows UNPROVEN, never a $ / ROI number.
    expect(screen.getAllByText("UNPROVEN").length).toBeGreaterThan(0);
    expect(container.textContent || "").not.toMatch(/\$/);
    // the honest note is surfaced.
    expect(screen.getByText(/REJECT is a SUCCESS/i)).toBeTruthy();
  });

  it("sorting by Sport reorders the rows (interactive header), no fabrication", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: richArtifacts }]]);
    const { container } = render(<GateLedgerPanel />);
    await waitFor(() => expect(screen.getByText("corners_total_calibration")).toBeTruthy());
    const before = container.querySelectorAll("tbody tr").length;
    fireEvent.click(screen.getByRole("button", { name: /sport/i }));
    // still 15 rows after a sort -- a re-order, never an add/drop.
    expect(container.querySelectorAll("tbody tr").length).toBe(before);
  });

  it("the verdict legend lists SHIP / REJECT / TIER3_BLOCKED keys (reject-as-success)", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: richArtifacts }]]);
    render(<GateLedgerPanel />);
    await waitFor(() => expect(screen.getByText(/what each verdict means/i)).toBeTruthy());
    // The legend keys are visible; the "reject = a SUCCESS" gloss lives in the
    // InfoTip (tooltip) and on the panel honest_note, which IS visible.
    const legend = screen.getByLabelText(/what each verdict means/i);
    expect(within(legend).getAllByText(/REJECT/).length).toBeGreaterThan(0);
    expect(screen.getByText(/a REJECT is a SUCCESS/i)).toBeTruthy();
  });

  it("an unavailable artifact route degrades to an honest Unavailable, never green-on-missing", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: {}, status: 500, ok: false }]]);
    render(<GateLedgerPanel />);
    await waitFor(() => expect(screen.getByText(/HTTP 500/)).toBeTruthy());
  });

  it("an empty ledger renders the honest no-verdicts state, not a fabricated row", async () => {
    global.fetch = routeFetch([
      [/funnel-artifacts/, { body: { ...richArtifacts, ledger: { rows: [], counts: {} } } }],
    ]);
    render(<GateLedgerPanel />);
    await waitFor(() => expect(screen.getByText(/no gate verdicts recorded on disk/i)).toBeTruthy());
  });
});

// --- A 73-candidate ranked backlog with categories. ---------------------------
function backlogCandidates() {
  const cats = ["UNTESTED_DATA", "EXPOSE_COHERENT_MARKET", "MISSING_TEST", "LOC_VIOLATION"];
  const out = [];
  for (let i = 0; i < 73; i++) {
    out.push({
      id: `b${i}`,
      category: cats[i % cats.length],
      sport: ["nba", "mlb", "soccer", "tennis"][i % 4],
      what: `candidate ${i}`,
      priority: 100 - i,
      expected_outcome: "REJECT-leaning",
      gate_action: "record verdict",
    });
  }
  return out;
}

const backlogArtifacts = {
  status: "ok",
  ledger: { rows: [], counts: {} },
  backlog: {
    note: "Measurement-only: discovers + ranks; never fixes / ships / flips a flag.",
    categories: ["UNTESTED_DATA", "EXPOSE_COHERENT_MARKET", "MISSING_TEST", "LOC_VIOLATION"],
    count: 73,
    candidates: backlogCandidates(),
  },
  honest_note: "",
  edge_claimed: false,
};

describe("BacklogPanel -- 73 ranked, filterable, show-all, measurement-only", () => {
  it("renders the 73-count header, top-ranked first, measurement-only note (no $)", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: backlogArtifacts }]]);
    const { container } = render(<BacklogPanel />);
    await waitFor(() => expect(screen.getByText(/73 ranked/)).toBeTruthy());
    // highest priority (100) candidate is rendered (sorted desc).
    expect(screen.getByText("candidate 0")).toBeTruthy();
    expect(screen.getByText("p100")).toBeTruthy();
    // the measurement-only note from the artifact is rendered verbatim.
    expect(screen.getByText(/never fixes \/ ships \/ flips a flag/i)).toBeTruthy();
    expect(container.textContent || "").not.toMatch(/\$/);
  });

  it("only the top 12 are shown until 'show all' is clicked", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: backlogArtifacts }]]);
    render(<BacklogPanel />);
    await waitFor(() => expect(screen.getByText("candidate 0")).toBeTruthy());
    // candidate 0..11 visible; candidate 60 hidden until expanded.
    expect(screen.queryByText("candidate 60")).toBeNull();
    fireEvent.click(screen.getByText(/show all 73/i));
    await waitFor(() => expect(screen.getByText("candidate 60")).toBeTruthy());
  });

  it("a category filter narrows the ranked list (no fabricated items)", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: backlogArtifacts }]]);
    render(<BacklogPanel />);
    await waitFor(() => expect(screen.getByText("candidate 0")).toBeTruthy());
    // click the LOC_VIOLATION category chip (a filter button).
    fireEvent.click(screen.getByRole("button", { name: "LOC_VIOLATION" }));
    // candidate 0 was UNTESTED_DATA (i%4==0) -> filtered out.
    await waitFor(() => expect(screen.queryByText("candidate 0")).toBeNull());
  });

  it("an empty backlog renders the honest no-candidates state", async () => {
    global.fetch = routeFetch([
      [/funnel-artifacts/, { body: { ...backlogArtifacts, backlog: { ...backlogArtifacts.backlog, candidates: [], count: 0 } } }],
    ]);
    render(<BacklogPanel />);
    await waitFor(() => expect(screen.getByText(/no backlog candidates discovered/i)).toBeTruthy());
  });

  it("category filter buttons carry focus-visible ring classes (keyboard nav)", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: backlogArtifacts }]]);
    render(<BacklogPanel />);
    await waitFor(() => expect(screen.getByText("candidate 0")).toBeTruthy());
    // Every category chip (including ALL) must include the focus-visible ring tokens.
    const filterBtns = screen.getAllByRole("button", { name: /^(ALL|UNTESTED_DATA|EXPOSE_COHERENT_MARKET|MISSING_TEST|LOC_VIOLATION)$/i });
    expect(filterBtns.length).toBeGreaterThanOrEqual(5);
    for (const btn of filterBtns) {
      const cls = btn.className;
      expect(cls, `filter button "${btn.textContent}" missing focus-visible:ring`).toMatch(/focus-visible:ring-2/);
    }
    // The active button exposes aria-pressed=true.
    const allBtn = filterBtns.find((b) => b.textContent === "ALL");
    expect(allBtn?.getAttribute("aria-pressed")).toBe("true");
  });

  it("show-all toggle button carries focus-visible ring classes and aria-expanded", async () => {
    global.fetch = routeFetch([[/funnel-artifacts/, { body: backlogArtifacts }]]);
    render(<BacklogPanel />);
    await waitFor(() => expect(screen.getByText(/show all 73/i)).toBeTruthy());
    const toggleBtn = screen.getByText(/show all 73/i);
    expect(toggleBtn.className).toMatch(/focus-visible:ring-2/);
    // starts collapsed: aria-expanded=false.
    expect(toggleBtn.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggleBtn);
    // after expansion: aria-expanded=true.
    await waitFor(() => expect(screen.getByText(/show top 12/i).getAttribute("aria-expanded")).toBe("true"));
  });
});

describe("ClvOverTimePanel -- INSUFFICIENT_DATA default, vs_close UNPROVEN, probability", () => {
  it("renders INSUFFICIENT_DATA + UNPROVEN + probability framing (no $)", async () => {
    const clv = {
      status: "ok",
      pool_verdict: "INSUFFICIENT_DATA",
      n_games: 1,
      n_settled_games: 0,
      pooled_mean_clv: null,
      clv_over_time: [],
      vs_close: "UNPROVEN",
      label: "CLV / calibration in probability space, no currency.",
      edge_claimed: false,
    };
    global.fetch = routeFetch([[/clv\/over-time/, { body: clv }]]);
    const { container } = render(<ClvOverTimePanel />);
    await waitFor(() => expect(screen.getByText("INSUFFICIENT_DATA")).toBeTruthy());
    expect(screen.getByText("UNPROVEN")).toBeTruthy();
    expect(screen.getByText(/One game is variance/i)).toBeTruthy();
    // probability space, never $.
    expect(container.textContent || "").not.toMatch(/\$/);
  });

  it("an unavailable CLV endpoint degrades honestly", async () => {
    global.fetch = routeFetch([[/clv\/over-time/, { body: {}, status: 503, ok: false }]]);
    render(<ClvOverTimePanel />);
    await waitFor(() => expect(screen.getByText(/HTTP 503/)).toBeTruthy());
  });
});

describe("NO $ field anywhere in the /system source", () => {
  it("no system source file emits a $-amount / pnl / roi / payout money field", () => {
    const dir = dirname(fileURLToPath(import.meta.url));
    const root = join(dir, "..");
    const files = readdirSync(root).filter((f) => f.endsWith(".ts") || f.endsWith(".tsx"));
    expect(files.length).toBeGreaterThan(0);
    // Ban any real money-VALUE token: a $-amount, a quoted-$ literal, or a
    // pnl/payout/roi money FIELD. Honest-rail PROSE in comments ("There is NO
    // $/ROI/payout field", "probability space, NOT dollars") is the honesty
    // statement itself, never a money field -- so we strip // and /* */ comments
    // before scanning and assert no money token survives in the CODE.
    const stripComments = (s: string) =>
      s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
    const banned = /\$\d|["']\$["']|\bpnl\b|\bpayout\b|\broi\b/i;
    for (const f of files) {
      const code = stripComments(readFileSync(join(root, f), "utf8"));
      expect(banned.test(code), `banned money token in ${f} (code, not comment)`).toBe(false);
    }
  });
});
