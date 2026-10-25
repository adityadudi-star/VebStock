"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { get } from "@/lib/api";
import { date, dec, int } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import type { AlertRow, AlertType, AlertsResponse, BatchResponse, BatchRow, InventoryLevel, InventoryResponse, InventoryRow } from "@/lib/types";
import DataTable, { type Column, type SortState } from "@/components/DataTable";
import FlagLabel, { Tag } from "@/components/FlagLabel";
import Pagination from "@/components/Pagination";
import Stateful, { Empty } from "@/components/Stateful";
import { Select, Tabs, TextInput } from "@/components/ui";

/** Honest list of what the current data cannot show, so a missing figure is never mistaken for zero. */
export function GapNotice({ title = "Not available in the current data", items }: { title?: string; items: string[] }) {
  return (
    <aside className="border border-dashed border-ink-40 p-4" aria-label={title}>
      <div className="kicker !text-ink">{title}</div>
      <ul className="mt-2 max-w-[80ch] list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-ink-60">
        {items.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </aside>
  );
}

function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  // Quote, and neutralise spreadsheet formulas in text cells.
  const safe = /^[=+\-@]/.test(s) && Number.isNaN(Number(s)) ? `'${s}` : s;
  return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export function CsvButton({ filename, headers, rows, label = "Download CSV" }: { filename: string; headers: string[]; rows: (string | number | null)[][]; label?: string }) {
  const click = () => {
    const body = [headers, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([body], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <button type="button" className="btn btn-sm" onClick={click} disabled={rows.length === 0}>
      <Download aria-hidden size={13} /> {label}
    </button>
  );
}

const FLAGS = [
  { value: "low_stock", label: "Running low" },
  { value: "excess", label: "Too much stock" },
  { value: "expiry_risk", label: "May expire" },
];

/**
 * Searchable, sortable, paged stock table over GET /inventory. `locked` params are fixed by the dashboard
 * (for example the warehouse tier); the backend still decides what the caller's role may read.
 */
export function StockTable({
  level,
  locked,
  nameHeader = "Name",
  caption,
  defaultFlag = "",
  defaultSort = { key: "name", desc: false },
  pageSize = 10,
  csvName,
  onData,
}: {
  level: InventoryLevel;
  locked?: Record<string, string | number>;
  nameHeader?: string;
  caption: string;
  defaultFlag?: string;
  defaultSort?: SortState;
  pageSize?: number;
  csvName?: string;
  onData?: (d: InventoryResponse) => void;
}) {
  const [search, setSearch] = useState("");
  const [flag, setFlag] = useState(defaultFlag);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState(pageSize);
  const [sort, setSort] = useState<SortState>(defaultSort);
  const q = useDebounced(search);
  const sortParam = `${sort.desc ? "-" : ""}${sort.key}`;
  const state = useApi<InventoryResponse>(`stock:${level}:${JSON.stringify(locked)}:${q}:${flag}:${page}:${size}:${sortParam}`, (s) =>
    get<InventoryResponse>("/inventory", { level, ...locked, search: q, flag, page, page_size: size, sort: sortParam }, s).then((d) => {
      onData?.(d);
      return d;
    }),
  );
  const cols: Column<InventoryRow>[] = [
    {
      key: "name",
      header: nameHeader,
      sort: "name",
      render: (r) => (
        <div>
          <div className="font-medium">{r.name}</div>
          <div className="text-[11px] text-ink-60">
            {[r.sku_name, r.category, r.warehouse && level !== "warehouse" ? r.warehouse : null, r.region].filter(Boolean).join(" · ")}
          </div>
        </div>
      ),
    },
    { key: "available", header: "Available", align: "right", sort: "available", render: (r) => int(r.available) },
    { key: "reserved", header: "Held back", align: "right", sort: "reserved", render: (r) => int(r.reserved) },
    { key: "incoming", header: "On the way", align: "right", sort: "incoming", render: (r) => int(r.incoming) },
    { key: "cover", header: "Days of stock left", align: "right", sort: "days_of_cover", render: (r) => dec(r.days_of_cover) },
    { key: "risk", header: "Units that may expire", align: "right", sort: "qty_expiry_at_risk", render: (r) => int(r.qty_expiry_at_risk) },
    { key: "flags", header: "Status", render: (r) => <FlagLabel low={r.low_stock} excess={r.excess_stock} expiry={r.expiry_risk} /> },
  ];
  return (
    <div>
      <div className="mb-4 grid grid-cols-1 gap-3 border border-ink-15 p-3 sm:grid-cols-2">
        <TextInput label="Search" value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Name contains" />
        <Select label="Show only" value={flag} onChange={(v) => { setFlag(v); setPage(1); }} options={FLAGS} />
      </div>
      <Stateful state={state} label="Loading stock">
        {(d) =>
          d.rows.length === 0 ? (
            <Empty title="No rows match">Loosen the filter or clear the search.</Empty>
          ) : (
            <>
              <DataTable caption={caption} columns={cols} rows={d.rows} rowKey={(r) => r.key} sort={sort} onSort={(s) => { setSort(s); setPage(1); }} />
              <Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} onPageSize={(s) => { setSize(s); setPage(1); }} sizes={[10, 25, 50]} />
              {csvName ? (
                <div className="mt-3">
                  <CsvButton
                    filename={csvName}
                    headers={[nameHeader, "Available", "Held back", "On the way", "Days of stock left", "Units that may expire"]}
                    rows={d.rows.map((r) => [r.name, r.available, r.reserved, r.incoming, r.days_of_cover, r.qty_expiry_at_risk])}
                    label="Download this page as CSV"
                  />
                </div>
              ) : null}
            </>
          )
        }
      </Stateful>
    </div>
  );
}

const ALERT_TABS: { id: AlertType; label: string; valueLabel: string }[] = [
  { id: "stockout_prediction", label: "Likely to run out", valueLabel: "Days to stockout" },
  { id: "low_stock", label: "Running low", valueLabel: "Days of stock left" },
  { id: "near_expiry", label: "May expire soon", valueLabel: "Units that may expire" },
  { id: "delayed_shipment", label: "Shipment delayed", valueLabel: "Days delayed" },
  { id: "rising_demand", label: "Demand rising", valueLabel: "Forecast against recent average" },
];

/** Alerts from GET /alerts, one tab per type. For store accounts the backend returns only that store's rows. */
export function AlertList({ types, showStore = true, limit = 25, onlyStore }: { types?: AlertType[]; showStore?: boolean; limit?: number; onlyStore?: string }) {
  const tabs = ALERT_TABS.filter((t) => !types || types.includes(t.id));
  const [type, setType] = useState<AlertType>(tabs[0].id);
  const t = tabs.find((x) => x.id === type) ?? tabs[0];
  // `onlyStore` is a view filter for open demo mode; with sign-in the backend already returns only the caller's store.
  const state = useApi<AlertsResponse>(`alerts-block:${type}:${limit}:${onlyStore ?? ""}`, (s) =>
    get<AlertsResponse>("/alerts", { type, limit: onlyStore ? 500 : limit }, s).then((d) =>
      onlyStore ? { ...d, alerts: d.alerts.filter((a) => a.store === onlyStore), total: d.alerts.filter((a) => a.store === onlyStore).length } : d,
    ),
  );
  const cols: Column<AlertRow>[] = [
    { key: "sev", header: "Urgency", render: (r) => <Tag tone={r.severity === "high" ? "solid" : r.severity === "medium" ? "outline" : "quiet"}>{r.severity}</Tag> },
    ...(showStore ? ([{ key: "store", header: "Store", render: (r) => <span>{r.store}<span className="block text-[11px] text-ink-60">{r.region}</span></span> }] as Column<AlertRow>[]) : []),
    { key: "sku", header: "Product", render: (r) => <div><span className="num">{r.sku_code}</span><span className="block text-[11px] text-ink-60">{r.sku_name}</span></div> },
    { key: "msg", header: "What is happening", render: (r) => <span className="text-[12.5px]">{r.message}</span> },
    { key: "val", header: t.valueLabel, align: "right", render: (r) => (r.value === null ? "—" : dec(r.value, type === "rising_demand" ? 2 : 1)) },
  ];
  return (
    <div>
      <Tabs tabs={tabs.map((x) => ({ id: x.id, label: x.label }))} value={type} onChange={setType} />
      <Stateful state={state} label="Loading alerts" isEmpty={(d) => d.alerts.length === 0} empty={<Empty title="Nothing in this list" />}>
        {(d) => (
          <>
            <p className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">
              {int(d.total)} in total{d.total > d.alerts.length ? `, showing the ${int(d.alerts.length)} most urgent` : ""}
            </p>
            <DataTable caption={t.label} columns={cols} rows={d.alerts} rowKey={(r) => `${r.type}:${r.store}:${r.sku_code}`} />
          </>
        )}
      </Stateful>
    </div>
  );
}

/** Warehouse batches that may not sell before expiry, earliest expiry first (the FEFO dispatch queue). */
export function BatchQueue({ pageSize = 8 }: { pageSize?: number }) {
  const [page, setPage] = useState(1);
  const state = useApi<BatchResponse>(`batch-queue:${page}:${pageSize}`, (s) =>
    get<BatchResponse>("/inventory/batches", { only_risk: true, page, page_size: pageSize }, s),
  );
  const cols: Column<BatchRow>[] = [
    { key: "wh", header: "Warehouse", render: (r) => r.warehouse },
    { key: "sku", header: "Product", render: (r) => <div><span className="num">{r.sku_code}</span><span className="block text-[11px] text-ink-60">{r.sku_name}</span></div> },
    { key: "batch", header: "Batch", render: (r) => <span className="num">{r.batch_code}</span> },
    { key: "qty", header: "Units in batch", align: "right", render: (r) => int(r.qty) },
    { key: "risk", header: "Units that may expire", align: "right", render: (r) => int(r.qty_at_risk) },
    { key: "exp", header: "Expires", render: (r) => date(r.expiry_date) },
    { key: "days", header: "Days left", align: "right", render: (r) => int(r.days_to_expiry) },
  ];
  return (
    <Stateful state={state} label="Loading batches" isEmpty={(d) => d.rows.length === 0} empty={<Empty title="No batches at risk" />}>
      {(d) => (
        <>
          <DataTable caption="Batches that may expire" columns={cols} rows={d.rows} rowKey={(r) => r.batch_id} />
          <Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} />
        </>
      )}
    </Stateful>
  );
}
