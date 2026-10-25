"use client";

import { useState } from "react";
import { get } from "@/lib/api";
import { REGIONS, useMeta } from "@/lib/data";
import { addDays, date, dec, int } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { ForecastAccuracy, ForecastItem, ForecastResponse } from "@/lib/types";
import { AccuracyBars, TrendChart } from "@/components/charts";
import DataTable, { Column } from "@/components/DataTable";
import Disclosure, { Term } from "@/components/Disclosure";
import { MetTag, SimTag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Pagination from "@/components/Pagination";
import Stat from "@/components/Stat";
import Stateful, { Empty } from "@/components/Stateful";
import { Section, Select } from "@/components/ui";

const SORTS = [
  { value: "days_of_cover", label: "Running out soonest" },
  { value: "-p50_7", label: "Highest expected demand, next 7 days" },
  { value: "-uncertainty", label: "Least certain forecast" },
  { value: "-safety_stock", label: "Largest safety stock" },
];

export default function ForecastPage() {
  const meta = useMeta();
  const [region, setRegion] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("days_of_cover");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [sel, setSel] = useState<{ store: number; sku: number } | null>(null);

  const list = useApi<ForecastResponse>(`fc:${region}:${category}:${sort}:${page}:${pageSize}`, (signal) =>
    get<ForecastResponse>("/forecast", { region, category, sort, page, page_size: pageSize }, signal),
  );
  const detail = useApi<ForecastResponse>(
    `fcd:${sel?.store}:${sel?.sku}`,
    sel
      ? (signal) =>
          get<ForecastResponse>("/forecast", { store_id: sel.store, sku_id: sel.sku, include_series: true }, signal)
      : null,
  );
  const reset = (set: (v: string) => void) => (v: string) => {
    set(v);
    setPage(1);
  };

  const cols: Column<ForecastItem>[] = [
    { key: "store", header: "Store", render: (r) => <span>{r.store}<span className="block text-[11px] text-ink-60">{r.region}</span></span> },
    {
      key: "sku",
      header: "Product",
      render: (r) => (
        <div>
          <div>{r.sku_name}</div>
          <div className="num text-[11px] text-ink-60">{r.sku_code} · {r.category}</div>
        </div>
      ),
    },
    { key: "stock", header: "In stock now", align: "right", render: (r) => int(r.available_stock) },
    { key: "p50", header: "Expected sales, next 7 days", align: "right", render: (r) => dec(r.horizons.find((h) => h.horizon_days === 7)?.p50) },
    { key: "so", header: "Expected to run out", render: (r) => (r.predicted_stockout_date ? date(r.predicted_stockout_date) : "Not soon") },
  ];

  const acc: ForecastAccuracy | undefined = list.data?.accuracy ?? detail.data?.accuracy;

  return (
    <div>
      <PageHeader
        href="/forecast"
        lede="See how much of each product every store is expected to sell and when it may run out. Click a row to open its forecast."
      />

      <Section title="How accurate is the forecast?" kicker="Measured on simulated held-out weeks" aside={<SimTag>Simulated</SimTag>}>
        {acc ? (
          <Accuracy acc={acc} asOf={(list.data ?? detail.data)?.as_of} />
        ) : (
          <Stateful state={list} label="Loading accuracy">
            {() => null}
          </Stateful>
        )}
      </Section>

      <Section title="Store and product forecasts" kicker="Click a row to see its forecast">
        <div className="mb-4 grid grid-cols-2 gap-3 border border-ink-15 p-3 md:grid-cols-4">
          <Select label="Region" value={region} onChange={reset(setRegion)} options={REGIONS.map((r) => ({ value: r, label: r }))} />
          <Select
            label="Category"
            value={category}
            onChange={reset(setCategory)}
            options={(meta.data?.categories_list ?? []).map((c) => ({ value: c, label: c }))}
          />
          <Select label="Show first" value={sort} onChange={reset(setSort)} options={SORTS} placeholder={null} />
        </div>
        <Stateful state={list} label="Loading forecasts">
          {(d) =>
            d.items.length === 0 ? (
              <Empty title="No forecasts match these filters">Try another region or category.</Empty>
            ) : (
              <>
                <DataTable
                  caption="Forecasts"
                  columns={cols}
                  rows={d.items}
                  rowKey={(r) => `${r.store_id}-${r.sku_id}`}
                  selectedKey={sel ? `${sel.store}-${sel.sku}` : null}
                  onRowClick={(r) => setSel({ store: r.store_id, sku: r.sku_id })}
                />
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
            )
          }
        </Stateful>
      </Section>

      <Section title="Selected forecast" kicker={sel ? "Store and product detail" : "Nothing selected"}>
        {!sel ? (
          <Empty title="Select a row above">The expected demand, the run-out date and the weekly chart appear here.</Empty>
        ) : (
          <Stateful state={detail} label="Loading forecast detail">
            {(d) => {
              const it = d.items[0];
              if (!it) return <Empty title="No forecast returned for this pair" />;
              return (
                <div>
                  <p className="serif max-w-[40ch] text-[26px] leading-snug sm:text-[32px]">
                    {it.predicted_stockout_date
                      ? `${it.store} is expected to run out of ${it.sku_name} around ${date(it.predicted_stockout_date)}.`
                      : `${it.store} is not expected to run out of ${it.sku_name} within the forecast window.`}
                  </p>
                  <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.08em] text-ink-60">
                    {it.sku_code} · {it.category} · {it.region}
                  </p>
                  <div className="mt-5 grid gap-px border border-ink-15 bg-ink-15 sm:grid-cols-3 [&>*]:bg-paper">
                    <Stat label="In stock now" value={int(it.available_stock)} sub={`sells about ${dec(it.avg_daily_demand, 1)} a day`} />
                    <Stat label={<Term k="cover" />} value={dec(it.days_of_cover)} />
                    <Stat
                      label="Expected to run out"
                      value={it.predicted_stockout_date ? date(it.predicted_stockout_date) : "Not soon"}
                      sub={it.stockout_within_days != null ? `in ${dec(it.stockout_within_days)} days` : undefined}
                      inverted={it.stockout_within_days != null && it.stockout_within_days <= 3}
                    />
                  </div>
                  <div className="mt-6 overflow-x-auto" data-lenis-prevent>
                    <table className="tbl">
                      <caption className="sr-only">Expected demand</caption>
                      <thead>
                        <tr>
                          <th>Demand over the next</th>
                          <th className="r">Low</th>
                          <th className="r">Expected</th>
                          <th className="r">High</th>
                        </tr>
                      </thead>
                      <tbody>
                        {it.horizons.map((h) => (
                          <tr key={h.horizon_days}>
                            <td>{h.horizon_days} days</td>
                            <td className="r num">{dec(h.p10)}</td>
                            <td className="r num font-medium">{dec(h.p50)}</td>
                            <td className="r num">{dec(h.p90)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-2 text-[12.5px] text-ink-60">Low and High are the 10th and 90th percentile (P10, P90): demand should land between them about 80% of the time.</p>
                  <div className="mt-8">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className="kicker">Weekly units</span>
                      <SimTag>Simulated demand</SimTag>
                    </div>
                    {d.series && d.series.length ? <TrendChart points={d.series} /> : <Empty title="No weekly series returned" />}
                  </div>
                  <Disclosure title="How the safety stock was set">
                    <p className="max-w-[80ch] text-[13.5px] leading-relaxed">{it.safety_stock_explanation}</p>
                    <table className="tbl mt-4 max-w-md">
                      <thead>
                        <tr>
                          <th>Horizon</th>
                          <th className="r">
                            <Term k="safety" />
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {it.horizons.map((h) => (
                          <tr key={h.horizon_days}>
                            <td>{h.horizon_days} days</td>
                            <td className="r num">{dec(h.safety_stock)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="mt-3 text-[12.5px] text-ink-60">Uncertainty ratio over 7 days: {dec(it.uncertainty_ratio_7d, 2)} (High minus Low, divided by Expected).</p>
                  </Disclosure>
                </div>
              );
            }}
          </Stateful>
        )}
      </Section>
    </div>
  );
}

function Accuracy({ acc, asOf }: { acc: ForecastAccuracy; asOf?: string }) {
  return (
    <div>
      <div className="grid gap-px border border-ink bg-ink sm:grid-cols-2 lg:grid-cols-4 [&>*]:bg-paper">
        <Stat label={<>Average weekly miss (<Term k="mape">MAPE</Term>)</>} value={`${dec(acc.mape_mean)}%`} sub={`best week ${dec(acc.mape_min)}% · worst week ${dec(acc.mape_max)}%`} />
        <Stat label={<>Total miss (<Term k="wape">WAPE</Term>)</>} value={`${dec(acc.wape)}%`} sub="across all units sold" />
        <Stat label="Sales inside the Low–High range" value={`${dec(acc.coverage_p10_p90)}%`} sub="about 80% is ideal" />
        <div className="p-4">
          <div className="kicker">Target</div>
          <div className="serif mt-1 text-[30px] font-medium leading-none">&lt; {dec(acc.target_mape, 0)}%</div>
          <div className="mt-2">
            <MetTag met={acc.target_met} />
          </div>
        </div>
      </div>
      <p className="mt-3 max-w-[90ch] text-[13.5px] leading-relaxed">{acc.note}</p>
      <Disclosure title="Technical details: error week by week">
        <div className="kicker mb-1">
          MAPE and WAPE per week, {acc.weeks.length} rolling-origin weeks (run {acc.run_id}, mode {acc.mode})
          {asOf ? `. Weeks run from ${date(asOf)} to ${date(addDays(asOf, 7 * acc.weeks.length - 1))}.` : ""}
        </div>
        <AccuracyBars weeks={acc.weeks} asOf={asOf} />
      </Disclosure>
    </div>
  );
}
