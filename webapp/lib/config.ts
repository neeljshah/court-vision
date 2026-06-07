export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export const WS_URL = (token?: string) => {
  const base = (process.env.NEXT_PUBLIC_WS_BASE ||
                API_BASE.replace(/^http/, "ws"));
  const t = token || process.env.NEXT_PUBLIC_AUTH_TOKEN || "";
  return `${base}/ws/live${t ? `?token=${encodeURIComponent(t)}` : ""}`;
};

export const REST = (path: string) => {
  const t = process.env.NEXT_PUBLIC_AUTH_TOKEN;
  const sep = path.includes("?") ? "&" : "?";
  return `${API_BASE}${path}${t ? `${sep}token=${encodeURIComponent(t)}` : ""}`;
};
