"use client";

import { RouteError } from "@/components/honest/RouteError";

export default function GameError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError section="Game" {...props} />;
}
