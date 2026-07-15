import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Agent Execution Pipeline | FinWise",
  description: "Trace the Finance Engine, risk agents, tool calls, and trading execution in one live run.",
};

export default function AgentLayout({ children }: { children: ReactNode }) {
  return children;
}
