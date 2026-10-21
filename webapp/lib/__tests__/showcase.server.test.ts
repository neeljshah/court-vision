// showcase.server.test.ts -- an unstaged artifact is pending (null) but a corrupt one
// throws, and the sample manifest / static module registry are development-only.
import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { listModules, loadArtifact, loadManifest } from "../showcase.server";

function dir(files: Record<string, string> = {}): string {
  const d = mkdtempSync(join(tmpdir(), "showcase-"));
  for (const [name, body] of Object.entries(files)) writeFileSync(join(d, name), body);
  return d;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("loadArtifact", () => {
  it("returns null for an unstaged artifact and throws for a corrupt one", () => {
    const d = dir({ "bad.json": "{nope", "good.json": '{"edge_claimed":false,"n":3}' });
    expect(loadArtifact("absent", d)).toBeNull();
    expect(loadArtifact("../../etc/passwd", d)).toBeNull();
    expect(loadArtifact("good", d)).toEqual({ edge_claimed: false, n: 3 });
    expect(() => loadArtifact("bad", d)).toThrow(/bad\.json is not valid JSON/);
    expect(loadArtifact("cross_sport_scoreboard")).not.toBeNull();
  });
});

describe("manifest fallbacks", () => {
  it("serve the sample manifest and the static registry only outside production", async () => {
    const empty = dir();
    const sample = dir({ "manifest-sample.json": '{"modules":[{"id":"x","label":"X"}]}' });
    expect(loadManifest(empty)).toBeNull();
    expect(listModules(empty).length).toBeGreaterThan(0); // NODE_ENV=test: the static registry
    expect(loadManifest(sample)?.modules).toEqual([{ id: "x", label: "X" }]);

    vi.stubEnv("NODE_ENV", "production");
    vi.resetModules();
    const prod = await import("../showcase.server");
    expect(prod.loadManifest(sample)).toBeNull();
    expect(() => prod.listModules(empty)).toThrow(/site_manifest\.json is missing or lists no modules; the static registry is development-only/);
    expect(prod.listModules().length).toBeGreaterThan(0); // the real staged manifest still serves
  });
});
