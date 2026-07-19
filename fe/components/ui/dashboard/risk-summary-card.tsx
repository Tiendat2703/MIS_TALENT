"use client";

interface RiskItem {
  id: string;
  title: string;
  category: string;
  description: string;
  severity: "Critical" | "Warning" | "Low";
}

const mockRisks: RiskItem[] = [
  {
    id: "RSK-001",
    title: "Over-exposure on Welding Labor",
    category: "Labor",
    description: "Welding sub-crew is exceeding standard shifts, leading to safety exposure and burnout.",
    severity: "Critical",
  },
  {
    id: "RSK-002",
    title: "Drywall Logistics Disruption",
    category: "Materials",
    description: "Regional transit strike threatens delivery schedules of finishing materials.",
    severity: "Warning",
  },
  {
    id: "RSK-003",
    title: "Zoning Board Review Backlog",
    category: "Land",
    description: "City permits office is delayed in processing foundation adjustments.",
    severity: "Warning",
  },
  {
    id: "RSK-004",
    title: "Contingency Fund Speed Run",
    category: "Contingency",
    description: "Drawdown rate of emergency budget is 38% ahead of initial schedule baseline.",
    severity: "Warning",
  },
  {
    id: "RSK-005",
    title: "Copper Cabling Price Spike",
    category: "Materials",
    description: "LME copper spot prices increased by 8.5% over the past two weeks.",
    severity: "Low",
  },
  {
    id: "RSK-006",
    title: "Rainwater Site Runoff Audit",
    category: "Compliance",
    description: "Pending environmental check on temporary drainage solutions.",
    severity: "Low",
  },
];

export function RiskSummaryCard() {
  const severityBadgeColor = {
    Critical: "bg-red-400/10 text-red-400 border-red-400/20",
    Warning: "bg-amber-400/10 text-amber-300 border-amber-400/20",
    Low: "bg-emerald-400/10 text-emerald-300 border-emerald-400/20",
  };

  return (
    <article className="h-full flex flex-col rounded-2xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-5 sm:p-6 transition-colors duration-200">
      <header className="flex items-center justify-between border-b border-[var(--fin-soft-border)] pb-4">
        <div>
          <h3 className="text-base font-semibold tracking-[-0.02em] text-[var(--fin-text)] sm:text-lg">Risk Summary</h3>
          <p className="mt-1 text-sm text-[var(--fin-muted)]">Active threats across all project categories.</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 bg-red-400/10 text-red-400 border border-red-400/20 px-2 py-0.5 rounded-full text-xs font-bold font-mono">
          6 Total Risks
        </div>
      </header>

      <div className="mt-4 flex-1 overflow-y-auto pr-1 max-h-[360px] space-y-3 divide-y divide-[var(--fin-soft-border)]/50">
        {mockRisks.map((risk, index) => (
          <div key={risk.id} className={`pt-3 ${index === 0 ? "pt-0" : ""}`}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <span className="text-[10px] font-mono text-[var(--fin-muted)] bg-[var(--fin-bg)] px-1.5 py-0.5 rounded border border-[var(--fin-soft-border)]">
                  {risk.id}
                </span>
                <span className="ml-2 text-[10px] font-semibold text-[var(--fin-muted)] uppercase">
                  {risk.category}
                </span>
                <h4 className="mt-1.5 text-xs font-bold text-[var(--fin-text)]">
                  {risk.title}
                </h4>
              </div>
              <span className={`rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase shrink-0 ${severityBadgeColor[risk.severity]}`}>
                {risk.severity}
              </span>
            </div>
            <p className="mt-1 text-xs text-[var(--fin-muted)] leading-relaxed">
              {risk.description}
            </p>
          </div>
        ))}
      </div>
    </article>
  );
}
