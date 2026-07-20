import Bar from "@/components/ui/about/Bar";

export default function DashboardLoading() {
  return (
    <main className="relative min-h-[100dvh] w-full overflow-hidden bg-[radial-gradient(circle_at_8%_0%,rgba(52,211,153,0.055),transparent_27%),var(--fin-bg)] px-4 pb-14 pt-28 text-[var(--fin-text)] sm:px-6 lg:px-8 xl:px-10">
      <Bar
        align="right"
        title={
          <span className="hidden shrink-0 items-center gap-2 text-sm font-semibold tracking-[-0.02em] text-[var(--fin-text)] sm:flex">
            <span className="size-2 rounded-sm bg-emerald-300" aria-hidden="true" />
            Contract desk
          </span>
        }
      />

      <div className="mx-auto w-full max-w-[1600px] animate-pulse motion-reduce:animate-none">
        <div className="mb-5">
          <div className="h-6 w-36 rounded-md bg-emerald-400/[0.07]" />
          <div className="mt-4 h-11 w-[34rem] max-w-full rounded-lg bg-white/[0.07]" />
          <div className="mt-3 h-4 w-[28rem] max-w-full rounded bg-white/[0.04]" />
        </div>

        <div className="grid overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="border-b border-[var(--fin-soft-border)] px-5 py-5 sm:border-b-0 sm:border-r sm:last:border-r-0">
              <div className="h-3 w-24 rounded bg-white/[0.05]" />
              <div className="mt-3 h-8 w-28 rounded bg-white/[0.08]" />
              <div className="mt-2 h-3 w-32 rounded bg-white/[0.04]" />
            </div>
          ))}
        </div>

        <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_23rem]">
          <div className="overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
            <div className="border-b border-[var(--fin-soft-border)] p-5">
              <div className="h-5 w-40 rounded bg-white/[0.07]" />
              <div className="mt-4 h-9 w-full rounded-lg bg-white/[0.035]" />
            </div>
            <div className="space-y-px">
              {[0, 1, 2, 3, 4].map((row) => (
                <div key={row} className="grid grid-cols-[2fr_1fr_1fr_1fr] gap-5 border-b border-[var(--fin-soft-border)] px-5 py-5 last:border-b-0">
                  <div className="h-8 rounded bg-white/[0.06]" />
                  <div className="h-8 rounded bg-white/[0.04]" />
                  <div className="h-8 rounded bg-white/[0.04]" />
                  <div className="h-8 rounded bg-white/[0.05]" />
                </div>
              ))}
            </div>
          </div>

          <div className="min-h-[36rem] rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-5">
            <div className="h-3 w-20 rounded bg-emerald-400/[0.08]" />
            <div className="mt-3 h-6 w-56 max-w-full rounded bg-white/[0.07]" />
            <div className="mt-5 h-16 rounded-lg bg-white/[0.04]" />
            <div className="mt-6 h-3 w-28 rounded bg-white/[0.05]" />
            <div className="mt-4 space-y-3">
              {[0, 1, 2].map((row) => <div key={row} className="h-12 rounded-lg bg-white/[0.035]" />)}
            </div>
          </div>
        </div>

        <div className="mt-12 border-t border-[var(--fin-soft-border)] pt-8">
          <div className="h-6 w-72 max-w-full rounded bg-white/[0.07]" />
          <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(20rem,.75fr)]">
            <div className="h-[27rem] rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-5">
              <div className="h-5 w-40 rounded bg-white/[0.07]" />
              <div className="mt-8 h-[20rem] rounded-lg bg-white/[0.03]" />
            </div>
            <div className="h-[27rem] rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-5">
              <div className="h-5 w-52 rounded bg-white/[0.07]" />
              <div className="mt-8 space-y-5">
                {[0, 1, 2, 3].map((row) => <div key={row} className="h-10 rounded bg-white/[0.035]" />)}
              </div>
            </div>
          </div>

          <div className="mt-5 overflow-hidden rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
            <div className="flex items-start justify-between gap-5 border-b border-[var(--fin-soft-border)] p-5">
              <div className="w-full max-w-lg">
                <div className="h-3 w-36 rounded bg-emerald-400/[0.08]" />
                <div className="mt-3 h-5 w-72 max-w-full rounded bg-white/[0.07]" />
                <div className="mt-2 h-3 w-full rounded bg-white/[0.035]" />
              </div>
              <div className="h-14 w-72 rounded-lg bg-white/[0.04]" />
            </div>
            <div className="grid grid-cols-[1fr_1.2fr_1fr_1fr_2fr_1.5fr] gap-4 px-5 py-5">
              {[0, 1, 2, 3, 4, 5].map((cell) => <div key={cell} className="h-12 rounded bg-white/[0.035]" />)}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
