import type { ReactNode } from "react";

import { BackgroundPaths } from "@/components/ui/background-paths";
import Bar from "@/components/ui/about/Bar";

export default function AboutLayout({ children }: { children: ReactNode }) {
  return (
    <BackgroundPaths
      className="min-h-[100dvh] overflow-x-hidden bg-[var(--fin-bg)]"
      svgOptions={{ duration: 8 }}
    >
      <Bar />
      <main className="relative mx-auto flex min-h-[100dvh] w-full max-w-7xl items-start justify-center px-4 pb-16 pt-32 sm:px-8 sm:pt-36 lg:px-12">
        {children}
      </main>
    </BackgroundPaths>
  );
}
