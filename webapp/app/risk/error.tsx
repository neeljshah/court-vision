"use client";

import { RouteError } from "@/components/honest/RouteError";

export default function RiskError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="Risk" {...props} />;
}
