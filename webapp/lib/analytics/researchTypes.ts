import type { LabDataset } from "./labTypes";

export type ResearchReference = { title: string; url: string };
export type ResearchRow = LabDataset["rows"][number] & { sourcePaths?: string[] };
export type ResearchAnalysis = Omit<LabDataset, "rows"> & {
  rows: ResearchRow[];
  formula: string;
  interpretation: string;
  references: ResearchReference[];
  asOf?: string;
  novelty: "Derived analysis" | "Experimental formulation";
};
