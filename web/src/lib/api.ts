export class ApiError extends Error {
  constructor(public status: number, public code: string) {
    super(code);
  }
}

export async function api<T>(path: string, csrf = "", init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (csrf && method !== "GET" && method !== "HEAD") headers.set("X-CSRF-Token", csrf);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const controller = new AbortController();
  const abort = () => controller.abort();
  const timeout = window.setTimeout(abort, init.body instanceof FormData ? 60_000 : 15_000);
  init.signal?.addEventListener("abort", abort, { once:true });
  if (init.signal?.aborted) abort();
  try {
    const response = await fetch(path, { ...init, signal:controller.signal, headers, credentials:"same-origin" });
    const text = await response.text();
    let data: Record<string, unknown>;
    try { data = JSON.parse(text) as Record<string, unknown>; }
    catch { throw new ApiError(response.status, "invalid_response"); }
    if (!response.ok) throw new ApiError(response.status, String(data.error ?? `http_${response.status}`));
    return data as T;
  } finally {
    window.clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abort);
  }
}
