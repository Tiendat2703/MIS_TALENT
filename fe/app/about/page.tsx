import { PageTransition } from "@/components/ui/page-transition";

export default function AboutPage() {
  return (
    <PageTransition>
      <div className="flex flex-1 items-center justify-center w-full">
        <section className="w-full max-w-3xl text-center text-[var(--fin-text)]">
          <article className="rounded-3xl border border-emerald-400/20 bg-[var(--fin-surface)] px-6 py-8 shadow-[0_24px_80px_rgba(0,0,0,.18)] ring-1 ring-white/[0.05] sm:px-10 sm:py-12">
            <h1 className="text-balance text-4xl font-bold tracking-[-0.04em] sm:text-6xl">
              <span className="text-emerald-400">No.1 Solution: </span>
              <span className="text-[var(--fin-text)]">
                 AI assistant for your Finance Department
              </span>
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-pretty text-lg leading-8 text-[var(--fin-muted)]">
              Our platform turns complex signals into clear, actionable insights so
              teams can understand risk and move forward with confidence.
            </p>
          </article>
        </section>
      </div>
    </PageTransition>
  );
}
