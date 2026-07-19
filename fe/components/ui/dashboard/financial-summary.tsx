const metrics = [
  { value: "$75,403,805", label: "Budget remaining", note: "66% utilised", progress: 66, color: "#34d399" },
  { value: "8 months", label: "Schedule remaining", note: "40% completed", progress: 40, color: "#6ee7b7" },
  { value: "$4,930,000", label: "Contingency remaining", note: "32% used", progress: 32, color: "#34d399" },
  { value: "$150,000", label: "Pending changes", note: "2 changes, 3 edits", progress: null, color: "#71717a" },
] as const;

export function FinancialSummary() {
  return (
    <section className="h-full rounded-2xl border border-white/[0.08] bg-[#0f1210] p-5 sm:p-6">
      <header>
        <h3 className="text-base font-semibold tracking-[-0.02em] text-zinc-100 sm:text-lg">Financial summary</h3>
        <p className="mt-1 text-sm text-zinc-500">Budget capacity and current change exposure.</p>
      </header>
      <div className="mt-5 grid overflow-hidden rounded-xl border border-white/[0.07] sm:grid-cols-2">
        {metrics.map((metric, index) => (
          <div
            key={metric.label}
            className={`min-w-0 p-5 ${index > 0 ? "border-t border-white/[0.07]" : ""} ${
              index % 2 === 1 ? "sm:border-l" : ""
            } ${index === 1 ? "sm:border-t-0" : ""}`}
          >
            <p className="font-mono text-xl font-semibold tracking-[-0.03em] text-zinc-100 sm:text-2xl">{metric.value}</p>
            <p className="mt-1 text-sm text-zinc-400">{metric.label}</p>
            {metric.progress !== null && (
              <div className="mt-5 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                <div className="h-full" style={{ width: `${metric.progress}%`, backgroundColor: metric.color }} />
              </div>
            )}
            <p className="mt-2 text-xs text-zinc-500">{metric.note}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
