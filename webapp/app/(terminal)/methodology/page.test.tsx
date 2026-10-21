import { describe, it, expect } from "vitest";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { BANNED_COPY, RETRACTED_TOKENS } from "@/lib/packetVerdicts";
import { loadChecks } from "@/components/desk/deskExtras.server";
import { REPO_URL, REPO_BRANCH } from "@/components/evidence/kit";
import { METHOD_ENTRIES } from "@/components/methodology/MethodEntries";
import MethodologyPage from "./page";

// Methodology (/methodology/): the first paragraph says what the page is, the packet verdict
// (NBA "cannot tell", never the retired "matches the close within noise" reading) and how to
// check; the retracted figures appear only inside the do-not-claim rail; every link resolves.

const WEBAPP = process.cwd();
const REPO = join(WEBAPP, "..");
const BLOB = `${REPO_URL}/blob/${REPO_BRANCH}/`;

/** Route -> page.tsx for every page under app/, route groups "(x)" dropped. */
function routes(): Map<string, string> {
  const out = new Map<string, string>();
  const walk = (dir: string, segs: string[]) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full, /^\(.*\)$/.test(name) ? segs : [...segs, name]);
      else if (name === "page.tsx") out.set(`/${segs.join("/")}`, full);
    }
  };
  walk(join(WEBAPP, "app"), []);
  return out;
}

describe("Methodology page", () => {
  it("leads with what the page is, the packet verdict and how to check", () => {
    render(<MethodologyPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent?.trim()).toBe("How every number here is checked");
    const lede = h1.nextElementSibling!;
    expect(lede.textContent).toMatch(/how a number earns a place on this site/);
    expect(lede.textContent).toMatch(/on MLB\s+moneyline and soccer over\/under 2\.5; on NBA moneyline it cannot tell \(interval\s+includes zero; underpowered\)/);
    expect(lede.textContent).toMatch(/the MLB verdict survived two\s+repairs, the soccer verdict has not been re-established/);
    expect(lede.textContent).toMatch(/run the one-command harness below/);
    expect(lede.textContent).not.toMatch(/within noise/i);
    expect(screen.getByRole("button", { name: "devigged close" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "retraction record" }))
      .toHaveAttribute("href", expect.stringMatching(/^\/evidence\/retractions\/?$/));
  });

  it("has the seven method entries plus the retraction and not-claimed entries, each with an artifact and an as-of", () => {
    const { container } = render(<MethodologyPage />);
    expect(METHOD_ENTRIES.map((e) => e.id)).toEqual(
      ["devig", "walk-forward", "truncation", "two-corpus", "paired", "in-game", "forward"]);
    for (const e of METHOD_ENTRIES) {
      const el = container.querySelector(`#${e.id}`)!;
      expect(el.textContent).toMatch(/artifact:.*\| as of /);
      expect(el.querySelectorAll("a").length).toBeGreaterThan(0);
    }
    for (const id of ["retractions", "not-claimed"]) {
      const el = container.querySelector(`[data-entry="${id}"]`)!;
      expect(el.textContent).toMatch(/artifact:.*\| as of /);
    }
    expect(container.querySelector("#paired")!.textContent).toMatch(/n = 372.*0\.0152.*cannot tell \(interval includes zero; underpowered\)/s);
    expect(container.querySelector("#walk-forward")!.textContent).toMatch(/48.*hours.*3.*days/s);
    expect(container.querySelector("#forward")!.textContent).toMatch(/30.*games/s);
    expect(container.querySelector('[data-entry="not-claimed"]')!.textContent)
      .toMatch(/forward track record, or execution quality; simulated fill counts are counts, not results/);
  });

  it("reads the same check_all report as the home page, with its as-of", () => {
    render(<MethodologyPage />);
    const c = loadChecks();
    const el = screen.getByTestId("self-check");
    expect(el.textContent).not.toMatch(/96\/96/);
    if (!c) return expect(el.textContent).toMatch(/not present/);
    expect(el.textContent).toBe(
      `${c.pass} of ${c.total} pass, ${c.noCheck} have no self-check, ${c.other} FAIL/other (report as of ${c.asOf})`);
  });

  it("links only repo paths that exist and internal routes that are real pages, not redirect stubs", () => {
    const { container } = render(<MethodologyPage />);
    const pages = routes();
    const hrefs = [...container.querySelectorAll("a[href]")].map((a) => a.getAttribute("href")!);
    expect(hrefs.length).toBeGreaterThan(20);
    for (const href of hrefs) {
      if (href.startsWith(BLOB)) {
        const rel = decodeURIComponent(href.slice(BLOB.length).split("#")[0]);
        expect(existsSync(join(REPO, rel)), `missing repo path ${rel}`).toBe(true);
      } else if (href.startsWith("/") && !href.startsWith("/data/")) {
        const route = href.split("#")[0].replace(/\/$/, "") || "/";
        const page = pages.get(route);
        expect(page, `no page for ${href}`).toBeTruthy();
        expect(readFileSync(page!, "utf-8"), `${href} is a redirect stub`).not.toMatch(/RedirectStub/);
      }
    }
  });

  it("prints retracted figures only inside the do-not-claim rail, and no banned copy outside it", () => {
    const { container } = render(<MethodologyPage />);
    const rail = container.querySelector("#do-not-claim")!;
    for (const t of RETRACTED_TOKENS) expect(rail.textContent).toContain(t);
    rail.remove();
    // The no-edge banner is the one place outside the rail that negates the banned words.
    container.querySelector('[role="note"]')!.remove();
    const txt = container.textContent ?? "";
    for (const t of RETRACTED_TOKENS) expect(txt).not.toContain(t);
    expect(BANNED_COPY.test(txt)).toBe(false);
  });

  it("renders the gate ledger token among the badges in its own style, with the one-line legend", () => {
    const { container } = render(<MethodologyPage />);
    const el = container.querySelector('#verified [data-gate="VALIDATION_PENDING"]');
    expect(el).toHaveClass("ev-gate");
    expect(el).toHaveTextContent("not yet validated");
    expect(el?.getAttribute("title")).toBe("VALIDATION_PENDING: not yet validated. gate ledger status, not a packet verdict.");
    expect(container.querySelectorAll("[data-gate]").length).toBe(1); // the packet badges keep their own style
    const legend = container.querySelector('#verified [data-testid="gate-status-legend"]');
    expect(legend?.textContent).toBe("Gate ledger statuses, not packet verdicts: VALIDATION_PENDING = not yet validated.");
  });
});
