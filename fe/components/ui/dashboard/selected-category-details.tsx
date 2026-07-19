"use client";

interface CategoryData {
  fullName: string;
  reason: string;
  riskLevel: "Low" | "Medium" | "High";
  riskDescription: string;
  mitigation: string;
  status: string;
}

const categoryDetails: Record<string, CategoryData> = {
  Land: {
    fullName: "Land Acquisition & Development",
    reason: "Unexpected permit fees and zoning adjustment charges required by local municipal office during code compliance review.",
    riskLevel: "Medium",
    riskDescription: "Delay in municipal clearance could stall structural excavation phase by up to 3 weeks.",
    mitigation: "Pre-arranged legal consult with zoning attorney to speed up local code appeals.",
    status: "Over Budget",
  },
  Construction: {
    fullName: "Structural Construction & Engineering",
    reason: "Optimized steel purchase contract resulting in 4% discount on raw material costs under fixed-volume terms.",
    riskLevel: "Low",
    riskDescription: "Minor supplier logistics delays due to regional transport union warning strikes.",
    mitigation: "Signed secondary supplier SLA with local concrete and steel distributor as contingency.",
    status: "Under Budget",
  },
  Labor: {
    fullName: "Direct Labor & Contractor Crew",
    reason: "Additional skilled welding crews hired for overtime to meet advanced foundation deadline ahead of heavy rain season.",
    riskLevel: "High",
    riskDescription: "Overtime burnout leading to quality checks failure or safety incidents on the floor.",
    mitigation: "Rotating shift schedules and additional on-site safety coordinator appointed.",
    status: "Over Budget",
  },
  Materials: {
    fullName: "Raw Materials & Finishes Procurement",
    reason: "Slight market stabilization for dry-wall and plumbing parts compared to project baseline estimations.",
    riskLevel: "Low",
    riskDescription: "Price volatility in copper wiring could impact secondary electrical phase.",
    mitigation: "Fixed-price contract signed for electrical materials for the next 6 months.",
    status: "Under Budget",
  },
};

interface SelectedCategoryDetailsProps {
  category: string | null;
}

export function SelectedCategoryDetails({ category }: SelectedCategoryDetailsProps) {
  if (!category) {
    return (
      <article className="h-full flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--fin-soft-border)] bg-[var(--fin-surface)]/20 p-6 text-center text-[var(--fin-muted)] min-h-[350px] transition-colors duration-200">
        <span className="text-2xl mb-2">📊</span>
        <h4 className="text-sm font-semibold text-[var(--fin-text)]">No Category Selected</h4>
        <p className="mt-1 text-xs text-[var(--fin-muted)] max-w-[200px] mx-auto leading-relaxed">
          Click a row in the Budget vs Actuals table to view variance details and risk mitigation.
        </p>
      </article>
    );
  }

  const data = categoryDetails[category] || categoryDetails.Land;

  const riskBadgeColor = {
    Low: "bg-emerald-400/10 text-emerald-300 border-emerald-400/20",
    Medium: "bg-amber-400/10 text-amber-300 border-amber-400/20",
    High: "bg-red-400/10 text-red-300 border-red-400/20",
  }[data.riskLevel];

  const statusBadgeColor = data.status === "Over Budget"
    ? "bg-red-400/10 text-red-300 border-red-400/20"
    : "bg-emerald-400/10 text-emerald-300 border-emerald-400/20";

  return (
    <article className="h-full rounded-2xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)] p-5 sm:p-6 transition-colors duration-200">
      <header className="flex items-start justify-between gap-4 border-b border-[var(--fin-soft-border)] pb-4">
        <div>
          <span className="text-[10px] uppercase tracking-wider text-[var(--fin-muted)]">Category Details</span>
          <h3 className="text-base font-bold tracking-tight text-[var(--fin-text)] sm:text-lg mt-0.5">
            {data.fullName}
          </h3>
        </div>
        <div className="flex flex-col gap-1.5 items-end shrink-0">
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${statusBadgeColor}`}>
            {data.status}
          </span>
        </div>
      </header>

      <div className="mt-5 space-y-5">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--fin-muted)]">Variance Reason</h4>
          <p className="mt-2 text-sm text-[var(--fin-text)] leading-relaxed bg-[var(--fin-bg)]/40 rounded-xl p-3 border border-[var(--fin-soft-border)]">
            {data.reason}
          </p>
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--fin-muted)]">Risk Level & Details</h4>
          <div className="mt-2 bg-[var(--fin-bg)]/40 rounded-xl p-3 border border-[var(--fin-soft-border)] space-y-2.5">
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--fin-muted)]">Assessment:</span>
              <span className={`rounded-md border px-1.5 py-0.5 text-[10px] font-bold uppercase ${riskBadgeColor}`}>
                {data.riskLevel} Risk
              </span>
            </div>
            <p className="text-sm text-[var(--fin-text)] leading-relaxed">
              {data.riskDescription}
            </p>
          </div>
        </div>

        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-[var(--fin-muted)]">Mitigation Strategy</h4>
          <p className="mt-2 text-sm text-[var(--fin-text)] leading-relaxed bg-[var(--fin-bg)]/40 rounded-xl p-3 border border-[var(--fin-soft-border)]">
            {data.mitigation}
          </p>
        </div>
      </div>
    </article>
  );
}
