// import { ArrowRight } from "lucide-react";

// import {
//   Announcement,
//   AnnouncementTitle,
// } from "@/components/ui/announcement";

// export default function Bar() {
//   return (
//     <header className="absolute inset-x-0 top-0 z-20 flex justify-center px-4 py-5 sm:px-6 sm:py-8">
//       <Announcement
//         styled
//         shiny
//         movingBorder
//         className="max-w-[94vw] border-slate-500/60 bg-slate-800/90 px-5 py-3 text-sm text-white shadow-2xl shadow-black/50 ring-1 ring-white/10 backdrop-blur-xl transition-transform duration-300 ease-out hover:scale-[1.02] hover:bg-slate-700/95 sm:px-8 sm:py-4 sm:text-base"
//         movingBorderClassName="bg-[radial-gradient(#34d399_40%,transparent_60%)]"
//       >
//         <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-white transition-all duration-300 ease-out hover:-translate-y-0.5 hover:scale-105 hover:bg-white/10 hover:text-emerald-300">
//           About us
//         </AnnouncementTitle>
//         <span className="h-4 w-px shrink-0 bg-white/20" aria-hidden="true" />
//         <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-slate-200 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:scale-105 hover:bg-white/10 hover:text-emerald-300">
//           AI Agent
//         </AnnouncementTitle>
//         <span className="h-4 w-px shrink-0 bg-white/20" aria-hidden="true" />
//         <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-slate-200 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:scale-105 hover:bg-white/10 hover:text-emerald-300">
//           Dashboard
//         </AnnouncementTitle>
//         <span
//           className="hidden h-4 w-px shrink-0 bg-white/20 sm:block"
//           aria-hidden="true"
//         />
//         <ArrowRight
//           className="ml-auto size-4 shrink-0 text-emerald-400 transition-transform duration-300 group-hover:translate-x-1 sm:size-5"
//           aria-hidden="true"
//         />
//       </Announcement>
//     </header>
//   );
// }
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import {
  Announcement,
  AnnouncementTitle,
} from "@/components/ui/announcement";

export default function Bar({
  align = "center",
  title,
}: {
  align?: "center" | "right";
  title?: ReactNode;
}) {
  return (
    <header
      className={`absolute inset-x-0 top-0 z-20 flex px-4 py-5 sm:px-6 sm:py-8 ${
        title ? "items-center justify-between gap-4" : align === "right" ? "justify-end" : "justify-center"
      }`}
    >
      {title}
      <Announcement
        styled
        shiny
        movingBorder
        className="max-w-[94vw] border-emerald-400/25 bg-[#111814]/95 px-5 py-3 text-sm text-white shadow-[0_18px_50px_rgba(0,0,0,.45)] ring-1 ring-white/[0.06] backdrop-blur-xl transition-transform duration-300 ease-out hover:scale-[1.02] hover:bg-[#17211c] sm:px-8 sm:py-4 sm:text-base"
        movingBorderClassName="bg-[radial-gradient(#34d399_40%,transparent_60%)]"
      >
        <Link href="/About">
        <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-white transition-all duration-300 ease-out hover:-translate-y-0.5 hover:scale-105 hover:bg-white/10 hover:text-emerald-300">
          About us
        </AnnouncementTitle>
        </Link>
        <span className="h-4 w-px shrink-0 bg-white/20" aria-hidden="true" />
        <Link href="/Agent">
          <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-zinc-300 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:scale-105 hover:bg-emerald-400/10 hover:text-emerald-300">
            AI Agent
          </AnnouncementTitle>
        </Link>
        
        <span className="h-4 w-px shrink-0 bg-white/20" aria-hidden="true" />
        <Link href="/dashboard">
          <AnnouncementTitle className="cursor-pointer rounded-full px-3 font-semibold text-zinc-300 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:scale-105 hover:bg-emerald-400/10 hover:text-emerald-300">
            Dashboard
          </AnnouncementTitle>
        </Link>
        <span
          className="hidden h-4 w-px shrink-0 bg-white/20 sm:block"
          aria-hidden="true"
        />
        <ArrowRight
          className="ml-auto size-4 shrink-0 text-emerald-400 transition-transform duration-300 group-hover:translate-x-1 sm:size-5"
          aria-hidden="true"
        />
      </Announcement>
    </header>
  );
}
