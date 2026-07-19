const sources = [
  { label: "Cash Equity", funded: "2.25", remaining: "0.75", percent: 70 },
  { label: "Citibank Loan", funded: "2.25", remaining: "2.75", percent: 60 },
] as const;

export function FundingSourcesChart() {
  return (
    <section className="h-full rounded-2xl border border-white/[0.08] bg-[#0f1210] p-5 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold tracking-[-0.02em] text-zinc-100 sm:text-lg">Funding sources</h3>
          <p className="mt-1 text-sm text-zinc-500">Drawn capital and remaining capacity.</p>
        </div>
        <div className="flex gap-4 text-xs text-zinc-400">
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-400" />Funded</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-zinc-700" />Remaining</span>
        </div>
      </header>
      <div className="mt-6 space-y-5">
        {sources.map((source) => (
          <div key={source.label} className="grid items-center gap-3 sm:grid-cols-[120px_minmax(0,1fr)]">
            <span className="text-sm text-zinc-400">{source.label}</span>
            <div className="flex h-11 overflow-hidden rounded-xl bg-white/[0.06] font-mono text-xs">
              <div className="flex items-center justify-center font-semibold text-[#07110c]" style={{ width: `${source.percent}%`, backgroundColor: "#34d399" }}>{source.funded}</div>
              <div className="flex flex-1 items-center justify-center text-white">{source.remaining}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
