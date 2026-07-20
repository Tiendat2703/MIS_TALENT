import Bar from "@/components/ui/about/Bar";
import { ContractApprovalWorkspace } from "@/components/ui/dashboard/contract-approval-workspace";
import { PageTransition } from "@/components/ui/page-transition";

export default function DashboardPage() {
  return (
    <PageTransition>
      <main className="relative min-h-[100dvh] w-full max-w-full overflow-x-clip bg-[radial-gradient(circle_at_8%_0%,rgba(52,211,153,0.055),transparent_27%),var(--fin-bg)] px-4 pb-14 pt-28 text-[var(--fin-text)] sm:px-6 lg:px-8 xl:px-10">
        <Bar
          align="right"
          title={
            <span className="hidden shrink-0 items-center gap-2 text-sm font-semibold tracking-[-0.02em] text-[var(--fin-text)] sm:flex">
              <span className="size-2 rounded-sm bg-emerald-300" aria-hidden="true" />
              Contract desk
            </span>
          }
        />
        <ContractApprovalWorkspace />
      </main>
    </PageTransition>
  );
}
