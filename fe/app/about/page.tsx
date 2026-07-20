import { PageTransition } from "@/components/ui/page-transition";
import { ContractFormCheck } from "./contract-form-check";

export default function AboutPage() {
  return (
    <PageTransition>
      <div className="flex w-full flex-1 flex-col gap-8 text-[var(--fin-text)]">
        <section className="mx-auto w-full max-w-5xl">
          <article className="rounded-2xl border border-emerald-400/20 bg-[var(--fin-surface)]/95 px-6 py-7 shadow-[0_24px_80px_rgba(0,0,0,.18)] ring-1 ring-white/[0.05] backdrop-blur sm:px-8 sm:py-9">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
              FinWise Finance AI
            </p>
            <h1 className="mt-3 max-w-3xl text-balance text-3xl font-bold tracking-[-0.035em] sm:text-5xl">
              Khởi tạo hồ sơ phân tích hợp đồng
            </h1>
            <p className="mt-4 max-w-2xl text-pretty text-base leading-7 text-[var(--fin-muted)] sm:text-lg">
              Nhập thông tin hợp đồng và nhu cầu vốn để các Finance, Risk và Decision
              Agent cùng đánh giá hồ sơ.
            </p>
          </article>
        </section>

        <ContractFormCheck />
      </div>
    </PageTransition>
  );
}
