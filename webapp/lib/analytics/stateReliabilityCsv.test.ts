import { describe, expect, it, vi } from "vitest";
import { loadStateReliability } from "./stateReliability.server";
import type { StateReliabilityRow, StateReliabilitySport } from "./stateReliability";
import { buildStateReliabilityCSV, exportStateReliabilityCSV } from "./stateReliabilityCsv";

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

const sampleRow: StateReliabilityRow = {
  sport: "sample", source: "market", timeBucket: "late", probabilityBucket: ".2-.4",
  n: 0, meanP: 0, meanY: 0, calibrationError: 0,
};
const sampleSport: StateReliabilitySport = {
  sport: "sample", artifactDate: null, nForecastObservations: 0, nSkippedNoStateField: 0,
  nCells: 1, rows: [sampleRow], timeBuckets: ["late"], probabilityBuckets: [".2-.4"],
};

describe("state reliability CSV", () => {
  it("exports the published MLB row with raw source error and distinct derived gaps", () => {
    const mlb = loadStateReliability().find(sport => sport.sport === "mlb")!;
    const row = mlb.rows.find(item => item.n === 617 && item.timeBucket === "late(inn7+)" && item.source === "model")!;
    const table = parseCSV(buildStateReliabilityCSV(mlb, [row]));
    expect(table).toHaveLength(2);
    expect(table[1].slice(0, 10)).toEqual(["mlb", "model", "late(inn7+)", ".2-.4", "617", "0.262", "0.0843", "0.1778", "-17.77", "17.78"]);
    expect(table[1].slice(10)).toEqual([mlb.artifactDate, "", "public/data/showcase/state_conditioned_calibration.json",
      "forecast observations, not independent games; unpaired source populations; observation dates not published; absent cells omitted"]);
  });

  it("retains the supplied filtered order without mutating source rows or fabricating dates", () => {
    const second = { ...sampleRow, source: "model" as const, n: 10, meanP: .2, meanY: .1, calibrationError: .11 };
    const selected = [second, sampleRow];
    const original = JSON.stringify(selected);
    const table = parseCSV(buildStateReliabilityCSV(sampleSport, selected));
    expect(table[0]).toContain("n (forecast observations)");
    expect(table.slice(1).map(record => record[1])).toEqual(["model", "market"]);
    expect(table[1].slice(4, 10)).toEqual(["10", "0.2", "0.1", "0.11", "-10", "11"]);
    expect(buildStateReliabilityCSV(sampleSport, selected)).toContain(',-10,11,');
    expect(table[2].slice(4, 10)).toEqual(["0", "0", "0", "0", "0", "0"]);
    expect(table[1][10]).toBe("");
    expect(table[1][11]).toBe("");
    expect(JSON.stringify(selected)).toBe(original);
  });

  it("quotes commas, quotes and newlines and guards formula-like text cells", () => {
    const row = { ...sampleRow, sport: ' \n=HYPERLINK("x,y")', timeBucket: '+late\nnext', probabilityBucket: '  @SUM("a,b")' };
    const table = parseCSV(buildStateReliabilityCSV({ ...sampleSport, artifactDate: "\n-tomorrow" }, [row]));
    expect(table[1].slice(0, 4)).toEqual(['\' \n=HYPERLINK("x,y")', "market", "'+late\nnext", '\'  @SUM("a,b")']);
    expect(table[1][10]).toBe("'\n-tomorrow");
  });

  it("downloads UTF-8 CSV with a safe sport name and revokes the object URL", () => {
    let blob: Blob | undefined;
    let cleanup: (() => void) | undefined;
    const originalCreate = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const originalRevoke = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const create = vi.fn((value: Blob) => { blob = value; return "blob:state-csv"; });
    const revoke = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe("courtvision-state-reliability-soccer-intl.csv");
    });
    const timeout = vi.spyOn(globalThis, "setTimeout").mockImplementation(((handler: TimerHandler) => {
      if (typeof handler === "function") cleanup = handler as () => void;
      return 1;
    }) as typeof setTimeout);
    try {
      exportStateReliabilityCSV({ ...sampleSport, sport: "Soccer Intl" }, [sampleRow]);
      expect(create).toHaveBeenCalledOnce();
      expect(blob?.type).toBe("text/csv;charset=utf-8");
      expect(click).toHaveBeenCalledOnce();
      cleanup?.();
      expect(revoke).toHaveBeenCalledWith("blob:state-csv");
    } finally {
      timeout.mockRestore(); click.mockRestore();
      if (originalCreate) Object.defineProperty(URL, "createObjectURL", originalCreate); else delete (URL as Partial<typeof URL>).createObjectURL;
      if (originalRevoke) Object.defineProperty(URL, "revokeObjectURL", originalRevoke); else delete (URL as Partial<typeof URL>).revokeObjectURL;
    }
  });
});
