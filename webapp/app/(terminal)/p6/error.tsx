"use client";

import { RouteError } from "@/components/honest/RouteError";

export default function P6Error(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="Dashboard" {...props} />;
}
