"use client";

import { get } from "./api";
import { useApi } from "./hooks";
import type { Meta, PlanSummary } from "./types";

export function useMeta() {
  return useApi<Meta>("meta", (signal) => get<Meta>("/meta", undefined, signal));
}

export function usePlans(limit = 20) {
  return useApi<PlanSummary[]>(`plans:${limit}`, (signal) => get<PlanSummary[]>("/plans", { limit }, signal));
}

export const REGIONS = ["North", "South", "East", "West", "Central"];

/** Display metadata for replay KPI keys. Units describe the backend values; nothing is computed here. */
export const KPI_META: Record<string, { label: string; unit: "%" | "" | "s"; lowerIsBetter: boolean }> = {
  stockout_rate: { label: "Stockout rate", unit: "%", lowerIsBetter: true },
  fill_rate: { label: "Fill rate", unit: "%", lowerIsBetter: false },
  transport_cost: { label: "Transport cost", unit: "", lowerIsBetter: true },
  expiry_wastage_pct: { label: "Expiry wastage", unit: "%", lowerIsBetter: true },
  weekly_mape: { label: "Weekly MAPE", unit: "%", lowerIsBetter: true },
  plan_seconds_mean: { label: "Plan time (mean)", unit: "s", lowerIsBetter: true },
};

export function fmtKpi(key: string, v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const m = KPI_META[key];
  const digits = key === "transport_cost" ? 0 : key === "plan_seconds_mean" ? 2 : 2;
  const s = new Intl.NumberFormat("en-IN", { minimumFractionDigits: digits === 0 ? 0 : 2, maximumFractionDigits: digits }).format(v);
  return `${s}${m?.unit ? (m.unit === "s" ? " s" : "%") : ""}`;
}
