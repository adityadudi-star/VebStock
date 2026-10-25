type Tone = "solid" | "outline" | "sage" | "dashed" | "quiet";

const CLS: Record<Tone, string> = {
  solid: "tag tag-solid",
  outline: "tag",
  sage: "tag tag-sage",
  dashed: "tag tag-dashed",
  quiet: "tag tag-quiet",
};

export function Tag({ tone = "outline", children, title }: { tone?: Tone; children: React.ReactNode; title?: string }) {
  return (
    <span className={CLS[tone]} title={title}>
      {children}
    </span>
  );
}

/** Row flags for inventory: low stock / excess / expiry risk. */
export default function FlagLabel({ low, excess, expiry }: { low?: boolean; excess?: boolean; expiry?: boolean }) {
  if (!low && !excess && !expiry) return <span className="text-ink-40">—</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {low ? <Tag tone="solid">Running low</Tag> : null}
      {excess ? <Tag tone="dashed">Too much</Tag> : null}
      {expiry ? <Tag tone="outline">May expire</Tag> : null}
    </span>
  );
}

export function StatusTag({ status }: { status: string }) {
  const tone: Tone =
    status === "approved" ? "solid" : status === "overridden" ? "sage" : status === "pending" ? "outline" : "quiet";
  return <Tag tone={tone}>{status}</Tag>;
}

export function MetTag({ met }: { met: boolean | null | undefined }) {
  if (met === null || met === undefined) return <Tag tone="quiet">No status</Tag>;
  return met ? <Tag tone="solid">✓ Target met</Tag> : <Tag tone="dashed">✗ Target not met</Tag>;
}

export function SimTag({ children = "Simulated" }: { children?: React.ReactNode }) {
  return <Tag tone="sage">{children}</Tag>;
}
