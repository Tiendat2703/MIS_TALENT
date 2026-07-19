const bars = [
  { height: 42, color: "#34d399", opacity: .4 }, { height: 58, color: "#34d399", opacity: .5 },
  { height: 78, color: "#34d399", opacity: .65 }, { height: 98, color: "#34d399", opacity: .8 },
  { height: 118, color: "#34d399", opacity: 1 }, { height: 96, color: "#34d399", opacity: .85 },
  { height: 80, color: "#f87171", opacity: .45 }, { height: 64, color: "#f87171", opacity: .6 },
  { height: 98, color: "#f87171", opacity: .8 }, { height: 138, color: "#f87171", opacity: 1 },
  { height: 105, color: "#f87171", opacity: .7 }, { height: 122, color: "#34d399", opacity: .8 },
  { height: 158, color: "#34d399", opacity: 1 }, { height: 128, color: "#34d399", opacity: .9 },
] as const;

export function ScheduleRiskChart() {
  return (
    <section className="h-full rounded-2xl border border-white/[0.08] bg-[#0f1210] p-5 sm:p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold tracking-[-0.02em] text-zinc-100 sm:text-lg">Schedule risk</h3>
          <p className="mt-1 text-sm text-zinc-500">Monthly distribution of delivery exposure.</p>
        </div>
        <div className="flex gap-4 text-xs text-zinc-400">
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-red-400" />High risk</span>
          <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-emerald-400" />Low risk</span>
        </div>
      </header>
      <div className="mt-8 flex h-56 items-end justify-between gap-1 px-2" role="img" aria-label="Schedule risk from January to August">
        {bars.map((bar, index) => <span key={index} className="w-2.5 rounded-t" style={{ height: bar.height, backgroundColor: bar.color, opacity: bar.opacity }} />)}
      </div>
      <div className="mt-4 grid grid-cols-8 text-center text-[10px] text-zinc-500">{["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"].map((month) => <span key={month}>{month}</span>)}</div>
    </section>
  );
}
