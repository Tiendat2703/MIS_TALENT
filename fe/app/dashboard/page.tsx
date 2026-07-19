"use client";

import { useState } from "react";
import {
  AiBackingCard,
  AiPredictionsCard,
  BudgetActualsChart,
  BudgetActualsTable,
  CashFlowChart,
  ContingencyUsageChart,
  FinancialSummary,
  FundingSourcesChart,
  ProjectOverview,
  ScheduleRiskChart,
  SelectedCategoryDetails,
  RiskSummaryCard,
  CreditCasesTable,
} from "@/components/ui/dashboard";
import Bar from "@/components/ui/about/Bar";
import { PageTransition } from "@/components/ui/page-transition";
import { motion, AnimatePresence } from "motion/react";

const cardClass =
  "min-w-0 overflow-hidden rounded-2xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-5 transition-colors duration-200 hover:border-emerald-400/25 sm:p-6";

const metrics = [
  { label: "Total project budget", value: "$15.0M", note: "Approved baseline", tone: "text-[var(--fin-text)]" },
  { label: "Total spent", value: "$9.5M", note: "63% used", tone: "text-[var(--fin-text)]" },
  { label: "Remaining budget", value: "$5.5M", note: "37% available", tone: "text-emerald-300" },
  { label: "Revenue forecast", value: "$22.0M", note: "46% projected ROI", tone: "text-emerald-300" },
] as const;

const metricBorders = [
  "",
  "border-t border-[var(--fin-soft-border)] sm:border-l sm:border-t-0",
  "border-t border-[var(--fin-soft-border)] xl:border-l xl:border-t-0",
  "border-t border-[var(--fin-soft-border)] sm:border-l xl:border-t-0",
] as const;

function PanelHeading({ title, description }: { title: string; description: string }) {
  return (
    <header className="mb-5">
      <h2 className="text-base font-semibold tracking-[-0.02em] text-[var(--fin-text)] sm:text-lg">{title}</h2>
      <p className="mt-1 text-sm leading-5 text-[var(--fin-muted)]">{description}</p>
    </header>
  );
}

export default function DashboardPage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  return (
    <PageTransition>
      <main className="relative min-h-[100dvh] w-full max-w-full overflow-x-clip bg-[var(--fin-bg)] px-4 pb-12 pt-28 text-[var(--fin-text)] sm:px-6 lg:px-8 xl:px-10">
        <Bar
          align="right"
          title={
            <h1 className="shrink-0 text-xl font-semibold tracking-tight text-emerald-400 sm:text-2xl lg:text-3xl">
              Financial Dashboard
            </h1>
          }
        />

        <div className="min-w-0 max-w-full">
          <section aria-label="Financial summary" className="grid overflow-hidden rounded-2xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] sm:grid-cols-2 xl:grid-cols-4">
            {metrics.map((metric, index) => (
              <div
                key={metric.label}
                className={`min-w-0 px-5 py-5 sm:px-6 ${metricBorders[index]}`}
              >
                <p className="text-xs font-medium text-[var(--fin-muted)]">{metric.label}</p>
                <p className={`mt-2 font-mono text-2xl font-semibold tracking-[-0.04em] sm:text-3xl ${metric.tone}`}>
                  {metric.value}
                </p>
                <p className="mt-1 text-xs text-[var(--fin-muted)]">{metric.note}</p>
              </div>
            ))}
          </section>

          <div className="mt-4 grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-12">
            <motion.section
              layout
              transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
              className={`${cardClass} ${selectedCategory ? "lg:col-span-8" : "lg:col-span-12"}`}
            >
              <PanelHeading title="Budget vs actuals" description="Planned and recorded spend by cost category. Click a row to view reasoning." />
              <BudgetActualsChart />
              <div className="mt-6 min-w-0 max-w-full">
                <BudgetActualsTable
                  selectedCategory={selectedCategory || ""}
                  onSelectCategory={setSelectedCategory}
                />
              </div>
            </motion.section>

            <AnimatePresence mode="popLayout">
              {selectedCategory && (
                <motion.section
                  initial={{ opacity: 0, x: 30, scale: 0.98 }}
                  animate={{ opacity: 1, x: 0, scale: 1 }}
                  exit={{ opacity: 0, x: 30, scale: 0.98 }}
                  transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  className="lg:col-span-4 min-w-0 h-full"
                >
                  <SelectedCategoryDetails
                    category={selectedCategory}
                    onClose={() => setSelectedCategory(null)}
                  />
                </motion.section>
              )}
            </AnimatePresence>

            <section className={`${cardClass} lg:col-span-8`}>
              <PanelHeading title="Credit Case Approvals" description="Loan requests validation pipeline." />
              <CreditCasesTable />
            </section>

            <section className="lg:col-span-4 min-w-0 h-full">
              <RiskSummaryCard />
            </section>

            <section className={`${cardClass} lg:col-span-8`}>
              <PanelHeading title="Cash flow" description="Monthly inflow, outflow and net cash position." />
              <CashFlowChart />
            </section>

            <div className="min-w-0 lg:col-span-4"><ProjectOverview /></div>
            <div className="min-w-0 lg:col-span-8"><FinancialSummary /></div>
            <div className="min-w-0 lg:col-span-4"><ContingencyUsageChart /></div>
            <div className="min-w-0 lg:col-span-8"><ScheduleRiskChart /></div>
            <div className="min-w-0 lg:col-span-12"><FundingSourcesChart /></div>

            <div className="min-w-0 lg:col-span-7"><AiPredictionsCard /></div>
            <div className="min-w-0 lg:col-span-5"><AiBackingCard /></div>
          </div>
        </div>
      </main>
    </PageTransition>
  );
}
