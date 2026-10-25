"use client";

import { int } from "@/lib/format";

export default function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  sizes = [25, 50, 100],
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
  onPageSize?: (s: number) => void;
  sizes?: number[];
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-ink-15 pt-3 font-mono text-[11px] uppercase tracking-[0.08em]">
      <div className="text-ink-60">
        {int(from)}–{int(to)} of {int(total)}
      </div>
      <div className="flex items-center gap-2">
        {onPageSize ? (
          <label className="flex items-center gap-2 text-ink-60">
            Rows
            <select
              className="field !py-1"
              value={pageSize}
              onChange={(e) => onPageSize(Number(e.target.value))}
              aria-label="Rows per page"
            >
              {sizes.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button type="button" className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(1)} aria-label="First page">
          «
        </button>
        <button type="button" className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          Prev
        </button>
        <span className="num px-1">
          {page} / {pages}
        </span>
        <button type="button" className="btn btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Next
        </button>
        <button
          type="button"
          className="btn btn-sm"
          disabled={page >= pages}
          onClick={() => onPage(pages)}
          aria-label="Last page"
        >
          »
        </button>
      </div>
    </div>
  );
}
