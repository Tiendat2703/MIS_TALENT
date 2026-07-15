"use client";

import Bar from "@/components/ui/about/Bar";

export default function DashboardError({ reset }: { reset: () => void }) {
  return (
    <main className="relative flex min-h-[100dvh] w-full items-center justify-center bg-black px-4 pb-12 pt-28 text-zinc-300 sm:px-6 lg:px-8 xl:px-10">
      <Bar
        align="right"
        title={
          <h1 className="shrink-0 text-xl font-semibold tracking-tight text-emerald-400 sm:text-2xl lg:text-3xl">
            Financial Dashboard
          </h1>
        }
      />

      <section className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#0f1210] p-6 text-center sm:p-8">
        <h2 className="text-xl font-semibold tracking-[-0.03em] text-zinc-100">Dashboard unavailable</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-zinc-400">
          We could not load the current financial data. Retry to request the latest reporting state.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-6 min-h-11 rounded-xl bg-emerald-300 px-5 text-sm font-semibold text-[#07110c] transition-colors hover:bg-emerald-200 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0f1210]"
        >
          Retry
        </button>
      </section>
    </main>
  );
}
