import { PageTransition } from "@/components/ui/page-transition";
import { AgentWorkspace } from "./agent-workspace";

export default function AgentPage() {
  return (
    <PageTransition>
      <AgentWorkspace />
    </PageTransition>
  );
}
