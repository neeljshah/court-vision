import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ExplainersIndexPage from "./page";

type Essay = { slug: string };

function readEssays(): Essay[] {
  const raw = readFileSync(
    join(process.cwd(), "public", "data", "explainers", "explainers.json"),
    "utf8"
  );
  return (JSON.parse(raw) as { essays: Essay[] }).essays;
}

describe("ExplainersIndexPage", () => {
  it("lists every committed explainer", () => {
    const essays = readEssays();
    const { container } = render(<ExplainersIndexPage />);
    expect(container.querySelectorAll('a[href^="/analytics/explainers/"]')).toHaveLength(
      essays.length
    );
  });
});
