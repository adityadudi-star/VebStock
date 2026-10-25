"use client";

import { get } from "@/lib/api";
import { date, dec, int } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { FinanceSummary } from "@/lib/types";
import { BarsChart } from "@/components/charts";
import { SimTag, Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Stat, { StatGrid } from "@/components/Stat";
import Stateful from "@/components/Stateful";
import { Section } from "@/components/ui";
import PlanQueue from "@/components/role/PlanQueue";
import { CsvButton, GapNotice } from "@/components/role/blocks";
import Link from "next/link";

const TIER_LABEL: Record<string, string> = { store: "stores", warehouse: "warehouses", in_transit: "in transit" };

export default function FinanceDashboard() {
  const fin = useApi<FinanceSummary>("finance-summary", (s) => get<FinanceSummary>("/finance/summary", undefined, s));
  return (
    <div>
      <PageHeader
        href="/finance"
        kicker="Business Owner / Finance workspace"
        title="Business Owner / Finance"
        lede="Sales and stock value at list price, expiry exposure and the cost of the latest distribution plan. Figures the data cannot support are listed, not estimated."
      />

      <Stateful state={fin} label="Loading financial summary">
        {(d) => {
          const exp = Object.values(d.expiry_exposure).reduce((a, b) => ({ units: a.units + b.units, writeoff_value: a.writeoff_value + b.writeoff_value, list_value: a.list_value + b.list_value }));
          const lp = d.latest_plan;
          const tiers = Object.entries(d.inventory_value.by_tier)
            .map(([k, v]) => `${int(v.value)} ${TIER_LABEL[k] ?? k}`)
            .join(", ");
          return (
            <>
              <Section title="Financial position" kicker={`Snapshot ${date(d.as_of)}`} aside={<><SimTag>Simulated data</SimTag><Tag tone="quiet">List price basis</Tag></>}>
                <StatGrid cols={4}>
                  <Stat label="Stock value at list price" value={int(d.inventory_value.total)} sub={tiers} />
                  <Stat label={`Sales, last ${d.sales.days} days`} value={int(d.sales.total)} sub={`${int(d.sales.units)} units at list price`} />
                  <Stat label="Expiry exposure" value={int(exp.writeoff_value)} sub={`${int(exp.units)} units that may expire, at write-off cost`} inverted />
                  <Stat
                    label="Latest plan cost"
                    value={lp ? int(lp.cost_breakdown.total) : "—"}
                    sub={lp ? `plan #${lp.id} (${lp.status}); fill ${dec(lp.projected_fill_rate_pct)}%` : "No plan generated yet"}
                  />
                </StatGrid>
              </Section>

              <Section title="Stock value by category" kicker="List price, by where the stock sits">
                <BarsChart
                  data={d.inventory_value.by_category}
                  xKey="category"
                  stacked
                  series={[
                    { key: "warehouse", name: "Warehouses", style: "ink" },
                    { key: "store", name: "Stores", style: "sage" },
                    { key: "in_transit", name: "In transit", style: "hatch" },
                  ]}
                />
                <div className="mt-3">
                  <CsvButton
                    filename="stock-value-by-category.csv"
                    headers={["Category", "Warehouses", "Stores", "In transit"]}
                    rows={d.inventory_value.by_category.map((r) => [r.category, r.warehouse, r.store, r.in_transit])}
                  />
                </div>
              </Section>

              <Section title="Sales by category" kicker={`Last ${d.sales.days} days, units × list price`}>
                <BarsChart data={d.sales.by_category} xKey="category" series={[{ key: "value", name: "Sales at list price", style: "sage" }]} />
                <div className="mt-3">
                  <CsvButton
                    filename="sales-by-category.csv"
                    headers={["Category", "Units", "Sales at list price"]}
                    rows={d.sales.by_category.map((r) => [r.category, r.units, r.value])}
                  />
                </div>
              </Section>

              {lp ? (
                <Section title="Cost of the latest plan" kicker={`Plan #${lp.id}, ${lp.status}`}>
                  <BarsChart
                    horizontal
                    height={160}
                    data={[
                      { name: "Transport", v: lp.cost_breakdown.transport },
                      { name: "Shortage", v: lp.cost_breakdown.shortage },
                      { name: "Expiry", v: lp.cost_breakdown.expiry },
                    ]}
                    xKey="name"
                    series={[{ key: "v", name: "Cost", style: "ink" }]}
                    yWidth={80}
                  />
                </Section>
              ) : null}
            </>
          );
        }}
      </Stateful>

      <Section title="Plans" kicker="Review, approve, download">
        <PlanQueue
          links={[
            { href: "/plan", label: "Review and approve plans" },
            { href: "/overrides", label: "Override log" },
            { href: "/compare", label: "Baseline comparison" },
            { href: "/overview", label: "Company overview" },
          ]}
        />
      </Section>

      <Section title="What these figures do not include" kicker="Limitations">
        <GapNotice
          title="Read before using any figure above"
          items={fin.data?.limitations ?? ["Loading…"]}
        />
        <p className="mt-3 text-[13px] text-ink-60">
          Revenue, cost and profit need invoice, purchase and payment records. Until those exist, use the figures above for relative comparison only.{" "}
          <Link href="/data" className="underline underline-offset-2">
            Data and assumptions
          </Link>
        </p>
      </Section>
    </div>
  );
}
