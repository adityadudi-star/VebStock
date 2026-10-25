"use client";

import { dec, date, when, int } from "@/lib/format";
import { useMeta } from "@/lib/data";
import PageHeader from "@/components/PageHeader";
import { SimTag, Tag } from "@/components/FlagLabel";
import Stateful from "@/components/Stateful";
import Disclosure from "@/components/Disclosure";
import { KV, Section } from "@/components/ui";

function val(v: unknown): string {
  if (typeof v === "number") return Number.isInteger(v) ? int(v) : dec(v, 4).replace(/0+$/, "").replace(/\.$/, "");
  if (v === null || v === undefined) return "—";
  return String(v);
}
const key = (k: string) => k.replace(/_/g, " ");

export default function DataPage() {
  const state = useMeta();
  return (
    <div>
      <PageHeader
        href="/data"
        lede="All numbers here come from a made-up (simulated) dataset. This page shows how it was built and the cost assumptions the optimizer uses."
      />
      <Stateful state={state} label="Loading metadata">
        {(m) => (
          <>
            <Section title="How the data was made" kicker="Synthetic data" aside={<SimTag>Simulated</SimTag>}>
              <div className="grid gap-x-10 gap-y-6 lg:grid-cols-2">
                <KV
                  rows={[
                    ["Dataset profile", val(m.generator_settings.profile)],
                    ["Random seed", val(m.generator_settings.seed)],
                    ["Warehouses", val(m.counts.warehouses)],
                    ["Stores", val(m.counts.stores)],
                    ["Products (SKUs)", val(m.counts.skus)],
                    ["Days simulated", val(m.generator_settings.n_days)],
                    ["First day", date(String(m.generator_settings.start_date))],
                  ]}
                />
                <ul className="space-y-1 text-[13px] leading-relaxed text-ink-60">
                  {m.notes.map((n, i) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            </Section>

            <Section title="Simulated date and real date" kicker="Two different clocks">
              <div className="grid gap-8 lg:grid-cols-[minmax(0,22rem)_1fr]">
                <KV rows={[["Simulated data snapshot", date(m.as_of.date)], ["Held-out window", `${val(m.generator_settings.test_days)} days`]]} />
                <div className="max-w-[70ch] text-[14px] leading-relaxed">
                <p className="mb-3 border-l-2 border-ink pl-3 font-medium">
                  The simulated snapshot date is {date(m.as_of.date)}. It is a date inside the simulation, taken from the backend, and is separate from the real clock in the page header, which shows the actual date and time on your device. The two may coincide or differ. Timestamps such as plan creation times are real and shown in your local time.
                </p>
                <p>
                  The system treats the first day of the held-out window as today. The forecast model was trained only on days before it. Sales inside the window are
                  kept aside and used to measure forecast accuracy and to replay the optimized and baseline policies, so those results are measured on simulated demand the model never saw.
                </p>
                </div>
              </div>
            </Section>

            <Section title="Festivals" kicker="Demand events in the generator">
              <table className="tbl max-w-md">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Festival</th>
                  </tr>
                </thead>
                <tbody>
                  {m.festivals.map((f) => (
                    <tr key={f.date + f.name}>
                      <td>{date(f.date)}</td>
                      <td>{f.name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>

            <Section title="Cost assumptions by category" kicker="Per unit, simulated">
              <div className="overflow-x-auto">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="r">SKUs</th>
                      <th className="r">Avg price</th>
                      <th className="r">Profit lost per unit not sold</th>
                      <th className="r">Value lost per unit that expires</th>
                      <th className="r">Shelf life (days)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {m.categories.map((c) => (
                      <tr key={c.category}>
                        <td className="font-medium">{c.category}</td>
                        <td className="r num">{c.skus}</td>
                        <td className="r num">{dec(c.avg_price, 2)}</td>
                        <td className="r num">{dec(c.lost_margin_per_unit, 2)}</td>
                        <td className="r num">{dec(c.writeoff_per_unit, 2)}</td>
                        <td className="r num">{c.shelf_life_days}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-6">
                <div className="kicker mb-2">Cost model, as stated by the backend</div>
                <dl className="border-t border-ink-15">
                  {Object.entries(m.cost_assumptions).map(([k, v]) => (
                    <div key={k} className="grid gap-1 border-b border-ink-15 py-2 sm:grid-cols-[10rem_1fr] sm:gap-4">
                      <dt className="font-mono text-[11px] uppercase tracking-[0.08em] text-ink-60">{key(k)}</dt>
                      <dd className="text-[13.5px]">{v}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </Section>

            <Section title="Warehouses" kicker={`${m.warehouses.length} nodes`}>
              <table className="tbl max-w-xl">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Region</th>
                  </tr>
                </thead>
                <tbody>
                  {m.warehouses.map((w) => (
                    <tr key={w.id}>
                      <td className="num">{w.id}</td>
                      <td>{w.name}</td>
                      <td>{w.region}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Section>

            <Disclosure>
              <div className="grid gap-x-10 gap-y-8 lg:grid-cols-2">
                <div>
                  <div className="h3 mb-2">All generator settings</div>
                  <KV rows={Object.entries(m.generator_settings).map(([k, v]) => [key(k), val(v)])} />
                </div>
                <div>
                  <div className="h3 mb-2">Row counts</div>
                  <KV rows={Object.entries(m.counts).map(([k, v]) => [key(k), val(v)])} />
                  <div className="h3 mb-2 mt-8">Thresholds behind the status labels</div>
                  <KV rows={Object.entries(m.thresholds).map(([k, v]) => [key(k), val(v)])} />
                </div>
                <div>
                  <div className="h3 mb-2">Forecast and replay runs</div>
                  <div className="mb-3 flex flex-wrap gap-2">
                    <Tag tone="outline">Forecast run {m.forecast_run_id ?? "none"}</Tag>
                    {m.comparison ? <Tag tone="outline">Comparison run {m.comparison.run_id}</Tag> : <Tag tone="dashed">No comparison run yet</Tag>}
                  </div>
                  {m.comparison ? (
                    <>
                      <p className="mb-2 text-[12px] text-ink-60">Comparison created {when(m.comparison.created_at)}</p>
                      <KV rows={Object.entries(m.comparison.config).map(([k, v]) => [key(k), val(v)])} />
                    </>
                  ) : null}
                </div>
                <div>
                  <div className="h3 mb-2">Other category figures</div>
                  <KV rows={m.categories.map((c) => [c.category, `avg price ${dec(c.avg_price, 2)} · min remaining life ${c.min_remaining_shelf_life_days} d`])} />
                </div>
              </div>
            </Disclosure>
          </>
        )}
      </Stateful>
    </div>
  );
}
