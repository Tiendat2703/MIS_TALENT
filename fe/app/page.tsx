import Link from "next/link";
import { Activity, Bot, ChartNoAxesCombined } from "lucide-react";

import Bar from "@/components/ui/about/Bar";
import { BackgroundPaths } from "@/components/ui/background-paths";
import { PageTransition } from "@/components/ui/page-transition";

const highlights = [
  {
    title: "Budget control",
    description: "Track budget, actual spend, cash flow, and variance in one finance cockpit.",
    icon: ChartNoAxesCombined,
  },
  {
    title: "Agent pipeline",
    description: "Monitor AI agents as they scan signals, assess risk, and prepare execution steps.",
    icon: Bot,
  },
  {
    title: "Risk signals",
    description: "Surface schedule, contingency, and forecast issues before they become blockers.",
    icon: Activity,
  },
] as const;

export default function Home() {
  return (
    <BackgroundPaths
      className="min-h-[100dvh] overflow-hidden bg-[var(--fin-bg)]"
      svgOptions={{ duration: 8 }}
    >
      <Bar />
      <PageTransition>
        <main className="relative mx-auto flex min-h-[100dvh] w-full max-w-6xl flex-col justify-center px-6 pb-14 pt-32 text-[var(--fin-text)] sm:px-10 lg:px-16">
          <section className="max-w-3xl">
            <p className="text-sm font-medium uppercase tracking-[0.22em] text-emerald-300/80">
              Finance AI Workspace
            </p>
            <h1 className="mt-5 text-balance text-5xl font-semibold leading-[0.95] tracking-tight text-[var(--fin-text)] sm:text-6xl lg:text-7xl">
              FinWise
            </h1>
            <p className="mt-6 max-w-2xl text-pretty text-lg leading-8 text-[var(--fin-muted)] sm:text-xl">
              A focused command center for finance teams to review performance,
              coordinate AI agents, and act on risk signals with less friction.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/dashboard"
                className="inline-flex h-12 items-center justify-center rounded-md bg-emerald-400 px-5 text-sm font-semibold text-black transition-colors hover:bg-emerald-300"
              >
                Open Dashboard
              </Link>
              <Link
                href="/agent"
                className="inline-flex h-12 items-center justify-center rounded-md border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] px-5 text-sm font-semibold text-[var(--fin-text)] transition-colors hover:border-emerald-400/40 hover:bg-emerald-400/10 hover:text-emerald-700"
              >
                View AI Agents
              </Link>
            </div>
          </section>

          <section className="mt-14 grid gap-4 md:grid-cols-3">
            {highlights.map((item) => {
              const Icon = item.icon;

              return (
                <article
                  key={item.title}
                  className="rounded-lg border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]/90 p-5 shadow-[0_18px_60px_rgba(0,0,0,.16)] ring-1 ring-white/[0.04] backdrop-blur"
                >
                  <Icon className="size-5 text-emerald-300" aria-hidden="true" />
                  <h2 className="mt-5 text-base font-semibold text-[var(--fin-text)]">
                    {item.title}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-[var(--fin-muted)]">
                    {item.description}
                  </p>
                </article>
              );
            })}
          </section>
        </main>
      </PageTransition>
    </BackgroundPaths>
  );
}
