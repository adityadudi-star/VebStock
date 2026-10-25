"use client";

import { useState } from "react";
import { get } from "@/lib/api";
import { ago, datetime, int } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { OverrideLogResponse, OverrideLogRow } from "@/lib/types";
import DataTable, { Column } from "@/components/DataTable";
import { Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Pagination from "@/components/Pagination";
import Stateful, { Empty } from "@/components/Stateful";
import { Select, TextInput } from "@/components/ui";

export default function OverridesPage() {
  const [action, setAction] = useState("");
  const [plan, setPlan] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const planD = useDebounced(plan);
  const state = useApi<OverrideLogResponse>(`ovr:${action}:${planD}:${page}:${pageSize}`, (s) =>
    get<OverrideLogResponse>("/overrides", { action, plan_id: planD, page, page_size: pageSize }, s),
  );
  const cols: Column<OverrideLogRow>[] = [
    {
      key: "ts",
      header: "When",
      render: (r) => (
        <span>
          {datetime(r.ts)}
          <span className="block text-[11px] text-ink-60">{ago(r.ts)}</span>
        </span>
      ),
    },
    {
      key: "act",
      header: "What",
      render: (r) => (
        <span>
          <Tag tone={r.action === "approve" ? "solid" : "sage"}>{r.action === "approve" ? "approved" : "changed"}</Tag>
          <span className="num block text-[11px] text-ink-60">plan #{r.plan_id}</span>
        </span>
      ),
    },
    { key: "actor", header: "Who", render: (r) => r.actor },
    {
      key: "what",
      header: "Product and route",
      render: (r) => (
        <span>
          <span className="num">{r.sku_code ?? "—"}</span>
          <span className="block text-[11px] text-ink-60">
            {r.warehouse ?? "—"} to {r.store ?? "—"}
          </span>
        </span>
      ),
    },
    {
      key: "qty",
      header: "Units",
      align: "right",
      render: (r) => (r.original_qty === null || r.new_qty === null ? "—" : r.original_qty === r.new_qty ? int(r.new_qty) : `${int(r.original_qty)} → ${int(r.new_qty)}`),
    },
    { key: "reason", header: "Reason", className: "max-w-[36ch] text-[12px]", render: (r) => r.reason },
  ];
  return (
    <div>
      <PageHeader
        href="/overrides"
        lede="See every change anyone made to a plan and every approval, with who did it, when and why."
      />
      <div className="mb-5 grid max-w-xl grid-cols-2 gap-3 border border-ink-15 p-3">
        <Select
          label="Show"
          value={action}
          onChange={(v) => {
            setAction(v);
            setPage(1);
          }}
          options={[
            { value: "override", label: "Changes" },
            { value: "approve", label: "Approvals" },
          ]}
        />
        <TextInput
          label="Plan number"
          type="number"
          min={1}
          value={plan}
          onChange={(v) => {
            setPlan(v);
            setPage(1);
          }}
        />
      </div>
      <Stateful state={state} label="Loading log" isEmpty={(d) => d.rows.length === 0} empty={<Empty title="Nothing logged yet">No plan has been changed or approved, or nothing matches these filters.</Empty>}>
        {(d) => (
          <>
            <DataTable caption="Override log" columns={cols} rows={d.rows} rowKey={(r) => r.id} />
            <Pagination
              page={d.page}
              pageSize={d.page_size}
              total={d.total}
              onPage={setPage}
              onPageSize={(s) => {
                setPageSize(s);
                setPage(1);
              }}
            />
          </>
        )}
      </Stateful>
    </div>
  );
}
