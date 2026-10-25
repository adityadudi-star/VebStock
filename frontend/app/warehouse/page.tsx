"use client";

import { get } from "@/lib/api";
import { date, int } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Overview } from "@/lib/types";
import { BarsChart } from "@/components/charts";
import { SimTag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Stat, { StatGrid } from "@/components/Stat";
import Stateful from "@/components/Stateful";
import { Section } from "@/components/ui";
import PlanQueue from "@/components/role/PlanQueue";
import { AlertList, BatchQueue, GapNotice, StockTable } from "@/components/role/blocks";

export default function WarehouseDashboard() {
  const ov = useApi<Overview>("overview", (s) => get<Overview>("/overview", undefined, s));
  return (
    <div>
      <PageHeader
        href="/warehouse"
        kicker="Warehouse & Dispatch workspace"
        title="Warehouse & Dispatch"
        lede="Stock in every warehouse, the batches to move first, and the plans waiting to be approved, picked and dispatched."
      />

      <Stateful state={ov} label="Loading warehouse position">
        {(d) => {
          const th = d.inventory.thresholds as Record<string, number | string>;
          const a = d.alert_counts;
          return (
            <>
              <Section title="Warehouse position" kicker="Right now" aside={<SimTag>Simulated data</SimTag>}>
                <StatGrid cols={4}>
                  <Stat label="Available to ship" value={int(th.warehouse_available as number)} sub={`${int(th.warehouse_on_hand as number)} in stock, ${int(th.warehouse_reserved as number)} held back`} />
                  <Stat label="Warehouse stock that may expire" value={int(th.warehouse_expiry_risk as number)} sub="warehouse-product pairs at risk" inverted />
                  <Stat label="Store-product pairs likely to run out" value={int(a.stockout_prediction ?? 0)} sub={`${int(a.low_stock ?? 0)} more running low`} />
                  <Stat label="Shipments delayed" value={int(a.delayed_shipment ?? 0)} sub={`snapshot ${date(d.as_of)}`} />
                </StatGrid>
              </Section>

              <Section title="Stock by warehouse" kicker="Units: available against held back">
                <BarsChart
                  data={d.charts.inventory_by_warehouse}
                  xKey="warehouse"
                  stacked
                  series={[
                    { key: "available", name: "Available", style: "ink" },
                    { key: "reserved", name: "Held back", style: "hatch" },
                  ]}
                />
              </Section>
            </>
          );
        }}
      </Stateful>

      <Section title="Plans waiting for dispatch" kicker="Approve, then pick">
        <PlanQueue
          links={[
            { href: "/plan", label: "Open Distribution Plan" },
            { href: "/alerts", label: "Pick lists and lane load" },
          ]}
        />
      </Section>

      <Section title="Move these batches first" kicker="Earliest expiry first">
        <BatchQueue />
      </Section>

      <Section title="Warehouse stock" kicker="Every warehouse-product pair">
        <StockTable
          level="warehouse_sku"
          nameHeader="Warehouse · product"
          caption="Warehouse stock"
          defaultFlag="low_stock"
          defaultSort={{ key: "days_of_cover", desc: false }}
          csvName="warehouse-stock.csv"
        />
      </Section>

      <Section title="Alerts" kicker="Exceptions that need action">
        <AlertList types={["stockout_prediction", "low_stock", "delayed_shipment", "near_expiry"]} />
      </Section>

      <Section title="Not in the current data" kicker="Gaps">
        <GapNotice
          items={[
            "Goods receipts and purchase orders: only supplier delay events and store-bound shipments are stored, so incoming warehouse receipts cannot be listed.",
            "Stock transfers between warehouses and manual inventory adjustments are not recorded.",
            "Shipment tracking beyond the planned lane lead time and the in-transit status.",
            "Stock counts, so inventory discrepancies cannot be detected.",
          ]}
        />
      </Section>
    </div>
  );
}
