export default function Stat({
  label,
  value,
  sub,
  inverted,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  inverted?: boolean;
}) {
  return (
    <div className={`p-4 ${inverted ? "!bg-ink text-paper" : ""}`}>
      <div className={`kicker ${inverted ? "!text-paper-60" : ""}`}>{label}</div>
      <div className="serif mt-1 text-[30px] font-medium leading-none tracking-[-0.02em]">{value}</div>
      {sub ? (
        <div className={`mt-2 font-mono text-[11px] leading-snug ${inverted ? "text-paper-60" : "text-ink-60"}`}>
          {sub}
        </div>
      ) : null}
    </div>
  );
}

/** Hairline-ruled grid of Stat cells. */
export function StatGrid({ children, cols = 4 }: { children: React.ReactNode; cols?: 2 | 3 | 4 | 5 | 6 }) {
  const c = {
    2: "lg:grid-cols-2",
    3: "lg:grid-cols-3",
    4: "lg:grid-cols-4",
    5: "lg:grid-cols-5",
    6: "lg:grid-cols-6",
  }[cols];
  return (
    <div className={`grid grid-cols-1 gap-px border border-ink-15 bg-ink-15 sm:grid-cols-2 ${c} [&>*]:bg-paper`}>
      {children}
    </div>
  );
}
