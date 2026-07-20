const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();

export const API_BASE_URL = configuredApiUrl?.replace(/\/+$/, "") ?? "";

export const API_REQUEST_HEADERS = {
  "ngrok-skip-browser-warning": "true",
} as const;

export function apiUrl(path: string): string {
  if (!API_BASE_URL) {
    throw new Error("Thiếu cấu hình NEXT_PUBLIC_API_URL.");
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}
