import type { ReactNode } from "react";

import { BackgroundPaths } from "@/components/ui/background-paths";
import Bar from "@/components/ui/about/Bar";

export default function AboutLayout({ children }: { children: ReactNode }) {
  return (
    <BackgroundPaths
      className="min-h-[100dvh] overflow-hidden bg-black"
      svgOptions={{ duration: 8 }}
    >
      <Bar />
      <main className="relative mx-auto flex min-h-[100dvh] w-full max-w-6xl items-center justify-center px-6 py-28 sm:px-10 lg:px-16">
        {children}
      </main>
    </BackgroundPaths>
  );
}
