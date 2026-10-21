import { describe, expect, it } from "vitest";
import sitemap from "./sitemap";
import { REDIRECTS, resolveRedirect } from "@/lib/redirects";

describe("sitemap", () => {
  const paths = sitemap().map((u) => u.url.replace(/^https?:\/\/[^/]+/, "").replace(/^\/court-vision/, ""));

  it("lists every kept section root", () => {
    for (const p of ["/", "/games/", "/desk/", "/analytics/calibration/", "/analytics/papers/", "/analytics/evidence/", "/evidence/", "/evidence/retractions/", "/about/", "/graveyard/", "/desk/execution/", "/desk/ingame/", "/desk/model-cards/"]) {
      expect(paths).toContain(p);
    }
  });

  it("lists the dynamic families, including /paper/<fill> but not the /paper stub", () => {
    for (const re of [/^\/evidence\/[^/]+\/$/, /^\/paper\/[^/]+\/$/, /^\/receipts\/\d+\/$/, /^\/games\/[^/]+\/[^/]+\/$/, /^\/analytics\/explainers\/[^/]+\/$/]) {
      expect(paths.some((p) => re.test(p)), String(re)).toBe(true);
    }
    expect(paths).not.toContain("/paper/");
    expect(paths.some((p) => p.includes("/none/"))).toBe(false);
  });

  it("lists no redirect stub and no retired family", () => {
    for (const p of paths.filter((x) => !x.startsWith("/paper/"))) expect(resolveRedirect(p), p).toBeNull();
    for (const stub of Object.keys(REDIRECTS)) expect(paths).not.toContain(stub);
    expect(new Set(paths).size).toBe(paths.length);
  });
});
