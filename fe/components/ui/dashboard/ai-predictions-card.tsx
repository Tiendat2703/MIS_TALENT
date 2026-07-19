import { Bot } from "lucide-react";

export function AiPredictionsCard() {
  return (
    <article className="relative flex h-full min-h-64 overflow-hidden rounded-2xl border border-emerald-400/20 bg-[#10241a] p-6 sm:p-8">
      <div className="relative z-10 flex max-w-xl flex-1 flex-col items-start">
        <span className="flex size-10 items-center justify-center rounded-xl border border-emerald-300/20 bg-emerald-300/10 text-emerald-300">
          <Bot className="size-5" strokeWidth={1.7} aria-hidden="true" />
        </span>
        <h3 className="mt-6 text-2xl font-semibold tracking-[-0.03em] text-zinc-50">Risk forecast</h3>
        <p className="mt-2 max-w-md text-sm leading-6 text-emerald-50/65">
          Review projected cost and schedule exposure before the next reporting cycle.
        </p>
        <button className="mt-auto min-h-11 rounded-xl bg-emerald-300 px-5 text-sm font-semibold text-[#07110c] transition-colors hover:bg-emerald-200 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200 focus-visible:ring-offset-2 focus-visible:ring-offset-[#10241a]">
          Review risks
        </button>
      </div>
      <Bot className="absolute -bottom-12 -right-8 size-56 text-emerald-200/[0.06]" strokeWidth={1} aria-hidden="true" />
    </article>
  );
}
