"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, get, patch, post } from "@/lib/api";
import { useMeta, usePlans } from "@/lib/data";
import { date, dec, int, when } from "@/lib/format";
import { useApi, useDebounced, useStoredString } from "@/lib/hooks";
import type { PickList, Plan, PlanLine, PlanPatchOut, Violation } from "@/lib/types";
import DataTable, { Column } from "@/components/DataTable";
import { StatusTag, Tag } from "@/components/FlagLabel";
import PageHeader from "@/components/PageHeader";
import Pagination from "@/components/Pagination";
import PickListView from "@/components/PickListView";
import { PlanDetails, ViolationList } from "@/components/PlanPanels";
import Stateful, { Banner, Empty, ErrorBox, Loading } from "@/components/Stateful";
import { Section, Select, TextInput } from "@/components/ui";

const STORE_KEY = "vebstock.currentPlanId";

interface Editor {
  lineId: number;
  qty: string;
  reason: string;
}
interface Check {
  lineId: number;
  kind: "valid" | "rejected" | "error";
  message: string;
  violations: Violation[];
}

export default function PlanPage() {
  const meta = useMeta();
  const plans = usePlans(20);
  const [stored, setStored] = useStoredString(STORE_KEY);
  const [mem, setMem] = useState<number | null>(null); // fallback when storage is blocked
  const planId = mem ?? (stored && Number.isFinite(Number(stored)) ? Number(stored) : null);
  const select = (id: number) => {
    setMem(id);
    setStored(String(id));
    setPage(1);
    setEditor(null);
    setCheck(null);
  };

  const [horizon, setHorizon] = useState("14");
  const [gen, setGen] = useState<{ busy: boolean; error: ApiError | null }>({ busy: false, error: null });
  const [rev, setRev] = useState(0);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [wh, setWh] = useState("");
  const [storeId, setStoreId] = useState("");
  const [q, setQ] = useState("");
  const qd = useDebounced(q);
  const sid = useDebounced(storeId);

  const [editor, setEditor] = useState<Editor | null>(null);
  const [check, setCheck] = useState<Check | null>(null);
  const [busy, setBusy] = useState(false);
  const [approve, setApprove] = useState<{ busy: boolean; error: ApiError | null }>({ busy: false, error: null });

  const detail = useApi<Plan>(
    `plan:${planId}:${page}:${pageSize}:${wh}:${sid}:${qd}:${rev}`,
    planId
      ? (signal) =>
          get<Plan>(`/plans/${planId}`, { page, page_size: pageSize, warehouse_id: wh, store_id: sid, q: qd }, signal)
      : null,
  );
  const approved = detail.data?.status === "approved";
  const pick = useApi<PickList>(
    `pick:${planId}:${approved}:${rev}`,
    planId && approved ? (signal) => get<PickList>(`/plans/${planId}/pick-list`, undefined, signal) : null,
  );

  async function generate() {
    const h = Number(horizon);
    if (!Number.isInteger(h) || h < 1 || h > 60) {
      setGen({ busy: false, error: new ApiError("Horizon must be a whole number of days between 1 and 60.", 422) });
      return;
    }
    setGen({ busy: true, error: null });
    try {
      const p = await post<Plan>("/plan", { horizon_days: h });
      setGen({ busy: false, error: null });
      select(p.id);
      setRev((r) => r + 1);
      plans.refetch();
    } catch (e) {
      setGen({ busy: false, error: e instanceof ApiError ? e : new ApiError(String(e), 0) });
    }
  }

  function parseEditor(line: PlanLine): { ok: true; qty: number } | { ok: false; msg: string } {
    if (!editor) return { ok: false, msg: "" };
    const n = Number(editor.qty);
    if (editor.qty.trim() === "" || !Number.isInteger(n) || n < 0) return { ok: false, msg: "Quantity must be a whole number, zero or more." };
    if (editor.reason.trim().length < 3) return { ok: false, msg: "A reason of at least 3 characters is required." };
    if (n === line.qty) return { ok: false, msg: "Quantity is unchanged." };
    return { ok: true, qty: n };
  }

  async function run(line: PlanLine, validateOnly: boolean) {
    if (!editor || !planId) return;
    const p = parseEditor(line);
    if (!p.ok) {
      setCheck({ lineId: line.id, kind: "error", message: p.msg, violations: [] });
      return;
    }
    setBusy(true);
    try {
      const res = await patch<PlanPatchOut>(`/plan/${planId}`, {
        actor: "demo.planner",
        overrides: [{ line_id: line.id, qty: p.qty, reason: editor.reason.trim() }],
        validate_only: validateOnly,
      });
      if (validateOnly) {
        setCheck({ lineId: line.id, kind: "valid", message: "No problems found. This change can be applied.", violations: res.violations });
      } else {
        setCheck(null);
        setEditor(null);
        setRev((r) => r + 1);
        plans.refetch();
      }
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(String(e), 0);
      setCheck({
        lineId: line.id,
        kind: err.status === 422 ? "rejected" : "error",
        message: err.message,
        violations: err.violations,
      });
    } finally {
      setBusy(false);
    }
  }

  async function doApprove() {
    if (!planId) return;
    setApprove({ busy: true, error: null });
    try {
      await patch<PlanPatchOut>(`/plan/${planId}`, { actor: "demo.planner", approve: true });
      setApprove({ busy: false, error: null });
      setRev((r) => r + 1);
      plans.refetch();
    } catch (e) {
      setApprove({ busy: false, error: e instanceof ApiError ? e : new ApiError(String(e), 0) });
    }
  }

  const cols = (plan: Plan): Column<PlanLine>[] => [
    {
      key: "sku",
      header: "Product",
      render: (r) => (
        <div>
          <span>{r.sku_name}</span>
          <span className="num block text-[11px] text-ink-60">{r.sku_code}</span>
        </div>
      ),
    },
    {
      key: "from",
      header: "From",
      render: (r) => (
        <div>
          {r.warehouse}
          <span className="num block text-[11px] text-ink-60">
            batch {r.batch_code} · expires {date(r.batch_expiry)} ({r.days_to_expiry}d)
          </span>
        </div>
      ),
    },
    {
      key: "store",
      header: "To",
      render: (r) => (
        <div>
          {r.store}
          <span className="num block text-[11px] text-ink-60">transport {dec(r.transport_cost, 2)}</span>
        </div>
      ),
    },
    {
      key: "qty",
      header: "Units",
      align: "right",
      render: (r) =>
        r.qty !== r.original_qty ? (
          <span>
            <span className="font-semibold">{int(r.qty)}</span>
            <span className="block text-[11px] font-normal text-ink-60 line-through">{int(r.original_qty)}</span>
          </span>
        ) : (
          int(r.qty)
        ),
    },
    { key: "reason", header: "Why this shipment", className: "max-w-[38ch] text-[12px] leading-snug", render: (r) => r.reason },
    {
      key: "status",
      header: "Status",
      render: (r) => (
        <div className="space-y-1">
          {r.status === "overridden" || r.qty !== r.original_qty ? <Tag tone="sage">Changed by you</Tag> : <Tag tone="quiet">{r.status}</Tag>}
          {r.override_reason ? <div className="max-w-[24ch] text-[11px] text-ink-60">“{r.override_reason}”</div> : null}
          {plan.status !== "approved" ? (
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                setEditor({ lineId: r.id, qty: String(r.qty), reason: "" });
                setCheck(null);
              }}
            >
              Edit
            </button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        href="/plan"
        lede="Create a shipping plan, read why each shipment was chosen, change any line if you know better, then approve it to release the pick list."
      />

      <Section title="Create a plan" kicker="Uses the default balance between stockouts and expiry">
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-40">
            <TextInput label="Plan ahead for (days)" type="number" min={1} max={60} value={horizon} onChange={setHorizon} />
          </div>
          <button type="button" className="btn btn-solid" onClick={generate} disabled={gen.busy}>
            {gen.busy ? "Calculating…" : "Generate plan"}
          </button>
          {gen.busy ? <span className="kicker">This takes about two seconds.</span> : null}
        </div>
        {gen.error ? (
          <div className="mt-4">
            <ErrorBox error={gen.error} onRetry={generate} />
          </div>
        ) : null}
      </Section>

      <Section title="Recent plans" kicker="Reopen one to review it">
        <Stateful state={plans} label="Loading plans" isEmpty={(d) => d.length === 0} empty={<Empty title="No plans yet">Generate one above.</Empty>}>
          {(list) => (
            <div className="overflow-x-auto">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Plan</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th className="r">Total cost</th>
                    <th>Type</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.map((p) => (
                    <tr key={p.id} className={p.id === planId ? "sel" : ""}>
                      <td className="num">#{p.id}</td>
                      <td>
                        <StatusTag status={p.status} />
                      </td>
                      <td>{when(p.created_at)}</td>
                      <td className="r num">{int(p.total_cost)}</td>
                      <td className="text-[12px] text-ink-60">
                        {p.scenario ? `what-if: ${String(p.scenario.type).replace(/_/g, " ")}` : "regular plan"}
                      </td>
                      <td>
                        <button type="button" className="btn btn-sm" onClick={() => select(p.id)} disabled={p.id === planId}>
                          {p.id === planId ? "Open" : "Reopen"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Stateful>
      </Section>

      {!planId ? (
        <Empty title="No plan open">Generate a plan or reopen one from the list above.</Empty>
      ) : (
        <Stateful state={detail} label="Loading plan">
          {(plan) => (
            <>
              <Section
                title="Plan"
                kicker="Summary"
                aside={
                  plan.status === "approved" ? (
                    <Tag tone="solid">Approved</Tag>
                  ) : (
                    <button type="button" className="btn btn-solid" onClick={doApprove} disabled={approve.busy}>
                      {approve.busy ? "Approving…" : "Approve plan"}
                    </button>
                  )
                }
              >
                {approve.error ? (
                  <div className="mb-4">
                    <ErrorBox error={approve.error} onRetry={doApprove} />
                  </div>
                ) : null}
                <PlanDetails plan={plan} />
              </Section>

              <Section title="Shipments" kicker={`${int(plan.total_lines)} shipment lines match your filters`}>
                <div className="mb-4 grid grid-cols-2 gap-3 border border-ink-15 p-3 md:grid-cols-4">
                  <Select
                    label="From warehouse"
                    value={wh}
                    onChange={(v) => {
                      setWh(v);
                      setPage(1);
                    }}
                    options={(meta.data?.warehouses ?? []).map((w) => ({ value: String(w.id), label: w.name }))}
                  />
                  <TextInput
                    label="Store number"
                    type="number"
                    min={1}
                    value={storeId}
                    onChange={(v) => {
                      setStoreId(v);
                      setPage(1);
                    }}
                  />
                  <TextInput
                    label="Search"
                    value={q}
                    onChange={(v) => {
                      setQ(v);
                      setPage(1);
                    }}
                    placeholder="SKU, store, batch"
                  />
                </div>
                {plan.status !== "approved" ? (
                  <p className="mb-3 text-[12.5px] text-ink-60">
                    Click Edit on a line to change its units. A reason of at least 3 characters is required. Validate checks the change without saving it.
                  </p>
                ) : (
                  <Banner>Approved plans are locked. Lines can no longer be edited.</Banner>
                )}
                {plan.lines.length === 0 ? (
                  <Empty title="No shipment lines match">Clear the filters to see every line.</Empty>
                ) : (
                  <>
                    <DataTable
                      caption="Shipment lines"
                      columns={cols(plan)}
                      rows={plan.lines}
                      rowKey={(r) => r.id}
                      selectedKey={editor?.lineId ?? null}
                    />
                    {editor && plan.lines.find((l) => l.id === editor.lineId) ? (
                      <OverrideForm
                        line={plan.lines.find((l) => l.id === editor.lineId)!}
                        editor={editor}
                        setEditor={setEditor}
                        check={check?.lineId === editor.lineId ? check : null}
                        busy={busy}
                        onValidate={(l) => run(l, true)}
                        onApply={(l) => run(l, false)}
                        onCancel={() => {
                          setEditor(null);
                          setCheck(null);
                        }}
                      />
                    ) : editor ? (
                      <Banner>The line being edited is not on this page. Cancel or navigate back.</Banner>
                    ) : null}
                    <Pagination
                      page={plan.page}
                      pageSize={plan.page_size}
                      total={plan.total_lines}
                      onPage={setPage}
                      onPageSize={(s) => {
                        setPageSize(s);
                        setPage(1);
                      }}
                    />
                  </>
                )}
              </Section>

              <Section title="Pick list" kicker="Released when the plan is approved">
                {!approved ? (
                  <Empty title="Pick list not available yet">Approve the plan above to release the pick list for the warehouse teams.</Empty>
                ) : (
                  <Stateful state={pick} label="Loading pick list" isEmpty={(d) => d.batches.length === 0} empty={<Empty title="Pick list is empty" />}>
                    {(p) => (
                      <>
                        <p className="mb-4 font-mono text-[11px] uppercase tracking-[0.08em] text-ink-60">Order: {p.ordering}. In short, the oldest stock ships first.</p>
                        <PickListView batches={p.batches} />
                      </>
                    )}
                  </Stateful>
                )}
              </Section>
            </>
          )}
        </Stateful>
      )}
      {planId && detail.loading && !detail.data ? <Loading /> : null}
    </div>
  );
}

function OverrideForm({
  line,
  editor,
  setEditor,
  check,
  busy,
  onValidate,
  onApply,
  onCancel,
}: {
  line: PlanLine;
  editor: Editor;
  setEditor: (e: Editor) => void;
  check: Check | null;
  busy: boolean;
  onValidate: (l: PlanLine) => void;
  onApply: (l: PlanLine) => void;
  onCancel: () => void;
}) {
  const reasonShort = editor.reason.trim().length < 3;
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollIntoView({ block: "center" });
  }, [line.id]);
  return (
    <div ref={ref} className="my-4 border border-ink p-4">
      <div className="kicker !text-ink">
        Change line #{line.id} · {line.sku_code} · {line.warehouse} to {line.store}
      </div>
      <p className="mt-1 text-[12.5px] text-ink-60">
        Originally {int(line.original_qty)} units, now {int(line.qty)}.
      </p>
      <div className="mt-3 grid gap-3 md:grid-cols-[8rem_1fr]">
        <TextInput label="New units" type="number" min={0} step={1} value={editor.qty} onChange={(v) => setEditor({ ...editor, qty: v })} />
        <TextInput
          label="Reason (required, min 3 characters)"
          value={editor.reason}
          onChange={(v) => setEditor({ ...editor, reason: v })}
          error={editor.reason.length > 0 && reasonShort ? "Reason is too short." : undefined}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn" disabled={busy || reasonShort} onClick={() => onValidate(line)}>
          Validate
        </button>
        <button type="button" className="btn btn-solid" disabled={busy || reasonShort} onClick={() => onApply(line)}>
          Apply change
        </button>
        <button type="button" className="btn btn-quiet" onClick={onCancel}>
          Cancel
        </button>
      </div>
      {check ? (
        <div role="status" className="mt-3">
          <div className="flex flex-wrap items-center gap-2">
            {check.kind === "valid" ? <Tag tone="solid">✓ Valid</Tag> : check.kind === "rejected" ? <Tag tone="dashed">✗ Rejected, line unchanged</Tag> : <Tag tone="dashed">Error</Tag>}
            <span className="text-[13px]">{check.message}</span>
          </div>
          <ViolationList violations={check.violations} />
        </div>
      ) : null}
    </div>
  );
}
