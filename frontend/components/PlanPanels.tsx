"use client";

import { dec, int, when } from "@/lib/format";
import type { Plan, PlanKpis, Violation } from "@/lib/types";
import Disclosure from "./Disclosure";
import { StatusTag, Tag } from "./FlagLabel";
import Stat, { StatGrid } from "./Stat";
import { KV } from "./ui";

export function PlanKpiGrid({ k }: { k: PlanKpis }) {
  return (
    <div>
      <StatGrid cols={4}>
        <Stat label="Demand covered" value={`${dec(k.projected_fill_rate_pct)}%`} sub="projected over the planning horizon" />
        <Stat label="Units not covered" value={int(k.unmet_demand_units)} sub={`${int(k.shortage_vs_target_units)} short of the stock target`} />
        <Stat label="Units that may expire" value={int(k.expected_expiring_units)} sub={`worth ${int(k.expected_expiry_value)}`} />
        <Stat label="Units shipped" value={int(k.units_shipped)} sub={`${int(k.shipments)} shipments to ${int(k.stores_served)} stores`} />
      </StatGrid>
      <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">Basis: {k.basis}</p>
    </div>
  );
}

const VIOLATION_LABEL: Record<string, string> = {
  supply: "Not enough stock",
  batch_stock: "Batch too small",
  lane_capacity: "Lane over capacity",
  store_capacity: "Store over capacity",
  shelf_life: "Shelf life too short",
  fefo: "Not oldest stock first",
  integrality: "Not a whole number",
  closed_warehouse: "Warehouse closed",
  candidate_lane: "Route not allowed",
  known_batch: "Unknown batch",
};

export function ViolationList({ violations }: { violations: Violation[] }) {
  if (!violations.length) return null;
  return (
    <ul className="mt-2 border-t border-ink">
      {violations.map((v, i) => {
        const t = v.type ?? v.rule ?? "violation";
        return (
          <li key={i} className="grid gap-1 border-b border-ink-15 py-2 text-[12.5px] sm:grid-cols-[10rem_1fr] sm:gap-3">
            <span className="font-medium">{VIOLATION_LABEL[t] ?? t}</span>
            <span>{v.message ?? JSON.stringify(v)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function scalar(v: unknown): string | null {
  if (typeof v === "number") return dec(v, Number.isInteger(v) ? 0 : 2);
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "yes" : "no";
  return null;
}

/** Plan description in plain words, with technical items collapsed. */
export function PlanDetails({ plan }: { plan: Plan }) {
  const v = plan.validation;
  const timing = plan.notes.timing as Record<string, number | boolean> | undefined;
  const cb = plan.cost_breakdown;
  const noteRows = Object.entries(plan.notes)
    .filter(([k]) => !["timing", "cost_breakdown", "baseline_projection"].includes(k))
    .map(([k, val]) => [k.replace(/_/g, " "), scalar(val)] as [string, string | null])
    .filter((r): r is [string, string] => r[1] !== null);
  const baseProj = plan.notes.baseline_projection as Record<string, unknown> | undefined;
  const nViol = v.n_violations ?? v.violations?.length ?? 0;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h3 className="serif text-[28px] font-medium leading-none">Plan #{plan.id}</h3>
        <StatusTag status={plan.status} />
        <Tag tone="sage">Simulated data</Tag>
        {plan.scenario ? <Tag tone="outline">What-if: {String(plan.scenario.type).replace(/_/g, " ")}</Tag> : null}
      </div>
      <p className="mb-5 text-[13px] text-ink-60">
        Created {when(plan.created_at)}. Plans ahead for {plan.horizon_days} days from the simulated snapshot of {plan.as_of}.
        {plan.approved_at ? ` Approved ${when(plan.approved_at)} by ${plan.approved_by}.` : ""}
      </p>

      <StatGrid cols={4}>
        <Stat label="Total cost" value={int(plan.total_cost)} sub={`transport ${int(cb.transport)} · shortage ${int(cb.shortage)} · expiry ${int(cb.expiry)}`} inverted />
        <Stat label="Demand covered" value={`${dec(plan.kpis.projected_fill_rate_pct)}%`} sub="projected, not a replay" />
        <Stat label="Units not covered" value={int(plan.kpis.unmet_demand_units)} sub="shortage if the plan runs as is" />
        <Stat label="Units that may expire" value={int(plan.kpis.expected_expiring_units)} sub={`worth ${int(plan.kpis.expected_expiry_value)}`} />
      </StatGrid>

      <div className="mt-5 border border-ink p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="kicker !text-ink">Plan check</span>
          {v.valid ? <Tag tone="solid">✓ Passed</Tag> : <Tag tone="dashed">✗ Problems found</Tag>}
          <span className="text-[13px]">
            {nViol === 0 ? "0 problems found. Every shipment respects stock, capacity and shelf-life limits." : `${int(nViol)} problems found.`}
          </span>
        </div>
        <ViolationList violations={v.violations ?? []} />
      </div>

      <Disclosure>
        <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
          <div>
            <div className="h3 mb-2">Solver</div>
            <KV
              rows={[
                ["Solver status", plan.solver_status],
                ["Default alpha", String(plan.default_alpha)],
                ["Category alphas", Object.keys(plan.alphas).length ? Object.entries(plan.alphas).map(([c, a]) => `${c} ${a}`).join(", ") : "none set"],
                ["Explanation coverage", `${dec(plan.kpis.explanation_coverage_pct)}%`],
                ["Constraint violations", int(plan.kpis.constraint_violations)],
              ]}
            />
            {v.checked ? <p className="mt-2 text-[12px] leading-relaxed text-ink-60">Checks run: {v.checked.map((c) => c.replace(/_/g, " ")).join(", ")}.</p> : null}
            {v.violation_counts && Object.keys(v.violation_counts).length ? (
              <p className="mt-1 text-[12px] text-ink-60">
                Warnings noted: {Object.entries(v.violation_counts).map(([k, n]) => `${k} ${n}`).join(", ")}.
              </p>
            ) : null}
          </div>
          <div>
            <div className="h3 mb-2">Time taken</div>
            {timing ? (
              <KV
                rows={[
                  ["Loading inputs", `${dec(Number(timing.inputs_seconds), 3)} s`],
                  ["Solving", `${dec(Number(timing.solve_seconds), 3)} s`],
                  ["Checking", `${dec(Number(timing.validate_seconds), 3)} s`],
                  ["Saving", `${dec(Number(timing.persist_seconds), 3)} s`],
                  ["Total", `${dec(Number(timing.wall_clock_seconds), 3)} s`],
                  ["Target", `${dec(Number(timing.target_seconds), 0)} s · ${timing.target_met ? "met" : "not met"}`],
                ]}
              />
            ) : (
              <p className="text-[13px] text-ink-60">No timing recorded.</p>
            )}
          </div>
          <div>
            <div className="h3 mb-2">Rounding and relaxation notes</div>
            <KV rows={noteRows} />
          </div>
          <div>
            <div className="h3 mb-2">All plan figures</div>
            <PlanKpiGrid k={plan.kpis} />
            {baseProj ? (
              <div className="mt-6">
                <div className="h3 mb-2">Reference: baseline projection on the same snapshot</div>
                <KV
                  rows={Object.entries(baseProj)
                    .map(([k, val]) => [k.replace(/_/g, " "), scalar(val)] as [string, string | null])
                    .filter((r): r is [string, string] => r[1] !== null)}
                />
              </div>
            ) : null}
          </div>
        </div>
      </Disclosure>
    </div>
  );
}
