"use client";

import type { ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  align?: "right";
  /** server-side sort key; makes the header clickable when onSort is given */
  sort?: string;
  className?: string;
}

export interface SortState {
  key: string;
  desc: boolean;
}

export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  sort,
  onSort,
  onRowClick,
  selectedKey,
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  sort?: SortState;
  onSort?: (s: SortState) => void;
  onRowClick?: (row: T) => void;
  selectedKey?: string | number | null;
  caption?: string;
}) {
  return (
    <div className="overflow-x-auto" data-lenis-prevent>
      <table className="tbl">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((c) => {
              const sortable = !!(c.sort && onSort);
              const active = sortable && sort?.key === c.sort;
              return (
                <th
                  key={c.key}
                  className={c.align === "right" ? "r" : ""}
                  aria-sort={active ? (sort?.desc ? "descending" : "ascending") : undefined}
                >
                  {sortable ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 uppercase tracking-[inherit]"
                      onClick={() => onSort?.({ key: c.sort!, desc: active ? !sort!.desc : false })}
                    >
                      {c.header}
                      <span aria-hidden className={active ? "" : "opacity-30"}>
                        {active ? (sort!.desc ? "▼" : "▲") : "↕"}
                      </span>
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const k = rowKey(r);
            return (
              <tr
                key={k}
                className={`${selectedKey !== undefined && selectedKey === k ? "sel" : ""} ${onRowClick ? "cursor-pointer" : ""}`}
                onClick={onRowClick ? () => onRowClick(r) : undefined}
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(r);
                        }
                      }
                    : undefined
                }
              >
                {columns.map((c) => (
                  <td key={c.key} className={`${c.align ? "r num" : ""} ${c.className ?? ""}`}>
                    {c.render(r)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
