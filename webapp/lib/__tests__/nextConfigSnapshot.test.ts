// nextConfigSnapshot.test.ts -- next.config.mjs in NEXT_PUBLIC_DATA_MODE=snapshot refuses
// an empty export: with no baked files or a manifest without games/bet_ids, the
// NEXT_PUBLIC_SNAPSHOT_* lists would stay unset and every game/bet link would 404.
import { describe, expect, it } from "vitest";
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CONFIG = join(process.cwd(), "next.config.mjs");

/** Copy next.config.mjs beside a public/demo-data holding the given files, load it in snapshot mode. */
function load(files: Record<string, string>, mode = "snapshot"): { ok: boolean; out: string } {
  const dir = mkdtempSync(join(tmpdir(), "next-config-"));
  mkdirSync(join(dir, "public", "demo-data"), { recursive: true });
  copyFileSync(CONFIG, join(dir, "next.config.mjs"));
  for (const [name, body] of Object.entries(files)) writeFileSync(join(dir, "public", "demo-data", name), body);
  const script = "import('./next.config.mjs').then((m) => console.log(JSON.stringify(m.default.env)))";
  try {
    const out = execFileSync(process.execPath, ["--input-type=module", "-e", script], {
      cwd: dir, env: { ...process.env, NEXT_PUBLIC_DATA_MODE: mode, GITHUB_SHA: "abcdef1234567890" }, encoding: "utf-8", stdio: "pipe",
    });
    return { ok: true, out };
  } catch (e) {
    return { ok: false, out: String((e as { stderr?: string }).stderr ?? e) };
  }
}

const manifest = JSON.stringify({ games: [{ sport: "mlb", game_id: "G1" }], bet_ids: ["b1"] });

describe("next.config.mjs snapshot guard", () => {
  it("inlines the file, game and bet lists plus the build id from a non-empty export", () => {
    const r = load({ "manifest.json": manifest, "api_report_nba.json": "{}" });
    expect(r.ok, r.out).toBe(true);
    const env = JSON.parse(r.out);
    expect(JSON.parse(env.NEXT_PUBLIC_SNAPSHOT_FILES)).toEqual(["api_report_nba.json", "manifest.json"]);
    expect(JSON.parse(env.NEXT_PUBLIC_SNAPSHOT_GAMES)).toEqual(["mlb/G1"]);
    expect(JSON.parse(env.NEXT_PUBLIC_SNAPSHOT_BETS)).toEqual(["b1"]);
    expect(env.NEXT_PUBLIC_BUILD_ID).toBe("abcdef123456");
  });

  it("throws when demo-data is empty, the manifest is missing, or it lists no games or bet_ids", () => {
    expect(load({}).out).toMatch(/holds no baked \*\.json/);
    expect(load({ "api_report_nba.json": "{}" }).out).toMatch(/manifest\.json is missing or invalid/);
    expect(load({ "manifest.json": JSON.stringify({ games: [], bet_ids: ["b1"] }) }).out).toMatch(/lists no games/);
    expect(load({ "manifest.json": JSON.stringify({ games: [{ sport: "mlb", game_id: "G1" }] }) }).out).toMatch(/lists no bet_ids/);
  });

  it("stays silent outside snapshot mode and still carries a build id", () => {
    const r = load({}, "");
    expect(r.ok, r.out).toBe(true);
    expect(JSON.parse(r.out)).toEqual({ NEXT_PUBLIC_BUILD_ID: "abcdef123456" });
  });
});
