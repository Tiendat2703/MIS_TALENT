import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Agent Execution Pipeline | FinWise",
  description: "Monitor Finance, Risk, Decision, and Validator agents throughout a live contract analysis run.",
};

export default function AgentLayout({ children }: { children: ReactNode }) {
  return children;
}
