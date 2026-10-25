"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { addDays, shortDate } from "@/lib/format";
import type { WeekPoint } from "@/lib/types";
import { motion } from "motion/react";
import { useReduced } from "./Motion";

// Charts use only the three tones (via CSS variables) and opacity/dash/hatch to separate series.
export type SeriesStyle = "ink" | "sage" | "hatch" | "light";

const FILL: Record<SeriesStyle, { fill: string; stroke: string }> = {
  ink: { fill: "var(--ink)", stroke: "var(--ink)" },
  sage: { fill: "var(--sage)", stroke: "var(--ink)" },
  hatch: { fill: "url(#vs-hatch)", stroke: "var(--ink)" },
  light: { fill: "var(--ink-15)", stroke: "var(--ink)" },
};

const tick = { fill: "var(--ink-60)", fontSize: 10, fontFamily: "var(--font-mono)" };
const tipStyle = {
  background: "var(--paper)",
  border: "1px solid var(--ink)",
  borderRadius: 0,
  fontSize: 12,
  fontFamily: "var(--font-mono)",
  color: "var(--ink)",
};

function Defs() {
  return (
    <defs>
      <pattern id="vs-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="var(--paper)" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--ink)" strokeWidth="2" />
      </pattern>
    </defs>
  );
}

export interface BarSeries {
  key: string;
  name: string;
  style: SeriesStyle;
}

export function BarsChart({
  data,
  xKey,
  series,
  height = 260,
  stacked = false,
  horizontal = false,
  fmt = (v: number) => new Intl.NumberFormat("en-IN").format(Math.round(v)),
  yWidth,
}: {
  data: object[];
  xKey: string;
  series: BarSeries[];
  height?: number;
  stacked?: boolean;
  horizontal?: boolean;
  fmt?: (v: number) => string;
  yWidth?: number;
}) {
  const reduced = useReduced();
  return (
    <div style={{ height }} className="w-full" role="img" aria-label="Bar chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <Defs />
          <CartesianGrid stroke="var(--ink-15)" vertical={horizontal} horizontal={!horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tick={tick} tickFormatter={fmt} stroke="var(--ink)" />
              <YAxis type="category" dataKey={xKey} tick={tick} width={yWidth ?? 110} stroke="var(--ink)" />
            </>
          ) : (
            <>
              <XAxis dataKey={xKey} tick={tick} stroke="var(--ink)" interval={0} />
              <YAxis tick={tick} tickFormatter={fmt} stroke="var(--ink)" width={yWidth ?? 62} />
            </>
          )}
          <Tooltip
            contentStyle={tipStyle}
            cursor={{ fill: "var(--ink-08)" }}
            formatter={(v) => (typeof v === "number" ? fmt(v) : String(v))}
          />
          {series.length > 1 ? (
            <Legend wrapperStyle={{ fontSize: 11, fontFamily: "var(--font-mono)" }} iconType="square" />
          ) : null}
          {series.map((s) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.name}
              stackId={stacked ? "a" : undefined}
              fill={FILL[s.style].fill}
              stroke={FILL[s.style].stroke}
              strokeWidth={1}
              isAnimationActive={!reduced} animationDuration={900}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface TrendRow {
  week: string;
  history?: number;
  actual?: number;
  p50?: number;
  band?: [number, number];
}

export function toTrendRows(points: WeekPoint[]): TrendRow[] {
  const map = new Map<string, TrendRow>();
  for (const p of [...points].sort((a, b) => a.week_start.localeCompare(b.week_start))) {
    const row = map.get(p.week_start) ?? { week: p.week_start };
    if (p.kind === "history") row.history = p.units;
    else if (p.kind === "actual_held_out") row.actual = p.units;
    else {
      row.p50 = p.p50 ?? p.units;
      if (p.p10 != null && p.p90 != null) row.band = [p.p10, p.p90];
    }
    map.set(p.week_start, row);
  }
  return [...map.values()];
}

/** Weekly history (solid ink) vs held-out actual (dashed ink) vs forecast P50 (sage) with P10-P90 band. */
export function TrendChart({ points, height = 300 }: { points: WeekPoint[]; height?: number }) {
  const reduced = useReduced();
  const data = toTrendRows(points);
  const f = (v: number) => new Intl.NumberFormat("en-IN").format(Math.round(v));
  return (
    <div style={{ height }} className="w-full" role="img" aria-label="Weekly demand: history, held-out actual, forecast with P10 to P90 band">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--ink-15)" vertical={false} />
          <XAxis dataKey="week" tick={tick} stroke="var(--ink)" minTickGap={28} tickFormatter={(v: string) => shortDate(v)} />
          <YAxis tick={tick} tickFormatter={f} stroke="var(--ink)" width={62} />
          <Tooltip
            contentStyle={tipStyle}
            labelFormatter={(l) => `Week of ${shortDate(String(l))}`}
            formatter={(v) => (Array.isArray(v) ? `${f(Number(v[0]))} – ${f(Number(v[1]))}` : typeof v === "number" ? f(v) : String(v))}
          />
          <Legend wrapperStyle={{ fontSize: 11, fontFamily: "var(--font-mono)" }} />
          <Area
            dataKey="band"
            name="Forecast P10–P90"
            stroke="var(--sage)"
            strokeDasharray="2 3"
            fill="var(--sage-30)"
            isAnimationActive={!reduced} animationDuration={900}
            connectNulls
          />
          <Line dataKey="history" name="History" stroke="var(--ink)" strokeWidth={1.5} dot={false} isAnimationActive={!reduced} animationDuration={900} />
          <Line
            dataKey="actual"
            name="Held-out actual (simulated)"
            stroke="var(--ink)"
            strokeWidth={1.5}
            strokeDasharray="5 3"
            dot={{ r: 2, fill: "var(--ink)" }}
            isAnimationActive={!reduced} animationDuration={900}
          />
          <Line dataKey="p50" name="Forecast P50" stroke="var(--sage)" strokeWidth={2.5} dot={{ r: 2, fill: "var(--sage)" }} isAnimationActive={!reduced} animationDuration={900} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Weekly accuracy: MAPE as solid bars, WAPE as hatched bars. */
export function AccuracyBars({ weeks, height = 240, asOf }: { weeks: { week: number; mape: number; wape: number }[]; height?: number; asOf?: string }) {
  const data = weeks.map((w) => ({ week: asOf ? shortDate(addDays(asOf, 7 * (w.week - 1))) : `W${w.week}`, mape: Number(w.mape.toFixed(2)), wape: Number(w.wape.toFixed(2)) }));
  return (
    <BarsChart
      data={data}
      xKey="week"
      height={height}
      series={[
        { key: "mape", name: "Weekly MAPE %", style: "ink" },
        { key: "wape", name: "WAPE %", style: "hatch" },
      ]}
      fmt={(v) => `${v.toFixed(1)}`}
      yWidth={36}
    />
  );
}

/** Horizontal utilisation bars on a hairline track. Pure CSS, no chart lib. */
export function UtilBar({ value, label, right }: { value: number; label: React.ReactNode; right?: React.ReactNode }) {
  const v = Math.max(0, Math.min(100, value));
  const reduced = useReduced();
  return (
    <div className="grid grid-cols-[minmax(0,10rem)_1fr_auto] items-center gap-3 py-1 text-[12px]">
      <div className="truncate">{label}</div>
      <div className="relative h-3 border border-ink">
        <motion.div
          className={`absolute inset-y-0 left-0 ${value > 80 ? "bg-ink" : "bg-sage"}`}
          initial={reduced ? false : { width: 0 }}
          whileInView={{ width: `${v}%` }}
          viewport={{ once: true }}
          animate={reduced ? { width: `${v}%` } : undefined}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>
      <div className="num w-24 text-right">{right}</div>
    </div>
  );
}
