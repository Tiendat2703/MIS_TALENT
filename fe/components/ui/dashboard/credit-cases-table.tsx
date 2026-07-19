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
  status: "Pending" | "Scanning" | "Approved";
  currentStep?: string;
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
  "Initializing validation agent...",
  "Scanning company credit record OPC-001...",
  "Verifying collateral document details...",
  "Running risk simulation engine...",
  "Performing compliance validation checks...",
  "Approve confirmation success!",
];

export function CreditCasesTable() {
  const [cases, setCases] = useState<CreditCase[]>(initialCases);
  const [activeAnalysis, setActiveAnalysis] = useState<{
    id: string;
    stepIndex: number;
    logs: string[];
  } | null>(null);

  const handleApprove = (caseId: string) => {
    // Set status to Scanning
    setCases((prev) =>
      prev.map((c) => (c.id === caseId ? { ...c, status: "Scanning", currentStep: agentSteps[0] } : c))
    );
    // Start active logs analysis panel
    setActiveAnalysis({
      id: caseId,
      stepIndex: 0,
      logs: [agentSteps[0]],
    });
  };

  useEffect(() => {
    if (!activeAnalysis) return;

    if (activeAnalysis.stepIndex >= agentSteps.length - 1) {
      // Completed!
      const timer = setTimeout(() => {
        setCases((prev) =>
          prev.map((c) => (c.id === activeAnalysis.id ? { ...c, status: "Approved", currentStep: undefined } : c))
        );
        setActiveAnalysis(null);
      }, 1000);
      return () => clearTimeout(timer);
    }

    // Progress to next step
    const timer = setTimeout(() => {
      const nextIndex = activeAnalysis.stepIndex + 1;
      const nextStep = agentSteps[nextIndex];
      setCases((prev) =>
        prev.map((c) => (c.id === activeAnalysis.id ? { ...c, currentStep: nextStep } : c))
      );
      setActiveAnalysis((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          stepIndex: nextIndex,
          logs: [...prev.logs, nextStep],
        };
      });
    }, 1200);

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
                    ) : (
                      <button
                        onClick={() => handleApprove(item.id)}
                        disabled={activeAnalysis !== null}
                        className={`rounded-md bg-emerald-500 hover:bg-emerald-600 active:bg-emerald-700 px-3 py-1 text-[10px] font-bold text-black shadow-md transition-all hover:shadow-emerald-500/20 active:scale-95 disabled:opacity-50 disabled:pointer-events-none`}
                      >
                        Approve
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {activeAnalysis && (
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
    </div>
  );
}
