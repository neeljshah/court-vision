import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

test("paper evidence CLI validates the committed corpus", () => {
  const result = spawnSync(process.execPath, ["scripts/check-paper-evidence.mjs"], {
    cwd: process.cwd(),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
});
