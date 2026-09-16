import type { LabDataset } from "./labTypes";

export type ResearchReference = { title: string; url: string };
export type ResearchSource = { id: string; asOf: string };
export type ResearchRow = LabDataset["rows"][number] & { sourcePaths?: string[]; href?: string };
export type ResearchAnalysis = Omit<LabDataset, "rows"> & {
  rows: ResearchRow[];
  question?: string;
  method?: string;
  formula: string;
  interpretation: string;
  references: ResearchReference[];
  sources?: ResearchSource[];
  asOf?: string;
  novelty: "Derived analysis" | "Experimental formulation";
};
