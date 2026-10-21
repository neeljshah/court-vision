// The retired "matching the close within noise" reading must not survive in page copy under app/ or
// components/ (the packet word MATCHES_CLOSE stays only as a VerdictLabel table cell).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const RETIRED = /matching the devigged close within noise|the honest,? defensible win is matching|MATCH the efficient close/i;

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return sources(p);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [p] : [];
  });
}

describe("retired MATCH copy", () => {
  it("no source file under app/ or components/ carries it", () => {
    const hits = ["app", "components"].flatMap((d) => sources(join(process.cwd(), d)))
      .filter((p) => RETIRED.test(readFileSync(p, "utf8").replace(/\s+/g, " ")));
    expect(hits).toEqual([]);
  });
});
