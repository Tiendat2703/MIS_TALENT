"use client";

import { useMemo, useState } from "react";
import Bar from "@/components/ui/about/Bar";
import {
  BarChart3,
  BookOpen,
  Check,
  Handshake,
  ShieldCheck,
} from "lucide-react";

type AgentId = "strategy" | "market" | "risk" | "trade";

const agents = {
  strategy: {
    name: "Strategy Reader",
    description: "Analyzing new trading rules.",
    status: "Working",
    accent: "green",
    icon: BookOpen,
    summary:
      "Strategy Reader is parsing the current rule set and translating market conditions into executable constraints.",
    progress: 64,
  },
  market: {
    name: "Market Scanner",
    description: "Analyzing new trading rules.",
    status: "Waiting",
    accent: "amber",
    icon: BarChart3,
    summary:
      "Market Scanner has identified a candidate opportunity and is waiting for the active risk envelope.",
    progress: 58,
  },
  risk: {
    name: "Risk Checker",
    description: "Analyzing new trading rules.",
    status: "Working",
    accent: "green",
    icon: ShieldCheck,
    summary:
      "Risk Checker is currently evaluating the proposed trade against safety parameters. It's ensuring the position is within allowed limits and does not exceed exposure thresholds.",
    progress: 78,
  },
  trade: {
    name: "Trade Executor",
    description: "Preparing trade execution.",
    status: "Done",
    accent: "blue",
    icon: Handshake,
    summary:
      "Trade Executor has prepared the order route and is waiting for the current risk evaluation to complete.",
    progress: 86,
  },
} as const;

const activity = [
  { time: "10:42 AM", agent: "Risk Checker", detail: "Validated the price threshold against safety parameters.", status: "Completed" },
  { time: "10:41 AM", agent: "Market Scanner", detail: "Identified potential trade opportunity.", status: "Pending" },
  { time: "10:40 AM", agent: "Strategy Reader", detail: "Parsed new trading rule set.", status: "Completed" },
  { time: "10:38 AM", agent: "Trade Executor", detail: "Executed trade order for asset.", status: "Completed" },
  { time: "10:36 AM", agent: "Risk Checker", detail: "Verified portfolio exposure remained within limits.", status: "Completed" },
] as const;

const ACCENT_COLORS: Record<string, string> = {
  green: "#34d399",
  amber: "#fbbf24",
  blue: "#38bdf8",
};

function AgentCard({
  id,
  selected,
  onSelect,
}: {
  id: AgentId;
  selected: boolean;
  onSelect: () => void;
}) {
  const agent = agents[id];
  const Icon = agent.icon;
  const color = ACCENT_COLORS[agent.accent];

  return (
    <button
      type="button"
      onClick={onSelect}
      style={selected ? { boxShadow: `0 0 0 1px ${color}55, 0 14px 34px rgba(0,0,0,.35), 0 0 24px ${color}22` } : undefined}
      className={`group relative z-10 flex h-[122px] w-[158px] flex-col rounded-[10px] border p-3 text-left transition duration-200 active:translate-y-px focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 sm:h-[138px] sm:w-[190px] sm:p-4 xl:h-[156px] xl:w-[220px] ${
        selected
          ? "border-emerald-400/40 bg-zinc-950 ring-1 ring-emerald-400/15"
          : "border-white/10 bg-[#080808] shadow-[0_10px_20px_rgba(0,0,0,.35)] hover:border-emerald-400/25"
      }`}
    >
      <span
        className="flex size-9 items-center justify-center rounded-lg border sm:size-11 xl:size-12"
        style={{ color, backgroundColor: `${color}1f`, borderColor: `${color}33`, boxShadow: `0 0 18px ${color}18` }}
      >
        <Icon className="size-5 sm:size-6" strokeWidth={1.8} />
      </span>
      <span className="mt-2 block text-[12px] font-semibold leading-none text-white sm:mt-3 sm:text-sm xl:text-base">
        {agent.name}
      </span>
      <span className="mt-2 block truncate text-[9px] text-zinc-400 sm:text-[11px] xl:text-xs">
        {agent.description}
      </span>
      <span className="mt-auto flex w-full items-center justify-between">
        <span
          className="rounded-full border px-1.5 py-0.5 text-[8px] font-medium sm:px-2 sm:text-[10px]"
          style={{ color, borderColor: `${color}70`, backgroundColor: `${color}18` }}
        >
          {agent.status}
        </span>
        <span className="flex items-center gap-1">
          {[0, 1, 2].map((dot) => (
            <span
              key={dot}
              className="size-1 rounded-full"
              style={{ backgroundColor: dot === 0 ? color : "#4a5563" }}
            />
          ))}
        </span>
      </span>
    </button>
  );
}

function WorkflowBoard({
  selected,
  onSelect,
}: {
  selected: AgentId;
  onSelect: (id: AgentId) => void;
}) {
  return (
    <div className="workflow-circuit relative min-h-[360px] overflow-hidden rounded-[10px] border border-emerald-400/20 bg-black shadow-2xl shadow-black/60 ring-1 ring-white/10 lg:min-h-[430px] xl:min-h-[480px]">
      {/* Circuit lines are calibrated for the 2-col desktop layout only — hide below lg to avoid misalignment */}
      <svg
        className="pointer-events-none absolute inset-0 hidden h-full w-full lg:block"
        viewBox="0 0 547 303"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <filter id="green-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <filter id="blue-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <marker id="green-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="#34d399" strokeWidth="1.6" />
          </marker>
          <marker id="blue-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="#5e9fe8" strokeWidth="1.6" />
          </marker>
        </defs>
        <path d="M200 87 H344" fill="none" stroke="#34d399" strokeWidth="2" filter="url(#green-glow)" markerEnd="url(#green-arrow)" />
        <path d="M200 215 H240 Q260 215 260 190 V122 Q260 103 280 103 H344" fill="none" stroke="#34d399" strokeWidth="2" filter="url(#green-glow)" markerEnd="url(#green-arrow)" />
        <path d="M200 225 H344" fill="none" stroke="#5e9fe8" strokeWidth="2.5" filter="url(#blue-glow)" markerEnd="url(#blue-arrow)" />
        <g fill="#34d399">
          <circle cx="255" cy="87" r="3" /><circle cx="260" cy="158" r="3" /><circle cx="292" cy="103" r="2.5" />
        </g>
        <g fill="#5e9fe8"><circle cx="260" cy="225" r="3" /><circle cx="330" cy="225" r="2.5" /></g>
      </svg>

      <div className="relative grid min-h-[360px] grid-cols-1 place-items-center gap-4 px-5 py-8 sm:grid-cols-2 sm:content-between sm:justify-items-center sm:gap-x-24 sm:gap-y-8 sm:px-[9%] lg:min-h-[430px] lg:py-10 xl:min-h-[480px] xl:py-12">
        <AgentCard id="strategy" selected={selected === "strategy"} onSelect={() => onSelect("strategy")} />
        <AgentCard id="market" selected={selected === "market"} onSelect={() => onSelect("market")} />
        <AgentCard id="risk" selected={selected === "risk"} onSelect={() => onSelect("risk")} />
        <AgentCard id="trade" selected={selected === "trade"} onSelect={() => onSelect("trade")} />
      </div>

      {/* <div className="absolute bottom-3 left-1/2 z-20 hidden -translate-x-1/2 items-center gap-2 rounded-full bg-[#0c1119]/90 px-5 py-2.5 text-xs font-semibold text-white shadow-xl ring-1 ring-white/10 sm:flex xl:text-sm">
        <ChevronDown className="size-4 xl:size-5" strokeWidth={1.8} /> Scroll for Details
      </div> */}
    </div>
  );
}

export function AgentWorkspace() {
  const [selected, setSelected] = useState<AgentId>("risk");
  const selectedAgent = useMemo(() => agents[selected], [selected]);
  const selectedColor = ACCENT_COLORS[selectedAgent.accent];

  return (
    <div className="relative min-h-[100dvh] overflow-x-hidden bg-black text-zinc-50">
      <style jsx global>{`
        .workflow-circuit {
          background-image:
            linear-gradient(rgba(0, 0, 0, 0.9), rgba(0, 0, 0, 0.9)),
            repeating-linear-gradient(90deg, transparent 0 34px, rgba(52, 211, 153, 0.055) 34px 35px),
            repeating-linear-gradient(0deg, transparent 0 31px, rgba(52, 211, 153, 0.045) 31px 32px);
        }
      `}</style>

      <Bar />

      <div className="w-full pt-24 sm:pt-28">
        <div className="min-h-[100dvh] w-full bg-black/80">
          {/* <header className="flex h-14 items-center justify-between border-b border-white/10 bg-[#0c1119]/95 px-4 sm:px-6 lg:px-8 xl:px-10">
            <div className="flex min-w-0 items-center gap-5 sm:gap-8">
              <div className="flex shrink-0 items-center gap-1.5">
                <LogoMark />
                <span className="leading-none">
                  <span className="block text-[12px] font-bold text-white">FinWise</span>
                  <span className="block text-[7px] text-[#9aa5b1]">Agent Network</span>
                </span>
              </div>
              <nav className="hidden h-14 items-center gap-7 text-xs text-[#9aa5b1] sm:flex" aria-label="Main navigation">
                <button className="h-full transition hover:text-white">Rule Engine</button>
                <button className="h-full border-b-2 border-[#61d79a] text-white">Automation</button>
                <button className="h-full transition hover:text-white">Trading</button>
              </nav>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setRunning((value) => !value)}
                className="flex min-h-9 items-center gap-2 rounded-md bg-white/10 px-3 text-xs text-white transition hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#63d89b]"
              >
                {running ? <Pause className="size-3.5" fill="currentColor" /> : <Play className="size-3.5" fill="currentColor" />}
                {running ? "Pause stream" : "Resume stream"}
              </button>
              <button className="flex size-9 items-center justify-center rounded-full bg-white/10 text-[#d5dbe3]" aria-label="User account">
                <UserRound className="size-[18px]" fill="currentColor" strokeWidth={1.5} />
              </button>
            </div>
          </header> */}

          <main className="px-4 py-5 sm:px-6 lg:px-8 xl:px-10">
            {/* <div className="mb-5">
              <h1 className="text-xl font-semibold leading-6 text-white sm:text-2xl xl:text-3xl">
                AGENT WORKFLOW MONITOR
              </h1>
              <p className="mt-1 text-xs text-[#9aa5b1] sm:text-sm">
                Real-time visibility into automated tasks, designed for clarity.
              </p>
            </div> */}

            <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px] xl:grid-cols-[minmax(0,1fr)_340px]">
              <WorkflowBoard selected={selected} onSelect={setSelected} />

              <aside className="flex min-h-[360px] flex-col overflow-hidden rounded-[10px] border border-emerald-400/20 bg-black shadow-2xl shadow-black/60 ring-1 ring-white/10 lg:min-h-[430px] xl:min-h-[480px]">
                <div className="border-b border-white/10 px-5 py-4">
                  <h2 className="text-base font-semibold leading-none text-white xl:text-lg">Task Summary</h2>
                  <p className="mt-1.5 text-xs text-zinc-400">What&apos;s happening right now?</p>
                </div>
                <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto]">
                  <div className="overflow-y-auto px-5 py-5 text-center xl:px-6 xl:py-6">
                    <span
                      className="mx-auto flex size-12 items-center justify-center rounded-full text-[#0d1a14] xl:size-14"
                      style={{ backgroundColor: selectedColor, boxShadow: `0 0 24px ${selectedColor}44` }}
                    >
                      <Check className="size-7" strokeWidth={2.4} />
                    </span>
                    <h3 className="mt-5 text-sm font-semibold text-white xl:text-base">{selectedAgent.name}</h3>
                    <p className="mt-3 text-left text-xs leading-5 text-zinc-300 xl:text-sm xl:leading-6">
                      {selectedAgent.summary}
                    </p>
                    <div className="mt-5 text-left">
                      <p className="text-xs text-zinc-300 xl:text-sm">Progress: {selectedAgent.progress}%</p>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{ width: `${selectedAgent.progress}%`, backgroundColor: selectedColor, boxShadow: `0 0 8px ${selectedColor}66` }}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="shrink-0 space-y-2 px-5 pb-5 pt-3 xl:px-6 xl:pb-6">
                    <button className="min-h-11 w-full rounded-md bg-[#f4f7fa] text-xs font-medium text-[#111827] transition hover:bg-white xl:text-sm">
                      View Details
                    </button>
                    <button className="min-h-11 w-full rounded-md border border-emerald-400/20 bg-zinc-950/90 text-xs text-white transition hover:border-emerald-400/35 hover:bg-zinc-900 xl:text-sm">
                      View All Agents
                    </button>
                  </div>
                </div>
              </aside>
            </section>

            <section className="mt-4 rounded-[10px] border border-emerald-400/20 bg-black p-4 shadow-2xl shadow-black/60 ring-1 ring-white/10 sm:p-5">
              <h2 className="mb-4 text-lg font-semibold text-white sm:text-xl">AGENT ACTIVITY DETAILS</h2>
              <div className="space-y-3">
                {activity.map((item, index) => {
                  const pending = item.status === "Pending";
                  return (
                    <article
                      key={`${item.time}-${item.agent}`}
                      className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 text-xs sm:grid-cols-[76px_minmax(0,1fr)]"
                    >
                      <div className="relative pt-3 text-zinc-400">
                        <span>{item.time}</span>
                        {index < activity.length - 1 && (
                          <span className="absolute bottom-[-12px] right-1 top-7 w-px bg-white/15" />
                        )}
                      </div>
                      <div className="rounded-[9px] border border-white/10 bg-zinc-950 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,.03)]">
                        <div className="flex items-center justify-between gap-3">
                          <p>
                            <span className="text-zinc-400">{item.time} | </span>
                            <strong className="text-sm text-white">{item.agent}</strong>
                          </p>
                          <span
                            className={`rounded-full border px-2 py-0.5 text-[10px] font-medium sm:text-xs ${
                              pending
                                ? "border-[#e3bd62]/60 bg-[#e3bd62]/12 text-[#f0cf85]"
                                : "border-[#61d79a]/60 bg-[#61d79a]/12 text-[#7fe4ac]"
                            }`}
                          >
                            {item.status}
                          </span>
                        </div>
                        <p className="mt-1.5 text-xs text-zinc-300 sm:text-sm">{item.detail}</p>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  );
}
