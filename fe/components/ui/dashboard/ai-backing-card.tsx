import { CirclePlay } from "lucide-react";

export function AiBackingCard() {
  return (
    <article className="flex h-full min-h-64 flex-col rounded-2xl border border-white/[0.08] bg-[#0f1210] p-6 sm:p-8">
      <div className="flex -space-x-2">
        {["LI", "AB", "UB"].map((initials, index) => (
          <span
            key={initials}
            className="flex size-9 items-center justify-center rounded-full border-2 border-[#0f1210] text-[10px] font-semibold text-[#07110c]"
            style={{ backgroundColor: ["#34d399", "#6ee7b7", "#a7f3d0"][index] }}
          >
            {initials}
          </span>
        ))}
      </div>
      <h3 className="mt-6 text-2xl font-semibold tracking-[-0.03em] text-zinc-50">Funding match</h3>
      <p className="mt-2 text-sm leading-6 text-zinc-400">
        Compare project health with investor criteria and available financing profiles.
      </p>
      <button className="mt-auto flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] text-sm font-medium text-zinc-100 transition-colors hover:border-emerald-400/25 hover:bg-emerald-400/10 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300">
        Find investors <CirclePlay className="size-4 text-emerald-300" strokeWidth={1.7} aria-hidden="true" />
      </button>
    </article>
  );
}
