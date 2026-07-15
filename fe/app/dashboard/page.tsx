import {
  AiBackingCard,
  AiPredictionsCard,
  BudgetActualsChart,
  BudgetActualsTable,
  BudgetAllocationChart,
  BudgetBreakdownRadar,
  CashFlowChart,
  ContingencyUsageChart,
  FinancialSummary,
  FundingSourcesChart,
  ProjectOverview,
  ScheduleRiskChart,
} from "@/components/ui/dashboard";
import Bar from "@/components/ui/about/Bar";

const cardClass =
  "min-w-0 overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0f1210] p-5 transition-colors duration-200 hover:border-emerald-400/25 sm:p-6";

const metrics = [
  { label: "Total project budget", value: "$15.0M", note: "Approved baseline", tone: "text-white" },
  { label: "Total spent", value: "$9.5M", note: "63% used", tone: "text-white" },
  { label: "Remaining budget", value: "$5.5M", note: "37% available", tone: "text-emerald-300" },
  { label: "Revenue forecast", value: "$22.0M", note: "46% projected ROI", tone: "text-emerald-300" },
] as const;

const metricBorders = [
  "",
  "border-t border-white/[0.07] sm:border-l sm:border-t-0",
  "border-t border-white/[0.07] xl:border-l xl:border-t-0",
  "border-t border-white/[0.07] sm:border-l xl:border-t-0",
] as const;

function PanelHeading({ title, description }: { title: string; description: string }) {
  return (
    <header className="mb-5">
      <h2 className="text-base font-semibold tracking-[-0.02em] text-zinc-100 sm:text-lg">{title}</h2>
      <p className="mt-1 text-sm leading-5 text-zinc-500">{description}</p>
    </header>
  );
}

export default function DashboardPage() {
  return (
    <main className="relative min-h-[100dvh] w-full max-w-full overflow-x-clip bg-black px-4 pb-12 pt-28 text-zinc-300 sm:px-6 lg:px-8 xl:px-10">
      <Bar
        align="right"
        title={
          <h1 className="shrink-0 text-xl font-semibold tracking-tight text-emerald-400 sm:text-2xl lg:text-3xl">
            Financial Dashboard
          </h1>
        }
      />

      <div className="min-w-0 max-w-full">
        <section aria-label="Financial summary" className="grid overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0b0e0c] sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map((metric, index) => (
            <div
              key={metric.label}
              className={`min-w-0 px-5 py-5 sm:px-6 ${metricBorders[index]}`}
            >
              <p className="text-xs font-medium text-zinc-500">{metric.label}</p>
              <p className={`mt-2 font-mono text-2xl font-semibold tracking-[-0.04em] sm:text-3xl ${metric.tone}`}>
                {metric.value}
              </p>
              <p className="mt-1 text-xs text-zinc-500">{metric.note}</p>
            </div>
          ))}
        </section>

        <div className="mt-4 grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-12">
          <section className={`${cardClass} lg:col-span-8`}>
            <PanelHeading title="Budget vs actuals" description="Planned and recorded spend by cost category." />
            <BudgetActualsChart />
            <div className="mt-6 min-w-0 max-w-full"><BudgetActualsTable /></div>
          </section>

          <section className={`${cardClass} lg:col-span-4`}>
            <PanelHeading title="Budget allocation" description="How the approved budget is currently distributed." />
            <BudgetAllocationChart />
          </section>

          <section className={`${cardClass} lg:col-span-8`}>
            <PanelHeading title="Cash flow" description="Monthly inflow, outflow and net cash position." />
            <CashFlowChart />
          </section>

          <section className={`${cardClass} lg:col-span-4`}>
            <PanelHeading title="Budget variance" description="Category exposure against the approved plan." />
            <BudgetBreakdownRadar />
          </section>

          <div className="min-w-0 lg:col-span-4"><ProjectOverview /></div>
          <div className="min-w-0 lg:col-span-8"><FinancialSummary /></div>
          <div className="min-w-0 lg:col-span-8"><ScheduleRiskChart /></div>
          <div className="min-w-0 lg:col-span-4"><ContingencyUsageChart /></div>
          <div className="min-w-0 lg:col-span-12"><FundingSourcesChart /></div>

          <div className="min-w-0 lg:col-span-7"><AiPredictionsCard /></div>
          <div className="min-w-0 lg:col-span-5"><AiBackingCard /></div>
        </div>
      </div>
    </main>
  );
}
