import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { verifyExport } from "./verify-analytics-export.mjs";

const out = resolve(fileURLToPath(new URL(".", import.meta.url)), "..", "out");

test("full export scan covers every analytics page and indexed destination", () => {
  const result = verifyExport(out);
  assert.equal(result.failures.length, 0, result.failures.join("\n"));
  assert.ok(result.htmlCount >= 1000);
  assert.ok(result.indexedCount >= 1000);
  assert.ok(result.referenceCount > result.htmlCount);
});

test("fixture scan catches nested missing routes, base path, and malformed links", () => {
  const fixture = mkdtempSync(resolve(tmpdir(), "cv-analytics-export-"));
  try {
    mkdirSync(resolve(fixture, "analytics"), { recursive: true });
    writeFileSync(resolve(fixture, "analytics", "index.html"), '<a href="/analytics/ok/">base</a><a href="/court-vision/analytics/nested/missing/">nested</a><a href="http://[bad">bad</a>');
    const records = Array.from({ length: 33 }, (_, index) => ({ id: `research-fixture-${index}`, href: "/analytics/nested/missing" }));
    writeFileSync(resolve(fixture, "analytics", "search-index.json"), JSON.stringify({ records }));
    const result = verifyExport(fixture, "/court-vision");
    assert.ok(result.failures.some((failure) => failure.includes("missing basePath for /analytics/ok/")));
    assert.ok(result.failures.some((failure) => failure.includes("references missing route or asset /analytics/nested/missing/")));
    assert.ok(result.failures.some((failure) => failure.includes("has an invalid internal reference")));
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

function redirectFixture() {
  const fixture = mkdtempSync(resolve(tmpdir(), "cv-analytics-redirect-"));
  const routes = ["/", "/evidence/retractions/", "/analytics/", "/analytics/findings/retraction/", "/analytics/ask/", "/analytics/lab/", "/analytics/compare/", "/analytics/evidence/", "/analytics/findings/ingame-join-integrity/", "/analytics/browse/", "/analytics/state-reliability/", "/analytics/pitch-sequencing/", "/analytics/count-context/", "/analytics/score-decomposition/", "/analytics/observation-dependence/", "/analytics/residual-anatomy/", "/analytics/blowout-timing/", "/analytics/state-contrasts/", "/analytics/cross-sport-comparability/", "/analytics/papers/", "/analytics/research-fixture/"];
  const writeRoute = (route, html = "<p>Published page</p>") => {
    mkdirSync(resolve(fixture, `.${route}`), { recursive: true });
    writeFileSync(resolve(fixture, `.${route}`, "index.html"), html);
  };
  for (const route of routes) writeRoute(route);
  const stub = destination => `<link rel="canonical" href="https://neeljshah.github.io/court-vision${destination}"><meta http-equiv="refresh" content="0; url=/court-vision${destination}"><a href="/court-vision${destination}">Moved</a>`;
  writeRoute("/analytics/", stub("/"));
  writeRoute("/analytics/findings/retraction/", stub("/evidence/retractions/"));
  const locations = routes.filter(route => !["/analytics/", "/analytics/findings/retraction/"].includes(route));
  const writeSitemap = included => writeFileSync(resolve(fixture, "sitemap.xml"), `<urlset>${included.map(route => `<url><loc>https://neeljshah.github.io/court-vision${route}</loc></url>`).join("")}</urlset>`);
  writeSitemap(locations);
  const records = Array.from({ length: 33 }, (_, index) => ({ id: `research-fixture-${index}`, href: "/analytics/research-fixture" }));
  records.push({ id: "retraction", href: "/analytics/findings/retraction" });
  writeFileSync(resolve(fixture, "analytics", "search-index.json"), JSON.stringify({ records }));
  return { fixture, writeRoute, stub, locations, writeSitemap };
}

test("retired redirect fixtures accept only the two mapped destinations", () => {
  const { fixture } = redirectFixture();
  try {
    assert.deepEqual(verifyExport(fixture, "/court-vision").failures, []);
  } finally { rmSync(fixture, { recursive: true, force: true }); }
});

test("retired redirect fixtures do not exempt arbitrary canonical routes from the sitemap", () => {
  const { fixture, writeRoute, stub, locations, writeSitemap } = redirectFixture();
  try {
    writeRoute("/analytics/lab/", stub("/"));
    writeSitemap(locations.filter(route => route !== "/analytics/lab/"));
    assert.ok(verifyExport(fixture, "/court-vision").failures.includes("sitemap is missing /analytics/lab/"));
  } finally { rmSync(fixture, { recursive: true, force: true }); }
});

for (const [route, destination] of [["/analytics/", "/"], ["/analytics/findings/retraction/", "/evidence/retractions/"]]) {
  for (const problem of ["missing target", "missing sitemap target", "wrong canonical", "wrong refresh", "missing original route"]) {
    test(`retired redirect fixtures reject ${problem} for ${route}`, () => {
      const { fixture, writeRoute, stub, locations, writeSitemap } = redirectFixture();
      try {
        if (problem === "missing target") rmSync(resolve(fixture, `.${destination}`, "index.html"));
        if (problem === "missing sitemap target") writeSitemap(locations.filter(item => item !== destination));
        if (problem === "wrong canonical") writeRoute(route, stub(destination).replace(`href="https://neeljshah.github.io/court-vision${destination}"`, 'href="https://neeljshah.github.io/court-vision/analytics/lab/"'));
        if (problem === "wrong refresh") writeRoute(route, stub(destination).replace(`url=/court-vision${destination}"`, 'url=/court-vision/analytics/lab/"'));
        if (problem === "missing original route") rmSync(resolve(fixture, `.${route}`, "index.html"));
        const failures = verifyExport(fixture, "/court-vision").failures;
        const expected = problem === "missing target" ? `retired route ${route} targets missing route ${destination}`
          : problem === "missing sitemap target" ? `sitemap is missing ${destination}`
          : problem === "missing original route" ? `retired route missing ${route}`
          : `retired route ${route} ${problem.slice(6)} must target ${destination}`;
        assert.ok(failures.includes(expected), failures.join("\n"));
      } finally { rmSync(fixture, { recursive: true, force: true }); }
    });
  }
}
