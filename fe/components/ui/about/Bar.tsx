import Link from "next/link";
import type { ReactNode } from "react";

import {
  Announcement,
  AnnouncementTitle,
} from "@/components/ui/announcement";
import { ThemeToggle } from "@/components/ui/theme-toggle";

export default function Bar({
  align = "center",
  title,
}: {
  align?: "center" | "right";
  title?: ReactNode;
}) {
  return (
    <header
      className={`absolute inset-x-0 top-0 z-20 flex px-4 py-5 sm:px-6 sm:py-8 lg:px-8 xl:px-10 ${
        title ? "items-center justify-between gap-4" : align === "right" ? "justify-end" : "justify-center"
      }`}
    >
      {title}
      <Announcement
        styled
        shiny
        movingBorder
        className="max-w-[94vw] border-emerald-400/25 bg-[var(--fin-surface)]/95 px-5 py-3 text-sm text-[var(--fin-text)] shadow-[0_18px_50px_rgba(0,0,0,.25)] ring-1 ring-white/[0.06] backdrop-blur-xl transition-colors duration-300 ease-out hover:bg-[var(--fin-surface-raised)] sm:px-8 sm:py-4 sm:text-base"
        movingBorderClassName="bg-[radial-gradient(#34d399_40%,transparent_60%)]"
      >
        <Link href="/">
          <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-[var(--fin-text)] transition-colors duration-300 ease-out hover:bg-emerald-400/10 hover:text-emerald-500">
            Home
          </AnnouncementTitle>
        </Link>
        <span className="h-4 w-px shrink-0 bg-[var(--fin-soft-border)]" aria-hidden="true" />
        <Link href="/about">
          <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-[var(--fin-muted)] transition-colors duration-300 ease-out hover:bg-emerald-400/10 hover:text-emerald-500">
            About us
          </AnnouncementTitle>
        </Link>
        <span className="h-4 w-px shrink-0 bg-[var(--fin-soft-border)]" aria-hidden="true" />
        <Link href="/agent">
          <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-[var(--fin-muted)] transition-colors duration-300 ease-out hover:bg-emerald-400/10 hover:text-emerald-500">
            AI Agent
          </AnnouncementTitle>
        </Link>
        <span className="h-4 w-px shrink-0 bg-[var(--fin-soft-border)]" aria-hidden="true" />
        <Link href="/dashboard">
          <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-[var(--fin-muted)] transition-colors duration-300 ease-out hover:bg-emerald-400/10 hover:text-emerald-500">
            Dashboard
          </AnnouncementTitle>
        </Link>
        <ThemeToggle />
      </Announcement>
    </header>
  );
}
