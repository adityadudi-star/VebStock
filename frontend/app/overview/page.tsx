"use client";

import { get } from "@/lib/api";
import { fmtKpi, KPI_META } from "@/lib/data";
import { date, dec, int, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Compare, Overview } from "@/lib/types";
import { AccuracyBars, BarsChart, TrendChart } from "@/components/charts";
import CountUp from "@/components/CountUp";
import Disclosure, { Term } from "@/components/Disclosure";
import { MetTag, SimTag, Tag } from "@/components/FlagLabel";
import { Stagger, StaggerItem } from "@/components/Motion";
import Stateful, { Empty } from "@/components/Stateful";
import { Hero, HowItWorks, PhotoStrip } from "@/components/Storytelling";
import { Section } from "@/components/ui";

const ALERT_LABELS: Record<string, string> = {
  stockout_prediction: "Likely to run out",
  low_stock: "Running low",
  near_expiry: "May expire soon",
  rising_demand: "Demand rising",
  delayed_shipment: "Shipment delayed",
};

function Headline({
  label,
  children,
  sub,
  inverted,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  sub?: React.ReactNode;
  inverted?: boolean;
}) {
  return (
    <div className={`h-full p-5 ${inverted ? "!bg-ink text-paper" : ""}`}>
      <div className={`kicker ${inverted ? "!text-paper-60" : ""}`}>{label}</div>
      <div className="serif mt-2 text-[40px] font-medium leading-none tracking-[-0.02em]">{children}</div>
      {sub ? <div className={`mt-3 text-[12.5px] leading-snug ${inverted ? "text-paper-60" : "text-ink-60"}`}>{sub}</div> : null}
    </div>
  );
}

export default function OverviewPage() {
  const ov = useApi<Overview>("overview", (s) => get<Overview>("/overview", undefined, s));
  // Target status is computed by the backend in /compare; the overview endpoint carries values only.
  const cmp = useApi<Compare>("compare-for-overview", (s) => get<Compare>("/compare", undefined, s));

  return (
    <div>
      <Hero snapshot={ov.data ? date(ov.data.as_of) : undefined} />
      <p className="mb-12 max-w-[70ch] text-[15px] leading-relaxed">
        VebStock shows where stock is, where it will be needed and which shipments to make. Start with the headline numbers below, then open any view from the menu at top left.
      </p>

      <HowItWorks />

      <Stateful state={ov} label="Loading overview">
        {(d) => {
          const inv = d.inventory;
          const th = inv.thresholds as Record<string, number | string>;
          const targets = cmp.data?.available ? cmp.data.replay?.kpis : undefined;
          const acc = d.forecast_accuracy;
          const lp = d.latest_plan;
          const fill = d.kpis_replay?.fill_rate;
          const stock = d.kpis_replay?.stockout_rate;
          const tFill = targets?.fill_rate?.target_status;
          const tStock = targets?.stockout_rate?.target_status;
          const totalAvail = (th.warehouse_available as number) + inv.available;
          return (
            <>
              <Section title="Headline numbers" kicker="Six things to know" aside={<SimTag>Simulated data</SimTag>}>
                <Stagger className="grid grid-cols-1 gap-px border border-ink-15 bg-ink-15 sm:grid-cols-2 lg:grid-cols-3 [&>*]:bg-paper">
                  <StaggerItem>
                    <Headline label="Stock you can ship or sell" sub={`${int(th.warehouse_available as number)} in warehouses, ${int(inv.available)} in stores. ${int(th.warehouse_reserved as number)} held back in warehouses.`}>
                      <CountUp value={totalAvail} format={(n) => int(n)} />
                    </Headline>
                  </StaggerItem>
                  <StaggerItem>
                    <Headline inverted label="Store-product pairs likely to run out" sub={`${int(d.alert_counts.low_stock)} more are already running low.`}>
                      <CountUp value={d.alert_counts.stockout_prediction ?? 0} format={(n) => int(n)} />
                    </Headline>
                  </StaggerItem>
                  <StaggerItem>
                    <Headline
                      label={<>Demand met from stock (<Term k="fill">fill rate</Term>)</>}
                      sub={
                        fill ? (
                          <>
                            Optimized plan, measured on simulated data. Baseline: {fmtKpi("fill_rate", fill.baseline)}.
                            <span className="mt-2 flex flex-wrap items-center gap-2">
                              <Tag tone="quiet">Target</Tag> {tFill?.target ?? "n/a"} {tFill ? <MetTag met={tFill.met} /> : null}
                            </span>
                          </>
                        ) : (
                          "No replay on file yet."
                        )
                      }
                    >
                      {fill ? <CountUp value={fill.optimized} format={(n) => `${dec(n, 1)}%`} /> : "—"}
                    </Headline>
                  </StaggerItem>
                  <StaggerItem>
                    <Headline
                      label="Stockout rate"
                      sub={
                        stock ? (
                          <>
                            Optimized plan, measured on simulated data. Baseline: {fmtKpi("stockout_rate", stock.baseline)}.
                            <span className="mt-2 flex flex-wrap items-center gap-2">
                              <Tag tone="quiet">Target</Tag> {tStock?.target ?? "n/a"} {tStock ? <MetTag met={tStock.met} /> : null}
                            </span>
                          </>
                        ) : (
                          "No replay on file yet."
                        )
                      }
                    >
                      {stock ? <CountUp value={stock.optimized} format={(n) => `${dec(n, 2)}%`} /> : "—"}
                    </Headline>
                  </StaggerItem>
                  <StaggerItem>
                    <Headline
                      label={<>Forecast miss (weekly <Term k="mape">MAPE</Term>)</>}
                      sub={
                        acc ? (
                          <>
                            Best week {dec(acc.mape_min)}%, worst week {dec(acc.mape_max)}%. <Term k="wape">WAPE</Term> {dec(acc.wape)}%.
                            <span className="mt-2 flex flex-wrap items-center gap-2">
                              <Tag tone="quiet">Target</Tag> below {dec(acc.target_mape, 0)}% <MetTag met={acc.target_met} />
                            </span>
                          </>
                        ) : (
                          "No forecast run on file."
                        )
                      }
                    >
                      {acc ? <CountUp value={acc.mape_mean} format={(n) => `${dec(n, 1)}%`} /> : "—"}
                    </Headline>
                  </StaggerItem>
                  <StaggerItem>
                    <Headline
                      label="Latest plan: time to calculate"
                      sub={
                        lp ? (
                          <>
                            Plan #{lp.id}, {lp.status}. Created {when(lp.created_at)}. Ships {int(lp.kpis.units_shipped)} units to {int(lp.kpis.stores_served)} stores.
                          </>
                        ) : (
                          "No plan generated yet. Open Distribution Plan to create one."
                        )
                      }
                    >
                      {lp ? <CountUp value={lp.kpis.solve_seconds} format={(n) => `${dec(n, 2)} s`} /> : "—"}
                    </Headline>
                  </StaggerItem>
                </Stagger>
                <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">
                  Plan figure is how long the plan took to calculate. {d.kpis_replay_label}
                </p>
              </Section>

              <Section title="Alerts at a glance" kicker="What needs attention">
                <Stagger className="grid grid-cols-2 gap-px border border-ink-15 bg-ink-15 sm:grid-cols-3 lg:grid-cols-5 [&>*]:bg-paper">
                  {Object.entries(d.alert_counts).map(([k, v]) => (
                    <StaggerItem key={k}>
                      <div className="h-full p-4">
                        <div className="kicker">{ALERT_LABELS[k] ?? k.replace(/_/g, " ")}</div>
                        <div className="serif mt-1 text-[30px] font-medium leading-none">
                          <CountUp value={v} format={(n) => int(n)} duration={0.9} />
                        </div>
                      </div>
                    </StaggerItem>
                  ))}
                </Stagger>
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

              <Section title="Demand over time" kicker="Weekly units sold" aside={<SimTag>Simulated demand</SimTag>}>
                <p className="mb-2 max-w-[70ch] text-[13.5px] text-ink-60">
                  The solid line is past sales. The dashed line is what actually sold in the simulated held-out weeks. The sage line and band are the forecast: Expected, with the Low to High range.
                </p>
                {d.charts.demand_trend.length ? <TrendChart points={d.charts.demand_trend} /> : <Empty title="No demand series" />}
              </Section>

              {d.charts.optimized_vs_baseline && d.charts.optimized_vs_baseline.length ? (
                <Section title="Optimized plan against baseline" kicker="Each measure in its own unit" aside={<SimTag>Measured on simulated data</SimTag>}>
                  <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-4">
                    {d.charts.optimized_vs_baseline
                      .filter((r) => ["fill_rate", "stockout_rate", "transport_cost", "expiry_wastage_pct"].includes(r.kpi))
                      .map((r) => (
                        <div key={r.kpi}>
                          <div className="kicker mb-1">{KPI_META[r.kpi]?.label ?? r.kpi}</div>
                          <BarsChart
                            height={150}
                            data={[
                              { name: "Baseline", v: r.baseline },
                              { name: "Optimized", v: r.optimized },
                            ]}
                            xKey="name"
                            series={[{ key: "v", name: KPI_META[r.kpi]?.label ?? r.kpi, style: "sage" }]}
                            fmt={(v) => dec(v, v >= 1000 ? 0 : 2)}
                            yWidth={56}
                          />
                        </div>
                      ))}
                  </div>
                </Section>
              ) : null}

              <PhotoStrip />

              <Disclosure>
                <div className="space-y-10">
                  <div>
                    <div className="h3 mb-2">Stock by category</div>
                    <BarsChart
                      data={d.charts.inventory_by_category}
                      xKey="category"
                      series={[
                        { key: "available", name: "Available", style: "sage" },
                        { key: "reserved", name: "Held back", style: "hatch" },
                      ]}
                    />
                  </div>
                  {acc ? (
                    <div>
                      <div className="h3 mb-2">Forecast error by week</div>
                      <AccuracyBars weeks={acc.weeks} asOf={d.as_of} />
                      <p className="mt-2 text-[12.5px] text-ink-60">{acc.note}</p>
                    </div>
                  ) : null}
                  <div className="grid gap-6 sm:grid-cols-2">
                    <dl className="text-[13px]">
                      <dt className="kicker">Store tier</dt>
                      <dd>
                        On hand {int(inv.on_hand)}, available {int(inv.available)}, held back {int(inv.reserved)}, incoming {int(inv.incoming)} across {int(inv.series)} store-product pairs.
                      </dd>
                    </dl>
                    <dl className="text-[13px]">
                      <dt className="kicker">Warehouse tier</dt>
                      <dd>
                        On hand {int(th.warehouse_on_hand as number)}, available {int(th.warehouse_available as number)}, held back {int(th.warehouse_reserved as number)}, {int(th.warehouse_expiry_risk as number)} warehouse series that may expire.
                      </dd>
                    </dl>
                    {lp ? (
                      <dl className="text-[13px]">
                        <dt className="kicker">Latest plan</dt>
                        <dd>
                          Solver status {lp.solver_status}, total cost {int(lp.total_cost)}, projected fill {dec(lp.kpis.projected_fill_rate_pct)}%.
                        </dd>
                      </dl>
                    ) : null}
                  </div>
                </div>
              </Disclosure>
            </>
          );
        }}
      </Stateful>
    </div>
  );
}
