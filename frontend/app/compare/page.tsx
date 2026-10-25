"use client";

import { get } from "@/lib/api";
import { fmtKpi, KPI_META } from "@/lib/data";
import { dec, int, signed, signedPct, when } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Compare } from "@/lib/types";
import { BarsChart } from "@/components/charts";
import Disclosure from "@/components/Disclosure";
import { MetTag, SimTag, Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Stateful, { Empty } from "@/components/Stateful";
import { Section } from "@/components/ui";

const ORDER = ["stockout_rate", "fill_rate", "transport_cost", "expiry_wastage_pct", "weekly_mape", "plan_seconds_mean"];
const PLAIN: Record<string, string> = {
  stockout_rate: "Stockout rate",
  fill_rate: "Demand met from stock (fill rate)",
  transport_cost: "Transport cost",
  expiry_wastage_pct: "Stock wasted to expiry (headline %)",
  weekly_mape: "Forecast miss (weekly MAPE)",
  plan_seconds_mean: "Time to calculate one plan",
};

const SHORT: Record<string, string> = {
  stockout_rate: "stockout rate",
  fill_rate: "demand met from stock",
  transport_cost: "transport cost",
  expiry_wastage_pct: "headline expiry wastage",
  weekly_mape: "forecast miss",
};

function stats(v: (number | null)[] | undefined) {
  const x = (v ?? []).filter((n): n is number => typeof n === "number");
  if (!x.length) return null;
  return { mean: x.reduce((a, b) => a + b, 0) / x.length, min: Math.min(...x), max: Math.max(...x) };
}

export default function ComparePage() {
  const state = useApi<Compare>("compare", (s) => get<Compare>("/compare", undefined, s));
  return (
    <div>
      <PageHeader
        href="/compare"
        lede="See whether the optimized plan beats a simple reorder-point baseline. Both were replayed day by day on the same simulated demand. Read the tick or cross to see if each goal was reached."
      />
      <Stateful state={state} label="Loading comparison">
        {(d) => {
          if (!d.available || !d.replay) {
            return (
              <div>
                <Empty title="Comparison not available yet">{d.message ?? "The backend reports no comparison run."}</Empty>
                <div className="mt-8">
                  <div className="kicker mb-2">Goals this comparison will be checked against</div>
                  <ul className="border-t border-ink-15">
                    {Object.entries(d.targets).map(([k, v]) => (
                      <li key={k} className="grid gap-1 border-b border-ink-15 py-2 text-[13.5px] sm:grid-cols-[18rem_1fr]">
                        <span>{PLAIN[k] ?? k.replace(/_/g, " ")}</span>
                        <span className="num">{v}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            );
          }
          const r = d.replay;
          const kpis = r.kpis;
          const keys = ORDER.filter((k) => kpis[k]);

          const judged = keys.filter((k) => k !== "plan_seconds_mean");
          const better: string[] = [];
          const worse: string[] = [];
          const same: string[] = [];
          for (const k of judged) {
            const diff = kpis[k].abs_diff;
            const lower = KPI_META[k].lowerIsBetter;
            const name = SHORT[k];
            if (diff === 0) same.push(name);
            else if ((diff < 0) === lower) better.push(name);
            else worse.push(name);
          }
          const statusKeys = keys.filter((k) => kpis[k].target_status);
          const met = statusKeys.filter((k) => kpis[k].target_status.met).length;
          const mixed = better.length > 0 && worse.length > 0;

          const seeds = r.per_seed;
          const expU = stats(seeds.map((s) => s.optimized.expired_units as number));
          const expUb = stats(seeds.map((s) => s.baseline.expired_units as number));
          const whU = stats(seeds.map((s) => s.optimized.expired_units_warehouse as number));
          const whUb = stats(seeds.map((s) => s.baseline.expired_units_warehouse as number));
          const stU = stats(seeds.map((s) => s.optimized.expired_units_store as number));
          const stUb = stats(seeds.map((s) => s.baseline.expired_units_store as number));
          const totalWorse = expU && expUb ? expU.mean > expUb.mean : false;

          const techRows = [
            { label: "Expired units, total", b: expUb, o: expU },
            { label: "Expired units, in stores", b: stUb, o: stU },
            { label: "Expired units, in warehouses", b: whUb, o: whU },
            { label: "Expiry value written off", b: stats(seeds.map((s) => s.baseline.expiry_value as number)), o: stats(seeds.map((s) => s.optimized.expiry_value as number)) },
          ];

          return (
            <>
              <div className="mb-8 border border-ink p-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <SimTag>Simulated</SimTag>
                  <Tag tone="outline">
                    Measured over {r.seeds.length} {r.seeds.length === 1 ? "run" : "runs"} (seeds {r.seeds.join(", ")})
                  </Tag>
                  <Tag tone="quiet">{r.window_days}-day simulated window</Tag>
                </div>
                <p className="text-[13.5px] leading-relaxed">{d.labels.replay}</p>
                <p className="mt-2 text-[13px] leading-relaxed text-ink-60">{d.labels.targets}</p>
                {d.labels.plan_projection ? <p className="mt-2 text-[13px] leading-relaxed text-ink-60">{d.labels.plan_projection}</p> : null}
                <p className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-60">{r.label}. Replay run {when(r.created_at)}.</p>
              </div>

              <Section title="The short version" kicker="Honest summary">
                <p className="serif max-w-[75ch] text-[22px] leading-snug">
                  {mixed ? "A mixed result. " : better.length ? "Better on every measure. " : worse.length ? "Worse on every measure. " : "No change. "}
                  {better.length ? `The optimized plan was better on ${better.join(", ")}. ` : ""}
                  {worse.length ? `It was worse on ${worse.join(", ")}. ` : ""}
                  {same.length ? `It was unchanged on ${same.join(", ")}. ` : ""}
                  {`${met} of ${statusKeys.length} goals were reached.`}
                </p>
              </Section>

              <Section title="Goal by goal" kicker="Baseline against optimized" aside={<SimTag>Measured on simulated data</SimTag>}>
                <div className="overflow-x-auto" data-lenis-prevent>
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Measure</th>
                        <th className="r">Baseline</th>
                        <th className="r">Optimized</th>
                        <th className="r">Change</th>
                        <th>Goal</th>
                        <th>Reached?</th>
                      </tr>
                    </thead>
                    <tbody>
                      {keys.map((k) => {
                        const v = kpis[k];
                        return (
                          <tr key={k}>
                            <td className="font-medium">{PLAIN[k]}</td>
                            <td className="r num">{fmtKpi(k, v.baseline.mean)}</td>
                            <td className="r num font-semibold">{fmtKpi(k, v.optimized.mean)}</td>
                            <td className="r num">
                              {signed(v.abs_diff, 2)}
                              <span className="block text-[11px] text-ink-60">{signedPct(v.rel_diff_pct)}</span>
                            </td>
                            <td className="text-[12.5px]">{v.target_status?.target ?? d.targets[k] ?? "—"}</td>
                            <td>{v.target_status ? <MetTag met={v.target_status.met} /> : <Tag tone="quiet">No status</Tag>}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {expU && expUb && whU && whUb ? (
                  <div className="mt-5 border-l-2 border-ink pl-4">
                    <div className="kicker !text-ink">Worth knowing about expiry</div>
                    <p className="mt-1 max-w-[80ch] text-[13.5px] leading-relaxed">
                      {totalWorse
                        ? `Counting stock that expired in both stores and warehouses, the optimized plan lost more units (${int(expU.mean)} against ${int(expUb.mean)} for the baseline). `
                        : `Counting stock that expired in both stores and warehouses, the optimized plan lost ${int(expU.mean)} units against ${int(expUb.mean)} for the baseline. `}
                      Most of it sits in warehouses: {int(whU.mean)} expired there against {int(whUb.mean)} for the baseline. The headline expiry percentage above may not show this, so read the two together.
                    </p>
                  </div>
                ) : null}
              </Section>

              <Disclosure>
                <div className="space-y-10">
                  <div>
                    <div className="h3 mb-2">Spread across runs: mean [min – max]</div>
                    <div className="overflow-x-auto" data-lenis-prevent>
                      <table className="tbl">
                        <thead>
                          <tr>
                            <th>Measure</th>
                            <th className="r">Baseline</th>
                            <th className="r">Optimized</th>
                          </tr>
                        </thead>
                        <tbody>
                          {keys.map((k) => (
                            <tr key={k}>
                              <td>{PLAIN[k]}</td>
                              <td className="r num">
                                {fmtKpi(k, kpis[k].baseline.mean)} [{fmtKpi(k, kpis[k].baseline.min)} – {fmtKpi(k, kpis[k].baseline.max)}]
                              </td>
                              <td className="r num">
                                {fmtKpi(k, kpis[k].optimized.mean)} [{fmtKpi(k, kpis[k].optimized.min)} – {fmtKpi(k, kpis[k].optimized.max)}]
                              </td>
                            </tr>
                          ))}
                          {Object.keys(kpis)
                            .filter((k) => !ORDER.includes(k))
                            .map((k) => (
                              <tr key={k}>
                                <td>{k.replace(/_/g, " ")}</td>
                                <td className="r num">{dec(kpis[k].baseline.mean, 2)}</td>
                                <td className="r num">{dec(kpis[k].optimized.mean, 2)}</td>
                              </tr>
                            ))}
                          {techRows.map((e) =>
                            e.b && e.o ? (
                              <tr key={e.label}>
                                <td>{e.label}</td>
                                <td className="r num">
                                  {int(e.b.mean)} [{int(e.b.min)} – {int(e.b.max)}]
                                </td>
                                <td className="r num">
                                  {int(e.o.mean)} [{int(e.o.min)} – {int(e.o.max)}]
                                </td>
                              </tr>
                            ) : null,
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div>
                    <div className="h3 mb-2">Each run, baseline against optimized</div>
                    <div className="grid gap-x-8 gap-y-8 md:grid-cols-2">
                      {["stockout_rate", "fill_rate", "transport_cost", "expiry_wastage_pct"].map((k) => (
                        <div key={k}>
                          <div className="kicker mb-1">{PLAIN[k]}</div>
                          <BarsChart
                            height={200}
                            data={r.per_seed.map((s) => ({ seed: `seed ${s.seed}`, baseline: s.baseline[k], optimized: s.optimized[k] }))}
                            xKey="seed"
                            series={[
                              { key: "baseline", name: "Baseline", style: "hatch" },
                              { key: "optimized", name: "Optimized", style: "ink" },
                            ]}
                            fmt={(v) => dec(v, v >= 1000 ? 0 : 2)}
                            yWidth={56}
                          />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <div className="h3 mb-2">Plan checks in the replay (one value per run)</div>
                    <table className="tbl">
                      <thead>
                        <tr>
                          <th>Measure</th>
                          <th className="r">Baseline</th>
                          <th className="r">Optimized</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(["constraint_violations", "explanation_coverage_pct", "plans", "units_shipped"] as const).map((k) => {
                          const e = r.extra[k];
                          if (!e) return null;
                          const fmt = (a: (number | null)[]) => a.map((n) => (n === null ? "n/a" : dec(n, k === "explanation_coverage_pct" ? 1 : 0))).join(", ");
                          return (
                            <tr key={k}>
                              <td>{k.replace(/_/g, " ")}</td>
                              <td className="r num">{fmt(e.baseline)}</td>
                              <td className="r num">{fmt(e.optimized)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    <p className="mt-2 text-[12px] text-ink-60">
                      Data profile {r.data_profile}. Replay wall clock {dec(r.wall_clock_seconds, 0)} s. Run {r.run_id}.
                    </p>
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
