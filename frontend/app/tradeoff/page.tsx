"use client";

import { useState } from "react";
import { ApiError, post } from "@/lib/api";
import { fmtKpi, KPI_META, useMeta } from "@/lib/data";
import { dec, int, signed } from "@/lib/format";
import type { Plan } from "@/lib/types";
import Disclosure from "@/components/Disclosure";
import { SimTag, Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import { PlanKpiGrid } from "@/components/PlanPanels";
import Slider from "@/components/Slider";
import Stat, { StatGrid } from "@/components/Stat";
import Stateful, { Empty, ErrorBox } from "@/components/Stateful";
import { Section, TextInput } from "@/components/ui";

const DELTAS: { key: string; label: string; get: (p: Plan) => number; d: number }[] = [
  { key: "fill", label: "Demand covered (%)", get: (p) => p.kpis.projected_fill_rate_pct, d: 2 },
  { key: "unmet", label: "Units not covered", get: (p) => p.kpis.unmet_demand_units, d: 1 },
  { key: "expiring", label: "Units that may expire", get: (p) => p.kpis.expected_expiring_units, d: 1 },
  { key: "expval", label: "Value that may expire", get: (p) => p.kpis.expected_expiry_value, d: 0 },
  { key: "transport", label: "Transport cost", get: (p) => p.kpis.transport_cost, d: 0 },
  { key: "total", label: "Total cost", get: (p) => p.total_cost, d: 0 },
  { key: "shipped", label: "Units shipped", get: (p) => p.kpis.units_shipped, d: 0 },
];

export default function TradeoffPage() {
  const meta = useMeta();
  return (
    <div>
      <PageHeader
        href="/tradeoff"
        lede="Decide whether the plan should worry more about running out of stock or about stock expiring. Move the sliders, press Re-solve and read what changed."
      />
      <Stateful state={meta} label="Loading categories">{(m) => <Solver categories={m.categories_list} cat={m.categories} />}</Stateful>
    </div>
  );
}

function Solver({ categories, cat }: { categories: string[]; cat: { category: string; lost_margin_per_unit: number; writeoff_per_unit: number }[] }) {
  const [def, setDef] = useState(0.7);
  const [alphas, setAlphas] = useState<Record<string, number>>(() => Object.fromEntries(categories.map((c) => [c, 0.7])));
  const [horizon, setHorizon] = useState("14");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [cur, setCur] = useState<Plan | null>(null);
  const [prev, setPrev] = useState<Plan | null>(null);

  async function solve() {
    const h = Number(horizon);
    if (!Number.isInteger(h) || h < 1 || h > 60) {
      setError(new ApiError("Horizon must be a whole number of days between 1 and 60.", 422));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const p = await post<Plan>("/plan", { horizon_days: h, alphas, default_alpha: def });
      setPrev(cur);
      setCur(p);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e), 0));
    } finally {
      setBusy(false);
    }
  }
  const setAll = (v: number) => {
    setDef(v);
    setAlphas(Object.fromEntries(categories.map((c) => [c, v])));
  };
  const costs = (c: string) => cat.find((x) => x.category === c);

  return (
    <div>
      <Section title="How the balance works" kicker="One dial, called alpha">
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="border-l-2 border-ink pl-4">
            <p className="serif text-[19px] leading-snug">
              Cost = transport + <b>α</b> × lost margin × demand not covered + (<b>1 − α</b>) × write-off value × stock that expires.
            </p>
          </div>
          <ul className="space-y-2 text-[13.5px] leading-relaxed">
            <li>
              <b>Alpha near 1</b>: avoid running out. The plan ships more stock to protect sales and accepts more expiry risk.
            </li>
            <li>
              <b>Alpha near 0</b>: avoid waste. The plan ships carefully to limit write-offs and accepts more shortages.
            </li>
            <li>Lost margin (profit missed per unit not sold) and write-off (value lost per unit that expires) differ by category. They are shown under each slider and are simulated assumptions.</li>
          </ul>
        </div>
      </Section>

      <Section title="Set the balance" kicker="Default and per category">
        <div className="mb-8 max-w-xl border border-ink p-4">
          <Slider label="Default balance (alpha), also sets every category below" value={def} onChange={setAll} hint="0 = avoid waste · 1 = avoid running out" />
        </div>
        <div className="grid gap-x-10 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
          {categories.map((c) => (
            <Slider
              key={c}
              label={c}
              value={alphas[c] ?? def}
              onChange={(v) => setAlphas((a) => ({ ...a, [c]: v }))}
              hint={costs(c) ? `lost margin ${dec(costs(c)!.lost_margin_per_unit, 2)} · write-off ${dec(costs(c)!.writeoff_per_unit, 2)} per unit` : undefined}
            />
          ))}
        </div>
        <div className="mt-8 flex flex-wrap items-end gap-4 border-t border-ink-15 pt-4">
          <div className="w-40">
            <TextInput label="Plan ahead for (days)" type="number" min={1} max={60} value={horizon} onChange={setHorizon} />
          </div>
          <button type="button" className="btn btn-solid" onClick={solve} disabled={busy}>
            {busy ? "Calculating…" : "Re-solve"}
          </button>
          {busy ? <span className="kicker">This takes about two seconds.</span> : null}
        </div>
        {error ? (
          <div className="mt-4">
            <ErrorBox error={error} onRetry={solve} />
          </div>
        ) : null}
      </Section>

      {!cur ? (
        <Empty title="No result yet">Press Re-solve to build a plan with these settings. The comparison with the previous plan appears after a second solve.</Empty>
      ) : (
        <>
          <Section title="Result" kicker={`Plan #${cur.id}`} aside={<SimTag>Simulated data</SimTag>}>
            <StatGrid cols={4}>
              <Stat label="Time to calculate" value={`${dec(cur.kpis.solve_seconds, 2)} s`} sub={`wall clock ${dec(Number(cur.notes.timing?.wall_clock_seconds), 2)} s`} />
              <Stat label="Total cost" value={int(cur.total_cost)} sub={`solver ${cur.solver_status}`} inverted />
              <Stat label="Default alpha used" value={cur.default_alpha.toFixed(2)} sub="0 = avoid waste · 1 = avoid running out" />
              <Stat label="Categories set" value={String(Object.keys(cur.alphas).length)} sub="each with its own alpha" />
            </StatGrid>
            <div className="mt-6">
              <PlanKpiGrid k={cur.kpis} />
            </div>
          </Section>

          <Section title="What changed since the last solve" kicker="New plan minus previous plan">
            {!prev ? (
              <Empty title="Nothing to compare yet">This is the first solve in this session. Move a slider and re-solve to see the changes.</Empty>
            ) : (
              <>
                <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.08em] text-ink-60">
                  Plan #{cur.id} against plan #{prev.id}. Both are static projections on the same snapshot.
                </p>
                <div className="overflow-x-auto">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Measure</th>
                        <th className="r">Before</th>
                        <th className="r">Now</th>
                        <th className="r">Change</th>
                      </tr>
                    </thead>
                    <tbody>
                      {DELTAS.map((r) => {
                        const a = r.get(prev);
                        const b = r.get(cur);
                        return (
                          <tr key={r.key}>
                            <td>{r.label}</td>
                            <td className="r num">{dec(a, r.d)}</td>
                            <td className="r num">{dec(b, r.d)}</td>
                            <td className="r num font-semibold">{signed(b - a, r.d)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </Section>

          <Disclosure title="Reference: measured baseline replay (a different basis)">
            <div className="mb-3"><Tag tone="sage">Measured on simulated data</Tag></div>
            {cur.baseline_kpis?.kpis ? (
              <>
                <p className="mb-3 max-w-[80ch] text-[13px] text-ink-60">
                  {cur.baseline_kpis.basis ??
                    "Measured replay values are not directly comparable to a static plan projection."}
                </p>
                <div className="overflow-x-auto">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Replay KPI</th>
                        <th className="r">Baseline policy</th>
                        <th className="r">Optimized policy</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(cur.baseline_kpis.kpis).map(([k, v]) => (
                        <tr key={k}>
                          <td>{KPI_META[k]?.label ?? k.replace(/_/g, " ")}</td>
                          <td className="r num">{fmtKpi(k, v.baseline)}</td>
                          <td className="r num">{fmtKpi(k, v.optimized)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <Empty title="No replay reference attached to this plan" />
            )}
          </Disclosure>
        </>
      )}
    </div>
  );
}
