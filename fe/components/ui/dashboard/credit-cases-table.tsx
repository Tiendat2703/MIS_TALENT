"use client";

import { useState, useEffect } from "react";

interface CreditCase {
  id: string;
  companyId: string;
  requestType: string;
  amount: number;
  tenor: string;
  collateral: string;
  score: number;
  note: string;
  status: "Pending" | "Scanning" | "NeedsReview" | "Approved";
}

const initialCases: CreditCase[] = [
  {
    id: "CR-001",
    companyId: "OPC-001",
    requestType: "Working capital line",
    amount: 950000000,
    tenor: "6 months",
    collateral: "Open invoices + founder guarantee",
    score: 0.71,
    note: "Need receivable aging evidence",
    status: "Pending",
  },
  {
    id: "CR-002",
    companyId: "OPC-001",
    requestType: "Performance bond",
    amount: 420000000,
    tenor: "Until contract acceptance",
    collateral: "Contract CON-004",
    score: 0.63,
    note: "Acceptable if contract signed & cashflow buffer confirmed",
    status: "Pending",
  },
  {
    id: "CR-003",
    companyId: "OPC-001",
    requestType: "Trade finance/LC support",
    amount: 650000000,
    tenor: "4 months",
    collateral: "CON-005 documentation",
    score: 0.56,
    note: "Missing supplier confirmation",
    status: "Pending",
  },
  {
    id: "CR-004",
    companyId: "OPC-001",
    requestType: "Micro working capital",
    amount: 220000000,
    tenor: "3 months",
    collateral: "Local cooperative receivables",
    score: 0.78,
    note: "Good fit for cooperative network pilot",
    status: "Pending",
  },
];

const agentSteps = [
  "Initializing credit validation agent...",
  "Scanning company records OPC-001 on national risk registry...",
  "Verifying collateral document details and ownership basis...",
  "Running Monte Carlo default simulations under market stress...",
  "Performing cross-check with legal and environmental compliance...",
  "AI Analysis complete. Report generated. Human review required.",
];

const caseRiskReports: Record<string, {
  score: number;
  grade: "A" | "B" | "C" | "D";
  recommendation: string;
  risks: string[];
  mitigations: string[];
}> = {
  "CR-001": {
    score: 0.71,
    grade: "B",
    recommendation: "Conditional approval recommended. Require verified invoice aging records before payout.",
    risks: [
      "Collateral liquidity risk: 45% of open invoices are within the 60-90 days payment bracket.",
      "Founder personal guarantee lacks secondary liquid asset validation audits.",
    ],
    mitigations: [
      "Include a covenants clause limiting secondary lines of credit from external entities.",
      "Require bi-weekly progress reports on receivables collections directly from the billing team.",
    ],
  },
  "CR-002": {
    score: 0.63,
    grade: "C",
    recommendation: "High caution. Perform physical progress audits of Contract CON-004 prior to activation.",
    risks: [
      "Performance bond release relies heavily on final delivery acceptance from primary construction clients.",
      "Company reported low cash reserves ratio (1.1x current liabilities) in Q2 accounting sheets.",
    ],
    mitigations: [
      "Verify signing of the head agreement contract with primary municipal stakeholders.",
      "Request collateral top-up with cash reserve margin ($50,000 equivalent) locked in escrow.",
    ],
  },
  "CR-003": {
    score: 0.56,
    grade: "D",
    recommendation: "Hold approval. Reject current state due to missing critical supplier confirmations.",
    risks: [
      "Lack of verified overseas supplier shipping license and import security documents.",
      "Trade route port labor disputes could delay critical raw materials landing by 14 days.",
    ],
    mitigations: [
      "Freeze LC release until verified notarized supplier signatures are uploaded via portal.",
      "Increase transit delay contingency budget buffers on commercial transport insurance.",
    ],
  },
  "CR-004": {
    score: 0.78,
    grade: "A",
    recommendation: "Standard approval recommended. Highly diversified pool of local cooperative members.",
    risks: [
      "Minor operational bottlenecks in micro-distribution channels for regional pilot rollout.",
    ],
    mitigations: [
      "Align with cooperative management for standard quarterly financial health reports.",
    ],
  },
};

export function CreditCasesTable() {
  const [cases, setCases] = useState<CreditCase[]>(initialCases);
  const [activeAnalysis, setActiveAnalysis] = useState<{
    id: string;
    stepIndex: number;
    logs: string[];
    showReport: boolean;
  } | null>(null);

  const handleStartAnalysis = (caseId: string) => {
    setCases((prev) =>
      prev.map((c) => (c.id === caseId ? { ...c, status: "Scanning" } : c))
    );
    setActiveAnalysis({
      id: caseId,
      stepIndex: 0,
      logs: [agentSteps[0]],
      showReport: false,
    });
  };

  const handleFinalApprove = (caseId: string) => {
    setCases((prev) =>
      prev.map((c) => (c.id === caseId ? { ...c, status: "Approved" } : c))
    );
    setActiveAnalysis(null);
  };

  const handleReject = (caseId: string) => {
    setCases((prev) =>
      prev.map((c) => (c.id === caseId ? { ...c, status: "Pending" } : c))
    );
    setActiveAnalysis(null);
  };

  useEffect(() => {
    if (!activeAnalysis || activeAnalysis.showReport) return;

    if (activeAnalysis.stepIndex >= agentSteps.length - 1) {
      const timer = setTimeout(() => {
        setCases((prev) =>
          prev.map((c) => (c.id === activeAnalysis.id ? { ...c, status: "NeedsReview" } : c))
        );
        setActiveAnalysis((prev) => prev ? { ...prev, showReport: true } : null);
      }, 1000);
      return () => clearTimeout(timer);
    }

    const timer = setTimeout(() => {
      const nextIndex = activeAnalysis.stepIndex + 1;
      const nextStep = agentSteps[nextIndex];
      setActiveAnalysis((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          stepIndex: nextIndex,
          logs: [...prev.logs, nextStep],
        };
      });
    }, 1000);

    return () => clearTimeout(timer);
  }, [activeAnalysis]);

  return (
    <div className="space-y-4">
      <div className="max-w-full fin-scrollbar overflow-x-auto rounded-xl border border-[var(--fin-soft-border)] bg-[var(--fin-surface)]">
        <table className="w-full min-w-[1000px] text-left text-xs">
          <thead className="bg-white/[0.02] text-[var(--fin-muted)] border-b border-[var(--fin-soft-border)]">
            <tr>
              <th className="px-4 py-3 font-medium">Case ID</th>
              <th className="px-4 py-3 font-medium">Company</th>
              <th className="px-4 py-3 font-medium">Request Type</th>
              <th className="px-4 py-3 text-right font-medium">Amount ($)</th>
              <th className="px-4 py-3 font-medium">Tenor</th>
              <th className="px-4 py-3 font-medium">Collateral / Basis</th>
              <th className="px-4 py-3 text-center font-medium">Score</th>
              <th className="px-4 py-3 font-medium">Precheck Note</th>
              <th className="px-4 py-3 text-center font-medium">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--fin-soft-border)]/50">
            {cases.map((item) => {
              const isScanning = item.status === "Scanning";
              const isApproved = item.status === "Approved";
              const isNeedsReview = item.status === "NeedsReview";
              return (
                <tr key={item.id} className="transition-colors hover:bg-white/[0.015]">
                  <td className="px-4 py-3.5 font-bold font-mono text-[var(--fin-text)]">{item.id}</td>
                  <td className="px-4 py-3.5 text-[var(--fin-muted)]">{item.companyId}</td>
                  <td className="px-4 py-3.5 font-medium text-[var(--fin-text)]">{item.requestType}</td>
                  <td className="px-4 py-3.5 text-right font-mono font-semibold text-emerald-300">
                    {item.amount.toLocaleString()}
                  </td>
                  <td className="px-4 py-3.5 text-[var(--fin-muted)]">{item.tenor}</td>
                  <td className="px-4 py-3.5 text-xs text-[var(--fin-text)]">{item.collateral}</td>
                  <td className="px-4 py-3.5 text-center font-mono">
                    <span className={`px-2 py-0.5 rounded font-bold text-[10px] ${
                      item.score >= 0.7
                        ? "bg-emerald-400/10 text-emerald-300"
                        : item.score >= 0.6
                        ? "bg-amber-400/10 text-amber-300"
                        : "bg-red-400/10 text-red-300"
                    }`}>
                      {item.score.toFixed(2)}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-xs text-[var(--fin-muted)] max-w-xs truncate" title={item.note}>
                    {item.note}
                  </td>
                  <td className="px-4 py-3.5 text-center">
                    {isApproved ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase text-emerald-400 bg-emerald-400/10 border border-emerald-400/25 px-2.5 py-1 rounded-md">
                        ✓ Approved
                      </span>
                    ) : isScanning ? (
                      <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold text-amber-400 bg-amber-400/5 px-2.5 py-1 rounded-md">
                        <span className="size-2 rounded-full bg-amber-400 animate-ping" />
                        Analyzing...
                      </span>
                    ) : isNeedsReview ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase text-amber-400 bg-amber-400/10 border border-amber-400/25 px-2.5 py-1 rounded-md">
                        ⚠ Needs Review
                      </span>
                    ) : (
                      <button
                        onClick={() => handleStartAnalysis(item.id)}
                        disabled={activeAnalysis !== null}
                        className="rounded-md bg-emerald-500 hover:bg-emerald-600 active:bg-emerald-700 px-3 py-1 text-[10px] font-bold text-black shadow-md transition-all hover:shadow-emerald-500/20 active:scale-95 disabled:opacity-50 disabled:pointer-events-none"
                      >
                        Analyze
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {activeAnalysis && !activeAnalysis.showReport && (
        <section className="rounded-xl border border-amber-400/20 bg-amber-400/[0.02] p-4 font-mono text-[11px] leading-relaxed transition-all">
          <header className="flex items-center justify-between border-b border-amber-400/10 pb-2 mb-3">
            <span className="flex items-center gap-2 font-bold text-amber-300">
              <span className="size-1.5 rounded-full bg-amber-400 animate-ping" />
              AI Agent Risk Assessment Active (Case: {activeAnalysis.id})
            </span>
            <span className="text-[10px] text-zinc-500">Turbopack Agent Worker #1</span>
          </header>
          <div className="space-y-1 text-zinc-400">
            {activeAnalysis.logs.map((log, idx) => {
              const isLast = idx === activeAnalysis.logs.length - 1;
              return (
                <div key={idx} className={`${isLast ? "text-amber-300 font-bold" : ""}`}>
                  &gt; {log}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {activeAnalysis && activeAnalysis.showReport && (
        (() => {
          const report = caseRiskReports[activeAnalysis.id];
          const gradeColor = {
            A: "bg-emerald-400/10 text-emerald-400 border-emerald-400/20",
            B: "bg-blue-400/10 text-blue-400 border-blue-400/20",
            C: "bg-amber-400/10 text-amber-300 border-amber-400/20",
            D: "bg-red-400/10 text-red-400 border-red-400/20",
          }[report.grade];

          return (
            <section className="rounded-xl border border-[var(--fin-border)] bg-[var(--fin-surface)] p-5 transition-all space-y-4">
              <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[var(--fin-soft-border)] pb-3">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-[var(--fin-text)]">
                    🤖 AI Risk Assessment Report: <span className="font-mono text-emerald-400">{activeAnalysis.id}</span>
                  </span>
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold ${gradeColor}`}>
                    Grade {report.grade}
                  </span>
                </div>
                <div className="text-[11px] text-[var(--fin-muted)]">
                  Eligibility Score: <span className="font-mono font-bold text-[var(--fin-text)]">{(report.score).toFixed(2)}</span>
                </div>
              </header>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs">
                <div>
                  <h4 className="font-bold text-[var(--fin-text)] uppercase tracking-wider text-[10px]">Identified Risks</h4>
                  <ul className="mt-2 space-y-2 text-[var(--fin-muted)] list-disc pl-4 leading-relaxed">
                    {report.risks.map((r, idx) => <li key={idx}>{r}</li>)}
                  </ul>
                </div>
                <div>
                  <h4 className="font-bold text-[var(--fin-text)] uppercase tracking-wider text-[10px]">AI Mitigations</h4>
                  <ul className="mt-2 space-y-2 text-[var(--fin-muted)] list-disc pl-4 leading-relaxed">
                    {report.mitigations.map((m, idx) => <li key={idx}>{m}</li>)}
                  </ul>
                </div>
              </div>

              <div className="bg-[var(--fin-bg)]/60 rounded-lg p-3 border border-[var(--fin-soft-border)] text-xs">
                <span className="font-semibold text-emerald-400">AI Recommendation:</span> <span className="text-[var(--fin-text)] leading-relaxed">{report.recommendation}</span>
              </div>

              <footer className="flex items-center justify-end gap-3 pt-2 border-t border-[var(--fin-soft-border)]">
                <button
                  onClick={() => handleReject(activeAnalysis.id)}
                  className="rounded-md border border-[var(--fin-soft-border)] hover:bg-white/5 px-4 py-1.5 text-xs font-semibold text-[var(--fin-text)] transition-all active:scale-95"
                >
                  Reject & Back
                </button>
                <button
                  onClick={() => handleFinalApprove(activeAnalysis.id)}
                  className="rounded-md bg-emerald-500 hover:bg-emerald-600 active:bg-emerald-700 px-4 py-1.5 text-xs font-bold text-black shadow-md shadow-emerald-500/10 transition-all active:scale-95"
                >
                  Confirm Approve Case
                </button>
              </footer>
            </section>
          );
        })()
      )}
    </div>
  );
}
