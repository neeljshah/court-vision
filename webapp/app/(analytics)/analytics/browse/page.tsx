import type { Metadata } from "next";
import LibraryExplorer from "@/components/analytics/library/LibraryExplorer";
import { getLibraryEntries } from "@/lib/analytics/libraryData";
import "../workspace.css";
import "./library.css";
import { pageMeta } from "@/lib/seo/meta";
export const metadata: Metadata = pageMeta("/analytics/browse/", { title: "Analytics library", description: "Explore source modules and derived sports analyses. Search formulas, compare measurements, and inspect the evidence." });
export default function BrowsePage() { return <LibraryExplorer entries={getLibraryEntries()} />; }
