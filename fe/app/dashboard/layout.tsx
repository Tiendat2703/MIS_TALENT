import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Contract Approvals | FinWise",
  description: "Review contracts, AI recommendations, cash flow, enterprise risk exposure, and approval decisions in one workspace.",
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-[100dvh] w-full max-w-full overflow-x-hidden bg-[var(--fin-bg)]">
      {children}
    </div>
  );
}
