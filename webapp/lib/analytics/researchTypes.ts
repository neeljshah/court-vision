import type { LabDataset } from "./labTypes";

export type ResearchReference = { title: string; url: string };
export type ResearchSource = { id: string; asOf: string };
export type ResearchOperandBinding = { operand: string; sourcePath: string; valueKey: string; label: string };
export type ResearchOperandValue = number | string | null;
export type ResearchRow = LabDataset["rows"][number] & {
  sourcePaths?: string[];
  href?: string;
  bindingValues?: Record<string, ResearchOperandValue>;
};
export type ResearchAnalysis = Omit<LabDataset, "rows"> & {
  rows: ResearchRow[];
  question?: string;
  method?: string;
  formula: string;
  interpretation: string;
  references: ResearchReference[];
  sources?: ResearchSource[];
  bindings?: ResearchOperandBinding[];
  asOf?: string;
  novelty: "Derived analysis" | "Experimental formulation";
};
