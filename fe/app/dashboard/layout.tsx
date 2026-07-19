import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Financial Overview | FinWise",
  description: "Project budget, cash flow, and financial performance dashboard.",
};

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-[100dvh] w-full max-w-full overflow-x-hidden bg-[var(--fin-bg)]">
      {children}
    </div>
  );
}
