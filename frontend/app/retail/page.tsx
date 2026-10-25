"use client";

import { useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { get } from "@/lib/api";
import { date, dec, int } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ForecastItem, ForecastResponse, InventoryResponse, RetailDeliveries } from "@/lib/types";
import DataTable, { type Column } from "@/components/DataTable";
import { SimTag, Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Stat, { StatGrid } from "@/components/Stat";
import Stateful, { Empty } from "@/components/Stateful";
import { Section, Select } from "@/components/ui";
import { AlertList, CsvButton, GapNotice, StockTable } from "@/components/role/blocks";

export default function RetailDashboard() {
  const { user, status } = useAuth();
  const [picked, setPicked] = useState("");
  // Signed in: the backend pins this account to one store. Open demo mode only: any store may be viewed.
  const open = status === "open";
  const stores = useApi<InventoryResponse>("retail-store-list", open ? (s) => get<InventoryResponse>("/inventory", { level: "store", page_size: 100 }, s) : null);
  const storeId = user?.store_id ? String(user.store_id) : open ? picked : "";
  const storeName = user?.store_name ?? stores.data?.rows.find((r) => r.key === picked)?.name ?? "";

  return (
    <div>
      <PageHeader
        href="/retail"
        kicker="Retail Stores workspace"
        title={storeName || "Retail Stores"}
        lede="Your store's stock, what is on its way and the products most likely to run out."
      />

      {open ? (
        <div className="mb-6 max-w-[360px]">
          <Select
            label="Demo view: choose a store"
            value={picked}
            onChange={setPicked}
            placeholder="Select a store"
            options={(stores.data?.rows ?? []).map((r) => ({ value: r.key, label: r.name }))}
          />
        </div>
      ) : null}

      {!storeId ? (
        <Empty title={open ? "Choose a store to begin" : "This account is not linked to a store"}>
          {open ? "Open demo mode has no store login." : "Ask an administrator to link your account to a store."}
        </Empty>
      ) : (
        <StoreView storeId={storeId} storeName={storeName} open={open} />
      )}
    </div>
  );
}

function StoreView({ storeId, storeName, open }: { storeId: string; storeName: string; open: boolean }) {
  const own = useApi<InventoryResponse>(`retail-own:${storeId}`, (s) => get<InventoryResponse>("/inventory", { level: "store", store_id: storeId }, s));
  const del = useApi<RetailDeliveries>(`retail-deliveries:${storeId}`, (s) => get<RetailDeliveries>("/retail/deliveries", open ? { store_id: storeId } : undefined, s));
  const fc = useApi<ForecastResponse>(`retail-forecast:${storeId}`, (s) =>
    get<ForecastResponse>("/forecast", { store_id: storeId, sort: "days_of_cover", page_size: 10 }, s),
  );

  const fcCols: Column<ForecastItem>[] = [
    { key: "sku", header: "Product", render: (r) => <div><span className="num">{r.sku_code}</span><span className="block text-[11px] text-ink-60">{r.sku_name}</span></div> },
    { key: "av", header: "Available", align: "right", render: (r) => int(r.available_stock) },
    { key: "cov", header: "Days of stock left", align: "right", render: (r) => dec(r.days_of_cover) },
    { key: "p50", header: "Expected sales, next 7 days", align: "right", render: (r) => int(r.horizons.find((h) => h.horizon_days === 7)?.p50) },
    { key: "so", header: "Likely to run out", render: (r) => (r.predicted_stockout_date ? date(r.predicted_stockout_date) : <span className="text-ink-40">Not within 30 days</span>) },
  ];

  return (
    <>
      <Section title="Your store today" kicker="Stock position" aside={<SimTag>Simulated data</SimTag>}>
        <Stateful state={own} label="Loading your store" isEmpty={(d) => d.rows.length === 0} empty={<Empty title="No stock records for this store" />}>
          {(d) => {
            const r = d.rows[0];
            return (
              <StatGrid cols={4}>
                <Stat label="Available to sell" value={int(r.available)} sub={`${int(r.on_hand)} in stock, ${int(r.reserved)} held back`} />
                <Stat label="On the way" value={int(r.incoming)} sub="units in transit to your store" />
                <Stat label="Products running low" value={int(r.n_low_stock)} sub={`of ${int(r.n_series)} products you stock`} inverted />
                <Stat label="Units that may expire" value={int(r.qty_expiry_at_risk)} sub={`${int(r.n_expiry_risk)} products affected`} />
              </StatGrid>
            );
          }}
        </Stateful>
      </Section>

      <Section title="Products to reorder first" kicker="Fewest days of stock left">
        <Stateful state={fc} label="Loading forecast" isEmpty={(d) => d.items.length === 0} empty={<Empty title="No forecast for this store" />}>
          {(d) => <DataTable caption="Products to reorder first" columns={fcCols} rows={d.items} rowKey={(r) => r.sku_id} />}
        </Stateful>
      </Section>

      <Section title="Incoming deliveries" kicker="Shipments on their way and planned replenishment">
        <Stateful state={del} label="Loading deliveries">
          {(d) => (
            <div className="space-y-8">
              <div>
                <div className="h3 mb-2">On the way now</div>
                {d.incoming.length === 0 ? (
                  <Empty title="Nothing in transit" />
                ) : (
                  <>
                    <DataTable
                      caption="Shipments in transit"
                      rows={d.incoming}
                      rowKey={(r) => `${r.sku_code}:${r.eta_date}`}
                      columns={[
                        { key: "sku", header: "Product", render: (r) => <div><span className="num">{r.sku_code}</span><span className="block text-[11px] text-ink-60">{r.sku_name}</span></div> },
                        { key: "qty", header: "Units", align: "right", render: (r) => int(r.qty) },
                        { key: "eta", header: "Arrives", render: (r) => date(r.eta_date) },
                        { key: "st", header: "Status", render: (r) => (r.delay_days > 0 ? <Tag tone="solid">Delayed {r.delay_days} days</Tag> : <Tag tone="outline">On time</Tag>) },
                      ]}
                    />
                    <div className="mt-3">
                      <CsvButton
                        filename="incoming-deliveries.csv"
                        headers={["Product code", "Product", "Units", "Arrives", "Delay (days)"]}
                        rows={d.incoming.map((r) => [r.sku_code, r.sku_name, r.qty, r.eta_date, r.delay_days])}
                      />
                    </div>
                  </>
                )}
              </div>
              <div>
                <div className="h3 mb-2">Approved replenishment plan</div>
                {!d.approved_plan ? (
                  <Empty title="No approved plan yet">Shipments appear here once the warehouse team approves a plan.</Empty>
                ) : d.planned_lines.length === 0 ? (
                  <Empty title={`Plan #${d.approved_plan.id} sends nothing to your store`} />
                ) : (
                  <DataTable
                    caption="Approved plan lines"
                    rows={d.planned_lines}
                    rowKey={(r) => `${r.sku_code}:${r.warehouse}:${r.qty}`}
                    columns={[
                      { key: "sku", header: "Product", render: (r) => <div><span className="num">{r.sku_code}</span><span className="block text-[11px] text-ink-60">{r.sku_name}</span></div> },
                      { key: "qty", header: "Units", align: "right", render: (r) => int(r.qty) },
                      { key: "wh", header: "Shipped from", render: (r) => r.warehouse },
                      { key: "lt", header: "Transit time", align: "right", render: (r) => (r.lead_time_days === null ? "—" : `${r.lead_time_days} days`) },
                    ]}
                  />
                )}
              </div>
            </div>
          )}
        </Stateful>
      </Section>

      <Section title="Your stock" kicker={storeName || "Every product in your store"}>
        <StockTable level="store_sku" locked={{ store_id: storeId }} nameHeader="Product" caption="Your store stock" defaultSort={{ key: "days_of_cover", desc: false }} csvName="my-store-stock.csv" />
      </Section>

      <Section title="Alerts for your store" kicker="Needs attention">
        <AlertList types={["stockout_prediction", "low_stock", "near_expiry", "delayed_shipment"]} showStore={false} onlyStore={open ? storeName : undefined} />
      </Section>

      <Section title="Not in the current data" kicker="Gaps">
        <GapNotice
          items={[
            "Placing orders or stock requests: the system plans replenishment centrally, so stores cannot raise orders here yet.",
            "Order history, invoices and payment status: no orders, invoices or payments are stored.",
            "Returns and damaged-stock reporting: no returns records exist.",
            "Store sales history is used for forecasting but is not shown as a sales report.",
          ]}
        />
      </Section>
    </>
  );
}
