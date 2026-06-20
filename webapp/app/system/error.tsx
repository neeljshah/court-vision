"use client";

import { RouteError } from "@/components/honest/RouteError";

export default function SystemError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="System" {...props} />;
}
