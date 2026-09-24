export class ApiError extends Error {
  constructor(public status: number, public code: string, public field?: string) {
    super(code);
  }
}

export function reportClientIssue(kind:"NetworkError"|"TimeoutError"|"HttpError"|"SlowRequest"|"MediaError",requestId="") {
  if(typeof window!=="undefined")window.dispatchEvent(new CustomEvent("sensi:diagnostic",{detail:{kind,requestId:/^[a-f0-9]{16}$/.test(requestId)?requestId:""}}));
}

export async function api<T>(path: string, csrf = "", init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const method = (init.method ?? "GET").toUpperCase();
  if (csrf && method !== "GET" && method !== "HEAD") headers.set("X-CSRF-Token", csrf);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const controller = new AbortController();
  const started=Date.now(),report=path!=="/api/analytics/client-error";
  const abort = () => controller.abort();
  const timeout = window.setTimeout(abort, init.body instanceof FormData ? 300_000 : 15_000);
  init.signal?.addEventListener("abort", abort, { once:true });
  if (init.signal?.aborted) abort();
  try {
    const response = await fetch(path, { ...init, signal:controller.signal, headers, credentials:"same-origin" });
    const text = await response.text();
    let data: Record<string, unknown>;
    try { data = JSON.parse(text) as Record<string, unknown>; }
    catch {
      if(report)reportClientIssue("HttpError",response.headers.get("X-Request-ID")??"");
      throw new ApiError(response.status, "invalid_response");
    }
    if (!response.ok) {
      if(report&&response.status>=500)reportClientIssue("HttpError",response.headers.get("X-Request-ID")??"");
      throw new ApiError(response.status, String(data.error ?? `http_${response.status}`), typeof data.field === "string" ? data.field : undefined);
    }
    return data as T;
  } catch(error) {
    if(report&&!(error instanceof ApiError)&&!init.signal?.aborted)reportClientIssue(controller.signal.aborted?"TimeoutError":"NetworkError");
    throw error;
  } finally {
    window.clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abort);
    if(report&&Date.now()-started>=2000&&!init.signal?.aborted)reportClientIssue("SlowRequest");
  }
}
