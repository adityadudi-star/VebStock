const nf0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function int(v: number | null | undefined): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : nf0.format(Math.round(v));
}
export function dec(v: number | null | undefined, d = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return new Intl.NumberFormat("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
}
export function pct(v: number | null | undefined, d = 1): string {
  return v === null || v === undefined ? "—" : `${dec(v, d)}%`;
}
export function signed(v: number | null | undefined, d = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const s = dec(Math.abs(v), d);
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}
export function signedPct(v: number | null | undefined, d = 1): string {
  return v === null || v === undefined ? "—" : `${signed(v, d)}%`;
}
export function date(v: string | null | undefined): string {
  if (!v) return "—";
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
/** Backend timestamps are UTC without a zone suffix. Parse them as UTC. */
export function parseUtc(v: string | null | undefined): Date | null {
  if (!v) return null;
  let t = v.includes("T") ? v : v.replace(" ", "T");
  if (!/(Z|[+-]\d\d:?\d\d)$/.test(t)) t += "Z";
  const d = new Date(t);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Local date and time of a backend UTC timestamp, e.g. "5 Mar 2027, 19:55". */
export function datetime(v: string | null | undefined): string {
  const d = parseUtc(v);
  if (!d) return "—";
  return `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}, ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
}

/** Relative form, e.g. "3 min ago". */
export function ago(v: string | null | undefined, now: number = Date.now()): string {
  const d = parseUtc(v);
  if (!d) return "";
  const s = Math.round((now - d.getTime()) / 1000);
  if (s < 0) return "just now";
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const days = Math.round(h / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

/** "5 Mar 2027, 19:55 (3 min ago)" */
export function when(v: string | null | undefined): string {
  const r = ago(v);
  return r ? `${datetime(v)} (${r})` : datetime(v);
}
export function label(key: string): string {
  return key.replace(/_/g, " ");
}

/** Short axis label for an ISO date such as "2026-10-25" -> "25 Oct 26". */
export function shortDate(v: string): string {
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });
}

/** ISO date plus whole days (calendar arithmetic, no time zone). */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
