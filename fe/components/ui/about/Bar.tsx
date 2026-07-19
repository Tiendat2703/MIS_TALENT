"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import React from "react";
import type { ReactNode } from "react";

import {
  Announcement,
  AnnouncementTitle,
} from "@/components/ui/announcement";
import { ThemeToggle } from "@/components/ui/theme-toggle";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About us" },
  { href: "/agent", label: "AI Agent" },
  { href: "/dashboard", label: "Dashboard" },
] as const;

export default function Bar({
  align = "center",
  title,
}: {
  align?: "center" | "right";
  title?: ReactNode;
}) {
  const pathname = usePathname();

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
        {navItems.map((item, index) => {
          const isActive = pathname === item.href;
          return (
            <React.Fragment key={item.href}>
              {index > 0 && (
                <span className="h-4 w-px shrink-0 bg-[var(--fin-soft-border)]" aria-hidden="true" />
              )}
              <Link href={item.href}>
                <AnnouncementTitle
                  className={`cursor-pointer rounded-full px-3 py-1 font-semibold transition-all duration-300 ease-out hover:bg-emerald-400/10 hover:text-emerald-500 ${
                    isActive
                      ? "text-[var(--fin-text)] bg-emerald-400/10 shadow-[0_0_12px_rgba(52,211,153,0.15)]"
                      : "text-[var(--fin-muted)]"
                  }`}
                >
                  {item.label}
                </AnnouncementTitle>
              </Link>
            </React.Fragment>
          );
        })}
        <ThemeToggle />
      </Announcement>
    </header>
  );
}
