from dataclasses import dataclass
from typing import Any

from agents import Agent, RunContextWrapper
from agents.lifecycle import AgentHooks

from app.Agent.bus import event_bus


@dataclass
class AppContext:
    document_id: str
    original_input: str
    run_id: str
    brain_request_payload: dict[str, Any] | None = None
    continuation_approval_id: str | None = None


TOOL_LABELS = {
    "tool_retrieve_document": "Read strategy document",
    "tool_retrieve_fomularRule": "Read rule package",
    "fetch_futures_ohlcv_field_series": "Fetch OHLCV data",
    "calculate_exponential_moving_average": "Calculate EMA",
    "place_market_order": "Place market order",
    "place_limit_order": "Place limit order",
    "save_log": "Save transaction log",
    "build_risk_pack": "Analyze risks and build Risk Pack",
    "save_risk_pack": "Save Risk Pack to workflow context",
}


class CustomAgentHooks(AgentHooks):
    def __init__(self, display_name: str | None = None):
        self.display_name = display_name

    async def _emit(self, context: RunContextWrapper, payload: dict[str, Any]) -> None:
        run_id = context.context.run_id
        print(
            f"[RUN {run_id}] "
            f"type={payload.get('type')} | "
            f"agent={payload.get('agent')} | "
            f"task={payload.get('task')} | "
            f"status={payload.get('status')}"
        )
        await event_bus.emit(run_id, payload)

    async def on_start(self, context: RunContextWrapper, agent: Agent) -> None:
        await self._emit(context, {
            "type": "agent_started",
            "agent": agent.name,
            "task": f"{agent.name} started",
            "status": "running",
        })

    async def on_end(self, context: RunContextWrapper, agent: Agent, output: Any) -> None:
        await self._emit(context, {
            "type": "agent_finished",
            "agent": agent.name,
            "task": f"{agent.name} completed",
            "status": "done",
            "summary": str(output)[:500],
        })

    async def on_handoff(self, context: RunContextWrapper, agent: Agent, source: Agent) -> None:
        await self._emit(context, {
            "type": "agent_handoff",
            "agent": source.name,
            "target_agent": agent.name,
            "task": f"Handoff from {source.name} to {agent.name}",
            "status": "done",
        })

    async def on_tool_start(self, context: RunContextWrapper, agent: Agent, tool) -> None:
        tool_name = tool.name
        await self._emit(context, {
            "type": "tool_started",
            "agent": agent.name,
            "tool_name": tool_name,
            "task": TOOL_LABELS.get(tool_name, f"Run tool {tool_name}"),
            "status": "running",
        })

    async def on_tool_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool,
        result: object,
    ) -> None:
        tool_name = tool.name
        
        # ✅ Print đầu ra tool trực tiếp ra terminal
        print(f"\n{'='*60}")
        print(f"[TOOL OUTPUT] {tool_name}")
        print(f"[AGENT] {agent.name}")
        print(f"[RESULT]\n{result}")
        print(f"{'='*60}\n")

        await self._emit(context, {
            "type": "tool_finished",
            "agent": agent.name,
            "tool_name": tool_name,
            "task": TOOL_LABELS.get(tool_name, f"Tool {tool_name} completed"),
            "status": "done",
            "summary": str(result)[:500],
        })
