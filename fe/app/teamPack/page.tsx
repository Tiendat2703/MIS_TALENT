import type { Metadata } from "next";

import Bar from "@/components/ui/about/Bar";
import { PageTransition } from "@/components/ui/page-transition";
import { TeamPackWorkspace } from "./team-pack-workspace";

export const metadata: Metadata = {
  title: "Kho dữ liệu | MIS Agent",
  description: "Kiểm tra dữ liệu Supabase và chọn hợp đồng để chạy AI Agent.",
};

export default function TeamPackPage() {
  return (
    <PageTransition>
      <main className="relative min-h-[100dvh] overflow-x-clip bg-[var(--fin-bg)] px-4 pb-10 pt-28 text-[var(--fin-text)] sm:px-6 sm:pt-32 lg:px-8 xl:px-10">
        <Bar />
        <TeamPackWorkspace />
      </main>
    </PageTransition>
  );
}
