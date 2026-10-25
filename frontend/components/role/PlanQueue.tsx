"use client";

import Link from "next/link";
import { dec, int, when } from "@/lib/format";
import { usePlans } from "@/lib/data";
import type { PlanSummary } from "@/lib/types";
import DataTable, { type Column } from "@/components/DataTable";
import { StatusTag } from "@/components/FlagLabel";
import Stateful, { Empty } from "@/components/Stateful";
import { CsvButton } from "./blocks";

/** Recent distribution plans from GET /plans. Approval and picking happen on the existing Plan and Alerts pages. */
export default function PlanQueue({ limit = 8, links }: { limit?: number; links: { href: string; label: string }[] }) {
  const state = usePlans(limit);
  const cols: Column<PlanSummary>[] = [
    { key: "id", header: "Plan", render: (r) => <span className="num">#{r.id}</span> },
    { key: "st", header: "Status", render: (r) => <StatusTag status={r.status} /> },
    { key: "at", header: "Created", render: (r) => <span className="text-[12px]">{when(r.created_at)}</span> },
    { key: "h", header: "Days planned", align: "right", render: (r) => int(r.horizon_days) },
    { key: "u", header: "Units to ship", align: "right", render: (r) => int(r.kpis.units_shipped) },
    { key: "s", header: "Stores served", align: "right", render: (r) => int(r.kpis.stores_served) },
    { key: "f", header: "Projected fill", align: "right", render: (r) => `${dec(r.kpis.projected_fill_rate_pct)}%` },
    { key: "c", header: "Total cost", align: "right", render: (r) => int(r.total_cost) },
  ];
  return (
    <Stateful state={state} label="Loading plans" isEmpty={(d) => d.length === 0} empty={<Empty title="No plans yet">Open the Distribution Plan page to generate one.</Empty>}>
      {(d) => (
        <>
          <DataTable caption="Recent plans" columns={cols} rows={d} rowKey={(r) => r.id} />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {links.map((l) => (
              <Link key={l.href} href={l.href} className="btn btn-sm">
                {l.label}
              </Link>
            ))}
            <CsvButton
              filename="plans.csv"
              headers={["Plan", "Status", "Created (UTC)", "Days planned", "Units to ship", "Stores served", "Projected fill %", "Total cost"]}
              rows={d.map((r) => [r.id, r.status, r.created_at, r.horizon_days, r.kpis.units_shipped, r.kpis.stores_served, r.kpis.projected_fill_rate_pct, r.total_cost])}
            />
          </div>
        </>
      )}
    </Stateful>
  );
}
