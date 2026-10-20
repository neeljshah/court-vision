import { describe, expect, it } from "vitest";
import sitemap from "./sitemap";
import { REDIRECTS, resolveRedirect } from "@/lib/redirects";

describe("sitemap", () => {
  const paths = sitemap().map((u) => u.url.replace(/^https?:\/\/[^/]+/, "").replace(/^\/court-vision/, ""));

  it("lists every kept section root", () => {
    for (const p of ["/", "/games/", "/desk/", "/analytics/calibration/", "/analytics/papers/", "/evidence/", "/evidence/retractions/", "/about/"]) {
      expect(paths).toContain(p);
    }
  });

  it("lists no redirect stub and no retired family", () => {
    for (const p of paths) expect(resolveRedirect(p), p).toBeNull();
    for (const stub of Object.keys(REDIRECTS)) expect(paths).not.toContain(stub);
    expect(new Set(paths).size).toBe(paths.length);
  });
});
