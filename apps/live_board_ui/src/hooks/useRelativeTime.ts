/** useRelativeTime -- returns a live-updating short relative label for an ISO timestamp. */
import { useState, useEffect } from "react";
import { localTime } from "@/lib/format";

function getLabel(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const diffMs = Date.now() - d.getTime();
  const diffS = Math.floor(diffMs / 1000);
  if (diffS < 10) return "just now";
  if (diffS < 60) return `${diffS}s ago`;
  const diffM = Math.floor(diffS / 60);
  if (diffM < 60) return `${diffM}m ago`;
  const diffH = Math.floor(diffM / 60);
  if (diffH < 24) return `${diffH}h ago`;
  return localTime(iso);
}

export function useRelativeTime(iso: string | null): string {
  const [label, setLabel] = useState<string>(() =>
    typeof window !== "undefined" ? getLabel(iso) : ""
  );

  useEffect(() => {
    setLabel(getLabel(iso));
    const id = setInterval(() => setLabel(getLabel(iso)), 20_000);
    return () => clearInterval(id);
  }, [iso]);

  return label;
}
