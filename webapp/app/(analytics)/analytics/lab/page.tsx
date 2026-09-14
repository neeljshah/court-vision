import type { Metadata } from "next";
import MeasurementLab from "@/components/analytics/lab/MeasurementLab";
import { getLabData } from "@/lib/analytics/labData";
import "../workspace.css";
import "./lab.css";
export const metadata: Metadata = { title: "Measurement lab", description: "Inspect published sports measurements with sortable rankings, scatter plots, full data tables, and source-specific context." };
export default function LabPage() { return <MeasurementLab data={getLabData()} />; }
