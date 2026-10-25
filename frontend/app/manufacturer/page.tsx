"use client";

import Link from "next/link";
import { get } from "@/lib/api";
import { date, dec, int, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Overview } from "@/lib/types";
import { TrendChart } from "@/components/charts";
import { SimTag, StatusTag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Stat, { StatGrid } from "@/components/Stat";
import Stateful, { Empty } from "@/components/Stateful";
import { Section } from "@/components/ui";
import { AlertList, GapNotice, StockTable } from "@/components/role/blocks";

export default function ManufacturerDashboard() {
  const ov = useApi<Overview>("overview", (s) => get<Overview>("/overview", undefined, s));
  return (
    <div>
      <PageHeader
        href="/manufacturer"
        kicker="Manufacturer workspace"
        title="Manufacturer"
        lede="What the market is expected to need, how much finished stock is on hand and which products are closest to running out."
      />

      <Stateful state={ov} label="Loading manufacturing view">
        {(d) => {
          const th = d.inventory.thresholds as Record<string, number | string>;
          const acc = d.forecast_accuracy;
          const lp = d.latest_plan;
          return (
            <>
              <Section title="Finished stock and demand" kicker="Right now" aside={<SimTag>Simulated data</SimTag>}>
                <StatGrid cols={4}>
                  <Stat
                    label="Finished stock available"
                    value={int((th.warehouse_available as number) + d.inventory.available)}
                    sub={`${int(th.warehouse_available as number)} in warehouses, ${int(d.inventory.available)} in stores`}
                  />
                  <Stat
                    label="Products to replenish"
                    value={int(d.alert_counts.stockout_prediction ?? 0)}
                    sub={`store-product pairs likely to run out; ${int(d.alert_counts.low_stock ?? 0)} more running low`}
                    inverted
                  />
                  <Stat
                    label="Forecast miss (weekly MAPE)"
                    value={acc ? `${dec(acc.mape_mean)}%` : "—"}
                    sub={acc ? `target below ${dec(acc.target_mape, 0)}%` : "No forecast run on file"}
                  />
                  <Stat label="Shipments delayed" value={int(d.alert_counts.delayed_shipment ?? 0)} sub={`snapshot ${date(d.as_of)}`} />
                </StatGrid>
              </Section>

              <Section title="Demand outlook" kicker="Weekly units: history and forecast">
                {d.charts.demand_trend.length ? <TrendChart points={d.charts.demand_trend} /> : <Empty title="No demand series" />}
              </Section>

              <Section title="Delivery readiness" kicker="Latest distribution plan">
                {lp ? (
                  <StatGrid cols={4}>
                    <Stat label="Plan" value={`#${lp.id}`} sub={<StatusTag status={lp.status} />} />
                    <Stat label="Units to ship" value={int(lp.kpis.units_shipped)} sub={`to ${int(lp.kpis.stores_served)} stores`} />
                    <Stat label="Projected fill" value={`${dec(lp.kpis.projected_fill_rate_pct)}%`} sub="static projection for the plan horizon" />
                    <Stat
                      label="Created"
                      value={<span className="text-[18px]">{when(lp.created_at)}</span>}
                      sub={lp.status === "approved" ? "Approved: the pick list is open for dispatch" : "Awaiting approval by warehouse or finance"}
                    />
                  </StatGrid>
                ) : (
                  <Empty title="No plan generated yet">Warehouse and finance teams create plans.</Empty>
                )}
                <div className="mt-3">
                  <Link href="/compare" className="btn btn-sm">
                    Baseline comparison
                  </Link>
                </div>
              </Section>
            </>
          );
        }}
      </Stateful>

      <Section title="Stock cover by product" kicker="Fewest days of stock first">
        <StockTable
          level="sku"
          nameHeader="Product"
          caption="Stock by product"
          defaultSort={{ key: "days_of_cover", desc: false }}
          csvName="stock-by-product.csv"
        />
      </Section>

      <Section title="Warehouses that need restocking" kicker="Warehouse-product pairs running low">
        <StockTable
          level="warehouse_sku"
          nameHeader="Warehouse · product"
          caption="Warehouses running low"
          defaultFlag="low_stock"
          defaultSort={{ key: "days_of_cover", desc: false }}
        />
      </Section>

      <Section title="Alerts" kicker="Delays and expiry">
        <AlertList types={["delayed_shipment", "near_expiry", "rising_demand"]} />
      </Section>

      <Section title="Not in the current data" kicker="Gaps">
        <GapNotice
          items={[
            "Production orders, production planning and progress: VebStock models distribution, not the factory floor.",
            "Raw material availability and requirements: no bill of materials or raw material stock is stored.",
            "Quality checks: no inspection or quality records are stored.",
            "Orders received and pending quantities: the data holds forecast demand and stock plans, not customer orders.",
            "Finished-goods stock shown here is distribution stock (warehouses and stores), not factory output.",
          ]}
        />
      </Section>
    </div>
  );
}
