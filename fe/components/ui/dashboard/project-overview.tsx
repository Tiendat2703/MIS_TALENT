const projects = [
  { label: "Active", count: "05", value: "$42.8M", note: "55% complete", progress: 55, color: "#34d399" },
  { label: "Upcoming", count: "03", value: "$18.5M", note: "Not started", progress: 0, color: "#71717a" },
  { label: "Completed", count: "07", value: "$67.3M", note: "100% complete", progress: 100, color: "#6ee7b7" },
] as const;

export function ProjectOverview() {
  return (
    <section className="h-full rounded-2xl border border-white/[0.08] bg-[#0f1210] p-5 sm:p-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold tracking-[-0.02em] text-zinc-100 sm:text-lg">Project overview</h3>
          <p className="mt-1 text-sm text-zinc-500">Portfolio delivery status.</p>
        </div>
        <p className="font-mono text-sm font-semibold text-emerald-300">15 total</p>
      </header>
      <div className="mt-5 divide-y divide-white/[0.07]">
        {projects.map((project) => (
          <div key={project.label} className="py-5 first:pt-0 last:pb-0">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-4">
              <div className="flex items-baseline gap-3">
                <p className="font-mono text-2xl font-semibold text-zinc-100">{project.count}</p>
                <p className="text-sm text-zinc-400">{project.label}</p>
              </div>
              <div className="text-right">
                <p className="font-mono text-sm font-semibold text-zinc-200">{project.value}</p>
                <p className="mt-0.5 text-xs text-zinc-500">{project.note}</p>
              </div>
            </div>
            <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/[0.06]">
              <div className="h-full rounded-full" style={{ width: `${project.progress}%`, backgroundColor: project.color }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
