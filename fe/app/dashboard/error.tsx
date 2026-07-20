"use client";

import Bar from "@/components/ui/about/Bar";

export default function DashboardError({ reset }: { reset: () => void }) {
  return (
    <main className="relative flex min-h-[100dvh] w-full items-center justify-center bg-[radial-gradient(circle_at_50%_20%,rgba(52,211,153,0.06),transparent_30%),var(--fin-bg)] px-4 pb-12 pt-28 text-[var(--fin-text)] sm:px-6 lg:px-8 xl:px-10">
      <Bar
        align="right"
        title={
          <span className="hidden shrink-0 items-center gap-2 text-sm font-semibold tracking-[-0.02em] text-[var(--fin-text)] sm:flex">
            <span className="size-2 rounded-sm bg-emerald-300" aria-hidden="true" />
            Contract desk
          </span>
        }
      />

      <section className="w-full max-w-md rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-6 text-center sm:p-8">
        <span className="mx-auto flex size-10 items-center justify-center rounded-lg border border-rose-300/15 bg-rose-300/[0.06] text-sm font-semibold text-rose-200">×</span>
        <h1 className="mt-5 text-xl font-semibold tracking-[-0.035em] text-[var(--fin-text)]">Không tải được hàng chờ hợp đồng</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-[var(--fin-muted)]">
          Dữ liệu phê duyệt hiện chưa sẵn sàng. Thử tải lại để lấy trạng thái mới nhất từ pipeline.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-6 min-h-11 rounded-lg bg-emerald-300 px-5 text-sm font-semibold text-[#07110c] transition-colors hover:bg-emerald-200 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--fin-surface)]"
        >
          Tải lại dashboard
        </button>
      </section>
    </main>
  );
}
