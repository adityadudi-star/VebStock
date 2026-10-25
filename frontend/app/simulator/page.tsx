"use client";

import { useState } from "react";
import { ApiError, post } from "@/lib/api";
import { useMeta } from "@/lib/data";
import { dec, int, signed } from "@/lib/format";
import type { Scenario, ScenarioType, SimulateOut } from "@/lib/types";
import Disclosure from "@/components/Disclosure";
import { SimTag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import { PlanKpiGrid } from "@/components/PlanPanels";
import Stat, { StatGrid } from "@/components/Stat";
import Stateful, { Empty, ErrorBox } from "@/components/Stateful";
import DataTable, { Column } from "@/components/DataTable";
import { Section, Select, Tabs, TextInput } from "@/components/ui";

const KPI_LABEL: Record<string, string> = {
  projected_fill_rate_pct: "Demand covered (%)",
  unmet_demand_units: "Units not covered",
  shortage_vs_target_units: "Units short of the stock target",
  expected_expiring_units: "Units that may expire",
  expected_expiry_value: "Value that may expire",
  transport_cost: "Transport cost",
  shortage_cost: "Shortage cost",
  expiry_cost: "Expiry cost",
  units_shipped: "Units shipped",
  shipments: "Shipments",
};

type Changed = SimulateOut["comparison"]["changed_lines"][number];

export default function SimulatorPage() {
  const meta = useMeta();
  return (
    <div>
      <PageHeader
        href="/simulator"
        lede="Ask a what-if, such as a demand jump or a closed warehouse, and see how the plan would change. The original plan is never altered."
      />
      <Stateful state={meta} label="Loading options">{(m) => <Sim warehouses={m.warehouses} categories={m.categories_list} />}</Stateful>
    </div>
  );
}

function Sim({ warehouses, categories }: { warehouses: { id: number; name: string }[]; categories: string[] }) {
  const [type, setType] = useState<ScenarioType>("demand_spike");
  const [pct, setPct] = useState("30");
  const [category, setCategory] = useState("");
  const [wh, setWh] = useState("");
  const [days, setDays] = useState("7");
  const [delay, setDelay] = useState("3");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<SimulateOut | null>(null);

  const whOpts = warehouses.map((w) => ({ value: String(w.id), label: w.name }));
  const fe = error?.fieldErrors ?? {};

  function build(): Scenario | string {
    const num = (s: string) => (s.trim() === "" ? NaN : Number(s));
    if (type === "demand_spike") {
      if (Number.isNaN(num(pct))) return "Enter a percentage.";
      return { type, pct: num(pct), ...(category ? { category } : {}) };
    }
    if (type === "warehouse_closure") {
      if (!wh) return "Choose a warehouse to close.";
      if (!Number.isInteger(num(days))) return "Days must be a whole number.";
      return { type, warehouse_id: Number(wh), days: num(days) };
    }
    if (type === "transport_cost_change") {
      if (Number.isNaN(num(pct))) return "Enter a percentage.";
      return { type, pct: num(pct), ...(wh ? { warehouse_id: Number(wh) } : {}) };
    }
    if (!Number.isInteger(num(delay))) return "Delay must be a whole number of days.";
    return { type, delay_days: num(delay), ...(wh ? { warehouse_id: Number(wh) } : {}) };
  }

  async function run() {
    const s = build();
    if (typeof s === "string") {
      setError(new ApiError(s, 422));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await post<SimulateOut>("/simulate", { scenario: s }));
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
    } finally {
      setBusy(false);
    }
  }

  const changedCols: Column<Changed>[] = [
    { key: "store", header: "Store", render: (r) => r.store },
    { key: "sku", header: "Product", render: (r) => <span className="num">{r.sku_code}</span> },
    { key: "wh", header: "Warehouse", render: (r) => r.warehouse },
    { key: "b", header: "Before", align: "right", render: (r) => int(r.qty_base) },
    { key: "n", header: "After", align: "right", render: (r) => int(r.qty_new) },
    { key: "d", header: "Change", align: "right", render: (r) => <b>{signed(r.delta, 0)}</b> },
  ];

  return (
    <div>
      <Section title="Choose a what-if" kicker="One at a time">
        <Tabs
          tabs={[
            { id: "demand_spike", label: "Demand jumps" },
            { id: "warehouse_closure", label: "Warehouse closes" },
            { id: "transport_cost_change", label: "Transport costs change" },
            { id: "supplier_delay", label: "Supplier delays" },
          ]}
          value={type}
          onChange={(t) => {
            setType(t);
            setError(null);
          }}
        />
        <div className="grid max-w-3xl grid-cols-1 gap-4 sm:grid-cols-2">
          {type === "demand_spike" ? (
            <>
              <TextInput label="Demand change (%, negative for a drop)" type="number" value={pct} onChange={setPct} error={fe.pct} />
              <Select label="Category (optional)" value={category} onChange={setCategory} options={categories.map((c) => ({ value: c, label: c }))} placeholder="All categories" />
            </>
          ) : null}
          {type === "warehouse_closure" ? (
            <>
              <Select label="Warehouse to close" value={wh} onChange={setWh} options={whOpts} placeholder="Select…" />
              <TextInput label="Closure length (days)" type="number" min={1} max={60} value={days} onChange={setDays} error={fe.days} />
            </>
          ) : null}
          {type === "transport_cost_change" ? (
            <>
              <TextInput label="Cost change (%)" type="number" value={pct} onChange={setPct} error={fe.pct} />
              <Select label="Warehouse (optional)" value={wh} onChange={setWh} options={whOpts} placeholder="All warehouses" />
            </>
          ) : null}
          {type === "supplier_delay" ? (
            <>
              <TextInput label="Delay (days)" type="number" min={1} max={60} value={delay} onChange={setDelay} error={fe.delay_days} />
              <Select label="Warehouse (optional)" value={wh} onChange={setWh} options={whOpts} placeholder="All warehouses" />
            </>
          ) : null}
        </div>
        <div className="mt-5 flex items-center gap-4">
          <button type="button" className="btn btn-solid" onClick={run} disabled={busy}>
            {busy ? "Calculating…" : "Run what-if"}
          </button>
          {busy ? <span className="kicker">Recalculating the plan, about two seconds.</span> : null}
        </div>
        {error ? (
          <div className="mt-4">
            <ErrorBox error={error} onRetry={error.status === 422 ? undefined : run} />
          </div>
        ) : null}
      </Section>

      {!result ? (
        <Empty title="No what-if run yet">Pick a scenario above and run it. Results are compared with the base plan.</Empty>
      ) : (
        <Results r={result} changedCols={changedCols} />
      )}
    </div>
  );
}

function Results({ r, changedCols }: { r: SimulateOut; changedCols: Column<Changed>[] }) {
  const c = r.comparison;
  const sd = c.shipment_diff;
  return (
    <>
      <Section
        title="Result"
        kicker={`Scenario ${String(r.scenario.type).replace(/_/g, " ")} · new plan #${r.new_plan.id} against base plan #${r.base_plan_id}`}
        aside={<SimTag>Simulated data</SimTag>}
      >
        <StatGrid cols={4}>
          <Stat label="Extra units not covered" value={signed(c.additional_shortage_units, 1)} sub={`vs target ${signed(c.additional_shortage_vs_target_units, 1)} units`} inverted />
          <Stat label="Change in total cost" value={signed(c.cost_delta.total, 0)} sub="new plan minus base plan" />
          <Stat label="Shipment lines changed" value={int(sd.lines_changed)} sub={`${int(sd.lines_added)} added · ${int(sd.lines_removed)} removed`} />
          <Stat label="Store-product pairs rerouted" value={int(sd.store_skus_rerouted)} sub={`${int(sd.store_skus_newly_served)} newly served · ${int(sd.store_skus_no_longer_served)} no longer served`} />
        </StatGrid>
        <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">
          Units shipped: base {int(sd.units_base)} · new {int(sd.units_new)}
        </p>
      </Section>

      
      <div className="grid gap-x-10 lg:grid-cols-2">
        <Section title="Cost change" kicker="A plus sign means cost went up">
          <table className="tbl">
            <thead>
              <tr>
                <th>Component</th>
                <th className="r">Delta</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(c.cost_delta).map(([k, v]) => (
                <tr key={k}>
                  <td className="capitalize">{k}</td>
                  <td className="r num">{signed(v, 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      </div>

      <Section title="Top changed lines" kicker="Order as returned by the backend">
        {c.changed_lines.length === 0 ? (
          <Empty title="No lines changed" />
        ) : (
          <DataTable caption="Changed lines" columns={changedCols} rows={c.changed_lines} rowKey={(x) => `${x.store}-${x.sku_code}-${x.warehouse}`} />
        )}
      </Section>
      <Disclosure>
        <div className="h3 mb-2">New plan figures</div>
        <PlanKpiGrid k={r.new_plan.kpis} />
        <div className="h3 mb-2 mt-8">Full comparison with the base plan</div>

          <table className="tbl">
            <thead>
              <tr>
                <th>Measure</th>
                <th className="r">Base</th>
                <th className="r">New</th>
                <th className="r">Delta</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(c.kpi_deltas).map(([k, v]) => (
                <tr key={k}>
                  <td>{KPI_LABEL[k] ?? k.replace(/_/g, " ")}</td>
                  <td className="r num">{dec(c.kpis_base[k], 1)}</td>
                  <td className="r num">{dec(c.kpis_new[k], 1)}</td>
                  <td className="r num font-semibold">{signed(v, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
      </Disclosure>
    </>
  );
}
