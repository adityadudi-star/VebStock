"use client";

import { useState } from "react";
import { get } from "@/lib/api";
import { REGIONS, useMeta } from "@/lib/data";
import { date, dec, int } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { BatchResponse, BatchRow, InventoryResponse, InventoryRow } from "@/lib/types";
import DataTable, { Column, SortState } from "@/components/DataTable";
import Disclosure from "@/components/Disclosure";
import FlagLabel, { Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Pagination from "@/components/Pagination";
import Stat, { StatGrid } from "@/components/Stat";
import Stateful, { Empty } from "@/components/Stateful";
import { Select, Tabs, TextInput, Toggle } from "@/components/ui";

const LEVELS = [
  { value: "warehouse", label: "By warehouse" },
  { value: "store", label: "By store" },
  { value: "sku", label: "By product" },
  { value: "region", label: "By region" },
  { value: "distributor", label: "By distributor" },
  { value: "store_sku", label: "Store and product" },
  { value: "warehouse_sku", label: "Warehouse and product" },
];

interface Q {
  level: string;
  product: string;
  region: string;
  date: string;
  flag: string;
  search: string;
  warehouse: string;
  page: number;
  pageSize: number;
  sort: SortState;
}

export default function InventoryPage() {
  const [tab, setTab] = useState<"levels" | "batches">("levels");
  return (
    <div>
      <PageHeader
        href="/inventory"
        lede="See how much stock you have, where it sits and what may expire. Pick a view, then use the filters to find a store, product or warehouse."
      />
      <Tabs
        tabs={[
          { id: "levels", label: "Stock levels" },
          { id: "batches", label: "Batches and expiry dates" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "levels" ? <Levels /> : <Batches />}
    </div>
  );
}

function Levels() {
  const meta = useMeta();
  const [q, setQ] = useState<Q>({
    level: "warehouse",
    product: "",
    region: "",
    date: "",
    flag: "",
    search: "",
    warehouse: "",
    page: 1,
    pageSize: 25,
    sort: { key: "name", desc: false },
  });
  const upd = (p: Partial<Q>) => setQ((o) => ({ ...o, page: 1, ...p }));
  const search = useDebounced(q.search);
  const product = useDebounced(q.product);
  const sortParam = `${q.sort.desc ? "-" : ""}${q.sort.key}`;
  const key = JSON.stringify({ ...q, search, product, sort: sortParam });
  const state = useApi<InventoryResponse>(`inv:${key}`, (signal) =>
    get<InventoryResponse>(
      "/inventory",
      {
        level: q.level,
        product,
        region: q.region,
        date: q.date,
        flag: q.flag,
        search,
        warehouse_id: q.warehouse,
        page: q.page,
        page_size: q.pageSize,
        sort: sortParam,
      },
      signal,
    ),
  );

  const [extra, setExtra] = useState(false);
  const cols: Column<InventoryRow>[] = [
    {
      key: "name",
      header: "Name",
      sort: "name",
      render: (r) => (
        <div>
          <div className="font-medium">{r.name}</div>
          <div className="text-[11px] text-ink-60">
            {[r.store && r.level !== "store" ? r.store : null, r.sku_name, r.category, r.warehouse && r.level !== "warehouse" ? r.warehouse : null, r.region, r.distributor]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </div>
      ),
    },
    { key: "on_hand", header: "In stock", align: "right", sort: "on_hand", render: (r) => int(r.on_hand) },
    { key: "reserved", header: "Held back", align: "right", sort: "reserved", render: (r) => int(r.reserved) },
    { key: "available", header: "Available", align: "right", sort: "available", render: (r) => int(r.available) },
    { key: "cover", header: "Days of stock left", align: "right", sort: "days_of_cover", render: (r) => dec(r.days_of_cover) },
    { key: "risk", header: "Units that may expire", align: "right", sort: "qty_expiry_at_risk", render: (r) => int(r.qty_expiry_at_risk) },
    {
      key: "flags",
      header: "Status",
      render: (r) => (
        <div className="space-y-1">
          <FlagLabel low={r.low_stock} excess={r.excess_stock} expiry={r.expiry_risk} />
          {r.n_series > 1 ? (
            <div className="num text-[10.5px] text-ink-60">
              {r.n_low_stock} low · {r.n_excess} too much · {r.n_expiry_risk} may expire (of {r.n_series})
            </div>
          ) : null}
        </div>
      ),
    },
    ...(extra
      ? ([
          { key: "incoming", header: "On the way", align: "right", sort: "incoming", render: (r) => int(r.incoming) },
          { key: "daily", header: "Sold per day", align: "right", sort: "avg_daily_demand", render: (r) => dec(r.avg_daily_demand, 1) },
          { key: "expiry", header: "Earliest expiry", sort: "nearest_expiry", render: (r) => date(r.nearest_expiry) },
        ] as Column<InventoryRow>[])
      : []),
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] uppercase tracking-[0.08em]">
        {LEVELS.map((l) => (
          <button
            key={l.value}
            type="button"
            onClick={() => upd({ level: l.value, sort: { key: "name", desc: false } })}
            aria-pressed={q.level === l.value}
            className={`border-b-2 pb-1 ${q.level === l.value ? "border-ink font-medium" : "border-transparent text-ink-60 hover:border-ink-40"}`}
          >
            {l.label}
          </button>
        ))}
      </div>

      <div className="mb-5 grid grid-cols-2 gap-3 border border-ink-15 p-3 md:grid-cols-3 lg:grid-cols-6">
        <TextInput label="Product (code or category)" value={q.product} onChange={(v) => upd({ product: v })} placeholder="SKU0012 or Dairy" />
        <Select label="Region" value={q.region} onChange={(v) => upd({ region: v })} options={REGIONS.map((r) => ({ value: r, label: r }))} />
        <Select
          label="Warehouse"
          value={q.warehouse}
          onChange={(v) => upd({ warehouse: v })}
          options={(meta.data?.warehouses ?? []).map((w) => ({ value: String(w.id), label: w.name }))}
        />
        <TextInput label="Check expiry as of" type="date" value={q.date} onChange={(v) => upd({ date: v })} />
        <Select
          label="Show only"
          value={q.flag}
          onChange={(v) => upd({ flag: v })}
          options={[
            { value: "low_stock", label: "Running low" },
            { value: "excess", label: "Too much stock" },
            { value: "expiry_risk", label: "May expire" },
          ]}
        />
        <TextInput label="Search" value={q.search} onChange={(v) => upd({ search: v })} placeholder="Name contains" />
      </div>

      {state.data ? (
        <p className="-mt-2 mb-4 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">
          Expiry is checked as of the simulated snapshot ({date(state.data.as_of)}) unless you pick another date.
        </p>
      ) : null}
      <Stateful state={state} label="Loading inventory">
        {(d) => (
          <>
            <StatGrid cols={4}>
              <Stat label="In stock (stores)" value={int(d.summary.on_hand)} sub={`${int(d.summary.reserved)} held back`} />
              <Stat label="Available (stores)" value={int(d.summary.available)} sub={`${int(d.summary.incoming)} on the way`} />
              <Stat label="Running low" value={int(d.summary.low_stock_series)} sub={`of ${int(d.summary.series)} store-product pairs`} />
              <Stat
                label="Too much / may expire"
                value={`${int(d.summary.excess_series)} / ${int(d.summary.expiry_risk_series)}`}
                sub={`simulated snapshot ${date(d.as_of)}`}
              />
            </StatGrid>
            <div className="mt-6">
              {d.rows.length === 0 ? (
                <Empty title="No rows match these filters">Loosen a filter or clear the search.</Empty>
              ) : (
                <DataTable
                  caption="Inventory"
                  columns={cols}
                  rows={d.rows}
                  rowKey={(r) => r.key}
                  sort={q.sort}
                  onSort={(s) => upd({ sort: s })}
                />
              )}
              <Pagination
                page={d.page}
                pageSize={d.page_size}
                total={d.total}
                onPage={(p) => setQ((o) => ({ ...o, page: p }))}
                onPageSize={(s) => upd({ pageSize: s })}
              />
            </div>
            <Disclosure>
              <div className="mb-3">
                <Toggle label="Show extra columns (on the way, sold per day, earliest expiry)" checked={extra} onChange={setExtra} />
              </div>
              <p className="max-w-[80ch] text-[12.5px] text-ink-60">
                Status rules: {String(d.summary.thresholds.expiry_risk_rule)}. Store thresholds: running low under {String(d.summary.thresholds.store_low_days)} days of stock left, too much over {String(d.summary.thresholds.store_excess_days)} days. Warehouse thresholds: {String(d.summary.thresholds.warehouse_low_days)} and {String(d.summary.thresholds.warehouse_excess_days)} days. Computed in {dec(d.elapsed_ms, 0)} ms.
              </p>
            </Disclosure>
          </>
        )}
      </Stateful>
    </div>
  );
}

function Batches() {
  const meta = useMeta();
  const [wh, setWh] = useState("");
  const [onlyRisk, setOnlyRisk] = useState(false);
  const [product, setProduct] = useState("");
  const [asOf, setAsOf] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const prod = useDebounced(product);
  const state = useApi<BatchResponse>(`batches:${wh}:${onlyRisk}:${prod}:${asOf}:${page}:${pageSize}`, (signal) =>
    get<BatchResponse>(
      "/inventory/batches",
      { warehouse_id: wh, only_risk: onlyRisk, product: prod, date: asOf, page, page_size: pageSize },
      signal,
    ),
  );
  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };

  const cols: Column<BatchRow>[] = [
    { key: "code", header: "Batch", render: (r) => <span className="num">{r.batch_code}</span> },
    { key: "wh", header: "Warehouse", render: (r) => r.warehouse },
    {
      key: "sku",
      header: "Product",
      render: (r) => (
        <div>
          <div className="num">{r.sku_code}</div>
          <div className="text-[11px] text-ink-60">
            {r.sku_name} · {r.category}
          </div>
        </div>
      ),
    },
    { key: "qty", header: "Units", align: "right", render: (r) => int(r.qty) },
    {
      key: "exp",
      header: "Expires on",
      render: (r) => (
        <div>
          {date(r.expiry_date)}
          <span className="block text-[11px] text-ink-60">{int(r.days_to_expiry)} days left</span>
        </div>
      ),
    },
    { key: "risk", header: "Units that may expire", align: "right", render: (r) => int(r.qty_at_risk) },
    { key: "flag", header: "Status", render: (r) => (r.expiry_risk ? <Tag tone="solid">May expire</Tag> : <span className="text-ink-40">OK</span>) },
  ];

  return (
    <div>
      <div className="mb-5 grid grid-cols-2 items-end gap-3 border border-ink-15 p-3 md:grid-cols-4">
        <Select
          label="Warehouse"
          value={wh}
          onChange={reset(setWh)}
          options={(meta.data?.warehouses ?? []).map((w) => ({ value: String(w.id), label: w.name }))}
        />
        <TextInput label="Product (code or category)" value={product} onChange={reset(setProduct)} />
        <TextInput label="Check expiry as of" type="date" value={asOf} onChange={reset(setAsOf)} />
        <div className="pb-2">
          <Toggle label="Only batches that may expire" checked={onlyRisk} onChange={reset(setOnlyRisk)} />
        </div>
      </div>
      <p className="mb-3 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">Earliest expiry first, so the oldest stock is at the top.</p>
      <Stateful state={state} label="Loading batches">
        {(d) =>
          d.rows.length === 0 ? (
            <Empty title="No batches match">Turn off the filter for batches that may expire, or pick another warehouse.</Empty>
          ) : (
            <>
              <DataTable caption="Batches" columns={cols} rows={d.rows} rowKey={(r) => r.batch_id} />
              <Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} onPageSize={reset(setPageSize)} />
            </>
          )
        }
      </Stateful>
    </div>
  );
}
