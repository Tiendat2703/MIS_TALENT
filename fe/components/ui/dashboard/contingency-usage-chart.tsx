export function ContingencyUsageChart() {
  const radius = 78;
  const circumference = 2 * Math.PI * radius;
  const used = circumference * 0.38;

  return (
    <section className="h-full rounded-2xl border border-white/[0.08] bg-[#0f1210] p-5 sm:p-6">
      <header>
        <h3 className="text-base font-semibold tracking-[-0.02em] text-zinc-100 sm:text-lg">Contingency usage</h3>
        <p className="mt-1 text-sm text-zinc-500">Committed reserve by hard-cost category.</p>
      </header>
      <div className="mx-auto mt-5 max-w-[210px]">
        <svg viewBox="0 0 200 200" className="h-auto w-full -rotate-90" role="img" aria-label="38 percent contingency usage">
          <circle cx="100" cy="100" r={radius} fill="none" stroke="#242824" strokeWidth="18" />
          <circle cx="100" cy="100" r={radius} fill="none" stroke="#34d399" strokeWidth="18" strokeDasharray={`${used} ${circumference - used}`} strokeLinecap="round" />
          <text x="100" y="109" textAnchor="middle" fill="white" fontSize="27" fontWeight="700" transform="rotate(90 100 100)">38%</text>
        </svg>
      </div>
      <div className="mt-5 divide-y divide-white/[0.07] border-t border-white/[0.07]">
        <div className="flex items-center justify-between gap-4 py-3"><p className="text-xs text-zinc-400">Electrical</p><p className="font-mono text-sm font-semibold text-emerald-300">$1,500,000</p></div>
        <div className="flex items-center justify-between gap-4 py-3"><p className="text-xs text-zinc-400">Framing</p><p className="font-mono text-sm font-semibold text-zinc-200">$2,000,000</p></div>
      </div>
    </section>
  );
}
