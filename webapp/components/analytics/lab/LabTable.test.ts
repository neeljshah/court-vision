import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { LabDataset } from "@/lib/analytics/labTypes";
import type { ResearchAnalysis, ResearchRow } from "@/lib/analytics/researchTypes";
import { buildLabCSV, exportLabCSV, LabTable } from "./LabTable";

function parseCSV(csv: string): string[][] {
  const records: string[][] = [];
  let record: string[] = [], field = "", quoted = false;
  for (let index = 0; index < csv.length; index += 1) {
    const character = csv[index];
    if (quoted && character === '"' && csv[index + 1] === '"') { field += '"'; index += 1; }
    else if (character === '"') quoted = !quoted;
    else if (!quoted && character === ",") { record.push(field); field = ""; }
    else if (!quoted && character === "\r" && csv[index + 1] === "\n") {
      record.push(field); records.push(record); record = []; field = ""; index += 1;
    } else field += character;
  }
  record.push(field); records.push(record);
  return records;
}

const provenanceHeaders = ["Analysis as of", "Sources (JSON)", "Fields (JSON)", "Bindings (JSON)", "Row source paths (JSON)", "Row binding values (JSON)", "Row windows (JSON)", "Row definition (JSON)"];
const basicDataset: LabDataset = {
  id: "example", title: "Example", sport: "all", category: "Example", source: "snapshot",
  description: "", scope: "Historical cohort", caveat: "Subset only", status: "Descriptive",
  fields: [{ key: "half", label: "Half life", unit: "hours" }, { key: "rate", label: "Rate", unit: "percent" }], rows: [],
};
const researchDataset: ResearchAnalysis = {
  ...basicDataset,
  fields: [{ key: "score", label: "Score, raw", unit: "number", digits: 3, sourceId: "source-a" }, { key: "rate", label: "Rate", unit: "percent" }],
  rows: [], formula: "score = numerator / denominator", interpretation: "Test", references: [], novelty: "Derived analysis",
  asOf: "2026-09-20T12:00:00Z",
  sources: [
    { id: "source-a", asOf: "2026-09-19", fields: ["score"], rowWindows: { score: ["2024-25", "2025-26"] } },
    { id: "source-b", asOf: "2026-09-18", fields: ["rate"], rowWindows: { rate: ["career"] } },
  ],
  bindings: [{ operand: "numerator", sourcePath: "cells[].numerator", valueKey: "numerator", label: "Numerator" }],
};

describe("buildLabCSV", () => {
  it("keeps the basic export byte-compatible, including raw null, zero, and negative measurements", () => {
    const csv = buildLabCSV(basicDataset, [
      { id: "t", label: '=HYPERLINK("bad")', group: "Tennis", values: { half: null, rate: 0.107 }, note: "Censored: >6 hours" },
      { id: "zero", label: "True zero", group: "Other", values: { half: 0, rate: -0.02 } },
    ]);
    expect(csv).toBe('"Entity","Group","Half life (hours; raw value)","Rate (percent; raw value)","Row note","Source","Scope","Caveat"\r\n"\'=HYPERLINK(""bad"")","Tennis",,0.107,"Censored: >6 hours","snapshot","Historical cohort","Subset only"\r\n"True zero","Other",0,-0.02,"","snapshot","Historical cohort","Subset only"');
    expect(csv).not.toContain("Analysis as of");
  });

  it("appends exact research provenance columns and preserves each row's own context", () => {
    const rows: ResearchRow[] = [
      { id: "one", label: "Quoted, row\none", group: "A", values: { score: 0, rate: -0.25 }, sourcePaths: ["cells[0].score", '=FORMULA("nested")'], bindingValues: { numerator: null, denominator: 0 }, windows: { score: "2024-25\nregular" }, definition: { population: "starters, only", threshold: 0 } },
      { id: "two", label: "Second", group: "B", values: { score: null, rate: 0 }, sourcePaths: ["cells[1].rate"], bindingValues: { numerator: 9 }, windows: { rate: "career, all" }, definition: { observationWindow: "career" } },
    ];
    const table = parseCSV(buildLabCSV(researchDataset, rows));
    expect(table[0].slice(-8)).toEqual(provenanceHeaders);
    expect(table[1].slice(0, 4)).toEqual(["Quoted, row\none", "A", "0", "-0.25"]);
    expect(JSON.parse(table[1].at(-7)!)).toEqual(researchDataset.sources);
    expect(JSON.parse(table[1].at(-6)!)).toEqual(researchDataset.fields);
    expect(JSON.parse(table[1].at(-5)!)).toEqual(researchDataset.bindings);
    expect(JSON.parse(table[1].at(-4)!)).toEqual(rows[0].sourcePaths);
    expect(JSON.parse(table[1].at(-3)!)).toEqual({ numerator: null, denominator: 0 });
    expect(JSON.parse(table[1].at(-2)!)).toEqual(rows[0].windows);
    expect(JSON.parse(table[1].at(-1)!)).toEqual(rows[0].definition);
    expect(JSON.parse(table[2].at(-4)!)).toEqual(rows[1].sourcePaths);
    expect(JSON.parse(table[2].at(-3)!)).toEqual(rows[1].bindingValues);
    expect(JSON.parse(table[2].at(-2)!)).toEqual(rows[1].windows);
    expect(JSON.parse(table[2].at(-1)!)).toEqual(rows[1].definition);
    expect(table[1].at(-8)).toBe(researchDataset.asOf);
  });

  it("distinguishes source dates and source row windows without inventing fallback sources", () => {
    const table = parseCSV(buildLabCSV(researchDataset, [{ id: "x", label: "X", group: "G", values: { score: 1, rate: null } }]));
    const sources = JSON.parse(table[1].at(-7)!);
    expect(sources).toEqual([
      { id: "source-a", asOf: "2026-09-19", fields: ["score"], rowWindows: { score: ["2024-25", "2025-26"] } },
      { id: "source-b", asOf: "2026-09-18", fields: ["rate"], rowWindows: { rate: ["career"] } },
    ]);
    expect(table[1].slice(-4)).toEqual(["", "", "", ""]);
    expect(sources).toHaveLength(2);
  });

  it("adds headers for row-only provenance and retains explicit empty containers and zero values", () => {
    const rowOnly = { ...basicDataset, rows: [] } as unknown as ResearchAnalysis;
    const table = parseCSV(buildLabCSV(rowOnly, [{ id: "x", label: "X", group: "G", values: { half: 0, rate: 0 }, sourcePaths: [], bindingValues: { n: 0, missing: null }, windows: {}, definition: { threshold: 0 } }]));
    expect(table[0].slice(-8)).toEqual(provenanceHeaders);
    expect(table[1].slice(-8)).toEqual(["", "", JSON.stringify(basicDataset.fields), "", "[]", '{"n":0,"missing":null}', "{}", '{"threshold":0}']);
    expect(table[1].slice(0, 4)).toEqual(["X", "G", "0", "0"]);
  });

  it("exports provenance headers without rows and lets a definition alone trigger them", () => {
    const headerOnly = parseCSV(buildLabCSV(researchDataset, []));
    expect(headerOnly).toHaveLength(1);
    expect(headerOnly[0].slice(-8)).toEqual(provenanceHeaders);
    const definitionOnly = parseCSV(buildLabCSV(basicDataset, [{ id: "x", label: "X", group: "G", values: { half: 1, rate: null }, definition: { season: "2025-26" } }]));
    expect(definitionOnly[0].slice(-8)).toEqual(provenanceHeaders);
    expect(definitionOnly[1].slice(-8)).toEqual(["", "", JSON.stringify(basicDataset.fields), "", "", "", "", '{"season":"2025-26"}']);
  });

  it("round-trips commas, quotes, newlines, and formula-like strings inside provenance JSON", () => {
    const dataset = { ...researchDataset, sources: [{ id: '=HYPERLINK("x,y")\nnext', asOf: "+tomorrow", fields: [] }] };
    const table = parseCSV(buildLabCSV(dataset, [{ id: "x", label: "X", group: "G", values: { score: 1, rate: 0 }, bindingValues: { text: '@SUM("a,b")\nnext' } }]));
    expect(JSON.parse(table[1].at(-7)!)).toEqual(dataset.sources);
    expect(JSON.parse(table[1].at(-3)!)).toEqual({ text: '@SUM("a,b")\nnext' });
    expect(table[1].at(-7)?.startsWith("'")).toBe(false);
  });

  it("downloads the generated provenance CSV with the expected name and MIME type", async () => {
    let blob: Blob | undefined, download = "", cleanup: (() => void) | undefined;
    const originalCreate = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const originalRevoke = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const createObjectURL = vi.fn((value: Blob) => { blob = value; return "blob:lab-csv"; });
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { download = this.download; });
    const timeout = vi.spyOn(globalThis, "setTimeout").mockImplementation(((handler: TimerHandler) => { if (typeof handler === "function") cleanup = handler as () => void; return 1; }) as typeof setTimeout);
    try {
      exportLabCSV(researchDataset, [{ id: "x", label: "X", group: "G", values: { score: 1, rate: 0 }, sourcePaths: ["cells[0].score"] }]);
      expect(createObjectURL).toHaveBeenCalledOnce();
      expect(blob?.type).toBe("text/csv;charset=utf-8");
      expect(download).toBe("courtvision-example.csv");
      const body = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(reader.error); reader.readAsText(blob!);
      });
      expect(parseCSV(body)[1].at(-4)).toBe('["cells[0].score"]');
      cleanup?.();
      expect(revokeObjectURL).toHaveBeenCalledWith("blob:lab-csv");
    } finally {
      timeout.mockRestore(); click.mockRestore();
      if (originalCreate) Object.defineProperty(URL, "createObjectURL", originalCreate); else delete (URL as Partial<typeof URL>).createObjectURL;
      if (originalRevoke) Object.defineProperty(URL, "revokeObjectURL", originalRevoke); else delete (URL as Partial<typeof URL>).revokeObjectURL;
    }
  });
});

it("links entity labels when a published entity route is available and retains inspection", () => {
  const onSelect = vi.fn();
  render(createElement(LabTable, { dataset: basicDataset, rows: [{ id: "entity", label: "Entity One", group: "Test", values: { half: 1 }, href: "/analytics/players/nba_players/entity_one" }], onSelect }));
  expect(screen.getByRole("link", { name: "Entity One" })).toHaveAttribute("href", "/analytics/players/nba_players/entity_one");
  screen.getByRole("button", { name: "Inspect Entity One" }).click();
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "entity" }));
});
