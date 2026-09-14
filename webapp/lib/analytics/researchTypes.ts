import type { LabDataset } from "./labTypes";

export type ResearchReference = { title: string; url: string };
export type ResearchAnalysis = LabDataset & {
  formula: string;
  interpretation: string;
  references: ResearchReference[];
  asOf?: string;
  novelty: "Derived analysis" | "Experimental formulation";
};
