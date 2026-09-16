import type { LabDataset, LabField } from "./labTypes";

export type ResearchReference = { title: string; url: string };
export type ResearchSource = { id: string; asOf: string; fields?: string[]; rowWindows?: Record<string, string[]> };
export type ResearchField = LabField & { sourceId?: string };
export type ResearchOperandBinding = { operand: string; sourcePath: string; valueKey: string; label: string };
export type ResearchOperandValue = number | string | null;
export type ResearchRow = LabDataset["rows"][number] & {
  sourcePaths?: string[];
  href?: string;
  bindingValues?: Record<string, ResearchOperandValue>;
  windows?: Record<string, string>;
};
export type ResearchAnalysis = Omit<LabDataset, "rows" | "fields"> & {
  fields: ResearchField[];
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
