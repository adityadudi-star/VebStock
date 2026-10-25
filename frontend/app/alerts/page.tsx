"use client";

import { useState } from "react";
import { get } from "@/lib/api";
import { REGIONS, useMeta, usePlans } from "@/lib/data";
import { dec, int, date } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AlertRow, AlertType, AlertsResponse, PickList } from "@/lib/types";
import { UtilBar } from "@/components/charts";
import DataTable, { Column } from "@/components/DataTable";
import { Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import PickListView from "@/components/PickListView";
import Stateful, { Empty } from "@/components/Stateful";
import { Section, Select, Tabs } from "@/components/ui";

const TYPES: { id: AlertType; label: string; valueLabel: string }[] = [
  { id: "stockout_prediction", label: "Likely to run out", valueLabel: "Days to stockout" },
  { id: "low_stock", label: "Running low", valueLabel: "Days of stock left" },
  { id: "rising_demand", label: "Demand rising", valueLabel: "Forecast against recent average" },
  { id: "near_expiry", label: "May expire soon", valueLabel: "Units that may expire" },
  { id: "delayed_shipment", label: "Shipment delayed", valueLabel: "Days delayed" },
];

export default function AlertsPage() {
  return (
    <div>
      <PageHeader
        href="/alerts"
        title="Alerts & Dispatch"
        lede="See which store-product pairs need attention, then pick an approved plan below to get the warehouse pick list."
      />
      <Alerts />
      <Dispatch />
    </div>
  );
}

function Alerts() {
  const [type, setType] = useState<AlertType>("stockout_prediction");
  const [region, setRegion] = useState("");
  const state = useApi<AlertsResponse>(`alerts:${type}:${region}`, (s) =>
    get<AlertsResponse>("/alerts", { type, region, limit: 100 }, s),
  );
  const t = TYPES.find((x) => x.id === type)!;
  const cols: Column<AlertRow>[] = [
    { key: "sev", header: "Urgency", render: (r) => <Tag tone={r.severity === "high" ? "solid" : r.severity === "medium" ? "outline" : "quiet"}>{r.severity}</Tag> },
    { key: "store", header: "Store", render: (r) => <span>{r.store}<span className="block text-[11px] text-ink-60">{r.region}</span></span> },
    {
      key: "sku",
      header: "Product",
      render: (r) => (
        <div>
          <span className="num">{r.sku_code}</span>
          <span className="block text-[11px] text-ink-60">{r.sku_name}</span>
        </div>
      ),
    },
    {
      key: "msg",
      header: "What is happening",
      className: "max-w-[60ch]",
      render: (r) => (
        <span>
          {r.message}
          <span className="num block text-[11px] text-ink-60">
            {t.valueLabel}: {dec(r.value, type === "rising_demand" ? 2 : Number.isInteger(r.value) ? 0 : 1)}
          </span>
        </span>
      ),
    },
  ];
  return (
    <Section title="Alerts" kicker="Pick a type" aside={<Tag tone="sage">Simulated data</Tag>}>
      <Tabs
        tabs={TYPES.map((x) => ({
          id: x.id,
          label: (
            <span>
              {x.label} <span className="num opacity-60">{state.data ? int(state.data.counts[x.id] ?? 0) : "…"}</span>
            </span>
          ),
        }))}
        value={type}
        onChange={setType}
      />
      <div className="mb-4 max-w-xs">
        <Select label="Region" value={region} onChange={setRegion} options={REGIONS.map((r) => ({ value: r, label: r }))} />
      </div>
      <Stateful state={state} label="Loading alerts" isEmpty={(d) => d.alerts.length === 0} empty={<Empty title="Nothing to flag here">No alerts of this type match the current region.</Empty>}>
        {(d) => (
          <>
            <p className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">
              Showing {int(d.alerts.length)} of {int(d.total)}, simulated snapshot {date(d.as_of)}
            </p>
            <DataTable caption="Alerts" columns={cols} rows={d.alerts} rowKey={(r) => `${r.type}-${r.store}-${r.sku_code}`} />
          </>
        )}
      </Stateful>
    </Section>
  );
}

function Dispatch() {
  const meta = useMeta();
  const plans = usePlans(50);
  const [planId, setPlanId] = useState("");
  const [wh, setWh] = useState("");
  const [allLanes, setAllLanes] = useState(false);
  const approved = (plans.data ?? []).filter((p) => p.status === "approved");
  const pick = useApi<PickList>(
    `dispatch:${planId}:${wh}`,
    planId ? (s) => get<PickList>(`/plans/${planId}/pick-list`, { warehouse_id: wh }, s) : null,
  );

  return (
    <Section title="Dispatch" kicker="Approved plans only">
      <Stateful
        state={plans}
        label="Loading plans"
        isEmpty={() => approved.length === 0}
        empty={<Empty title="No approved plan yet">Approve a plan in the Distribution Plan view first. A pick list is only released for approved plans.</Empty>}
      >
        {() => (
          <>
            <div className="mb-6 grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
              <Select
                label="Approved plan"
                value={planId}
                onChange={setPlanId}
                placeholder="Select…"
                options={approved.map((p) => ({ value: String(p.id), label: `Plan #${p.id}, horizon ${p.horizon_days}d` }))}
              />
              <Select label="Warehouse" value={wh} onChange={setWh} options={(meta.data?.warehouses ?? []).map((w) => ({ value: String(w.id), label: w.name }))} placeholder="All warehouses" />
            </div>
            {!planId ? (
              <Empty title="Choose an approved plan">Its pick list and lane loads appear here.</Empty>
            ) : (
              <Stateful state={pick} label="Loading pick list" isEmpty={(d) => d.batches.length === 0} empty={<Empty title="Nothing to pick for this selection" />}>
                {(p) => {
                  const lanes = [...p.lanes].sort((a, b) => b.utilization_pct - a.utilization_pct);
                  const shown = allLanes ? lanes : lanes.slice(0, 15);
                  return (
                    <>
                      <div className="mb-10">
                        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                          <h3 className="h3">How full each delivery route is</h3>
                          <span className="kicker">Busiest first. A longer bar means the route is closer to its capacity.</span>
                        </div>
                        {lanes.length === 0 ? (
                          <Empty title="No lane data" />
                        ) : (
                          <>
                            <div className="border-t border-ink">
                              {shown.map((l) => (
                                <UtilBar
                                  key={`${l.warehouse_id}-${l.store_id}`}
                                  label={`${l.warehouse} → ${l.store}`}
                                  value={l.utilization_pct}
                                  right={`${dec(l.utilization_pct, 1)}% · ${int(l.units)}u`}
                                />
                              ))}
                            </div>
                            {lanes.length > 15 ? (
                              <button type="button" className="btn btn-sm mt-3" onClick={() => setAllLanes((v) => !v)}>
                                {allLanes ? "Show top 15 only" : `Show all ${lanes.length} lanes`}
                              </button>
                            ) : null}
                          </>
                        )}
                      </div>
                      <h3 className="h3 mb-1">Pick list, grouped by expiry date</h3>
                      <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.08em] text-ink-60">Order: {p.ordering}. In short, the oldest stock ships first.</p>
                      <PickListView batches={[...p.batches].sort((a, b) => a.expiry_date.localeCompare(b.expiry_date))} groupBy="expiry" />
                    </>
                  );
                }}
              </Stateful>
            )}
          </>
        )}
      </Stateful>
    </Section>
  );
}
