const segments = [
  { label: "Total spent", value: "$9,500,000", note: "63% used", color: "#34d399", width: "45%" },
  { label: "Cost overruns", value: "$750,000", note: "5% over", color: "#f87171", width: "20%" },
  { label: "Remaining budget", value: "$5,500,000", note: "37% left", color: "#6ee7b7", width: "25%" },
  { label: "Revenue forecast", value: "$22,000,000", note: "46% ROI", color: "#a1a1aa", width: "10%" },
] as const;

export function BudgetAllocationChart() {
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-zinc-800" role="img" aria-label="Project budget allocation">
        {segments.map((segment) => (
          <span key={segment.label} style={{ width: segment.width, backgroundColor: segment.color }} />
        ))}
      </div>
      <div className="mt-6 divide-y divide-white/[0.07]">
        {segments.map((segment) => (
          <div key={segment.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 py-4 first:pt-0 last:pb-0">
            <div className="min-w-0">
              <p className="text-xs text-zinc-500">{segment.label}</p>
              <p className="mt-1 truncate font-mono text-lg font-semibold text-zinc-100">{segment.value}</p>
            </div>
            <span className="text-xs font-medium" style={{ color: segment.color }}>{segment.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
