// Single gateway to the VebStock backend. Every request in the app goes through this module.

const RAW = process.env.NEXT_PUBLIC_API_BASE_URL;

/** Returns the backend base URL, or null when the deployment is misconfigured. */
export function apiBase(): string | null {
  if (RAW && RAW.trim()) return RAW.trim().replace(/\/+$/, "");
  if (process.env.NODE_ENV !== "production") return "http://localhost:8000";
  return null;
}

export const configError: string | null =
  apiBase() === null
    ? "NEXT_PUBLIC_API_BASE_URL is not set. Set it to the backend URL in the deployment environment and redeploy."
    : null;

export interface Violation {
  type?: string;
  rule?: string;
  warehouse_id?: number;
  sku_id?: number;
  message?: string;
  line_id?: number;
  [k: string]: unknown;
}

export class ApiError extends Error {
  status: number; // 0 = network failure / unreachable
  violations: Violation[];
  fieldErrors: Record<string, string>;
  constructor(
    message: string,
    status: number,
    violations: Violation[] = [],
    fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.status = status;
    this.violations = violations;
    this.fieldErrors = fieldErrors;
  }
  get unreachable() {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504;
  }
}

type Params = Record<string, string | number | boolean | null | undefined>;

function qs(params?: Params): string {
  if (!params) return "";
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

function extract(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return new ApiError(detail, status);
  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    const msgs = detail.map((d: { loc?: unknown[]; msg?: string }) => {
      const loc = (d.loc ?? []).filter((x) => x !== "body").map(String);
      const msg = String(d.msg ?? "invalid").replace(/^Value error, /, "");
      fields[loc[loc.length - 1] ?? "_"] = msg;
      return loc.length ? `${loc.join(".")}: ${msg}` : msg;
    });
    return new ApiError(msgs.join("; "), status, [], fields);
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; violations?: Violation[] };
    return new ApiError(d.message ?? `Request failed (${status})`, status, d.violations ?? []);
  }
  return new ApiError(`Request failed (${status})`, status);
}

export async function request<T>(
  path: string,
  opts: { method?: string; body?: unknown; params?: Params; signal?: AbortSignal } = {},
): Promise<T> {
  const base = apiBase();
  if (base === null) throw new ApiError(configError ?? "API base URL is not configured", 0);
  let res: Response;
  try {
    res = await fetch(`${base}${path}${qs(opts.params)}`, {
      method: opts.method ?? "GET",
      headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(
      "Cannot reach the backend. It may be waking up from sleep (free hosting tiers can take up to a minute) or is offline.",
      0,
    );
  }
  let json: unknown = null;
  try {
    json = await res.json();
  } catch {
    json = null;
  }
  if (!res.ok) throw extract(res.status, json);
  return json as T;
}

export const get = <T>(path: string, params?: Params, signal?: AbortSignal) =>
  request<T>(path, { params, signal });
export const post = <T>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, { method: "POST", body, signal });
export const patch = <T>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, { method: "PATCH", body, signal });
