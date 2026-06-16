import type { BoardResponse, Sport } from "@/types/board";

/**
 * Fetch the live board for a sport. Tennis can return 300+ rows and the ESPN
 * upstream is occasionally slow, so callers should expect multi-second waits
 * and pass an AbortSignal when polling. Throws on non-2xx or network failure.
 */
export async function fetchBoard(
  sport: Sport,
  leagues?: string,
  signal?: AbortSignal,
): Promise<BoardResponse> {
  const params = new URLSearchParams({ sport });
  if (leagues) params.set("leagues", leagues);
  const res = await fetch(`/api/board?${params.toString()}`, {
    cache: "no-store",
    signal,
  });
  if (!res.ok) {
    throw new Error(`Board request failed: HTTP ${res.status}`);
  }
  return (await res.json()) as BoardResponse;
}
