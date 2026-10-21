import type { Metadata } from "next";
import MeasurementLab from "@/components/analytics/lab/MeasurementLab";
import { getLabData } from "@/lib/analytics/labData";
import "../workspace.css";
import "./lab.css";
import { pageMeta } from "@/lib/seo/meta";
export const metadata: Metadata = pageMeta("/analytics/lab/", { title: "Measurement lab", description: "Inspect published sports measurements with sortable rankings, scatter plots, full data tables, and source-specific context." });
export default function LabPage() { return <MeasurementLab data={getLabData()} />; }
