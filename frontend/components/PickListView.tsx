"use client";

import { date, int } from "@/lib/format";
import type { PickBatch } from "@/lib/types";

/** Pick list grouped by warehouse. Batch order is exactly as returned (earliest expiry first). */
export default function PickListView({ batches, groupBy = "warehouse" }: { batches: PickBatch[]; groupBy?: "warehouse" | "expiry" }) {
  const groups = new Map<string, PickBatch[]>();
  for (const b of batches) {
    const k = groupBy === "warehouse" ? b.warehouse : b.expiry_date;
    groups.set(k, [...(groups.get(k) ?? []), b]);
  }
  return (
    <div className="space-y-8">
      {[...groups.entries()].map(([g, rows]) => (
        <div key={g}>
          <div className="mb-2 flex items-baseline justify-between border-b border-ink pb-1">
            <h4 className="serif text-[20px] font-medium">{groupBy === "warehouse" ? g : `Expiry ${date(g)}`}</h4>
            <span className="num text-[11px] text-ink-60">
              {rows.length} batches · {int(rows.reduce((s, r) => s + r.qty, 0))} units
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Batch</th>
                  {groupBy === "expiry" ? <th>Warehouse</th> : null}
                  <th>SKU</th>
                  <th>Expiry</th>
                  <th className="r">Days left</th>
                  <th className="r">Pick qty</th>
                  <th>Destinations (store, qty, lead time)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((b) => (
                  <tr key={`${b.warehouse_id}-${b.batch_id}`}>
                    <td className="num">{b.batch_code}</td>
                    {groupBy === "expiry" ? <td>{b.warehouse}</td> : null}
                    <td>
                      <span className="num">{b.sku_code}</span>
                      <span className="block text-[11px] text-ink-60">{b.sku_name}</span>
                    </td>
                    <td>{date(b.expiry_date)}</td>
                    <td className="r num">{int(b.days_to_expiry)}</td>
                    <td className="r num font-medium">{int(b.qty)}</td>
                    <td className="text-[12px]">
                      {b.destinations.map((d, i) => (
                        <span key={i} className="mr-3 inline-block whitespace-nowrap">
                          {d.store} <span className="num">× {int(d.qty)}</span>{" "}
                          <span className="text-ink-60">({d.lead_time_days}d)</span>
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
