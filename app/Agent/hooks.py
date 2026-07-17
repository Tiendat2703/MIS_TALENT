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
    "tool_retrieve_fomularRule": "Đọc rule package",
    "fetch_futures_ohlcv_field_series": "Lấy dữ liệu OHLCV",
    "calculate_exponential_moving_average": "Tính EMA",
    "place_market_order": "Đặt market order",
    "place_limit_order": "Đặt limit order",
    "save_log": "Lưu log giao dịch",
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
            "task": f"{agent.name} bắt đầu chạy",
            "status": "running",
        })

    async def on_end(self, context: RunContextWrapper, agent: Agent, output: Any) -> None:
        await self._emit(context, {
            "type": "agent_finished",
            "agent": agent.name,
            "task": f"{agent.name} hoàn tất",
            "status": "done",
            "summary": str(output)[:500],
        })

    async def on_handoff(self, context: RunContextWrapper, agent: Agent, source: Agent) -> None:
        await self._emit(context, {
            "type": "agent_handoff",
            "agent": source.name,
            "target_agent": agent.name,
            "task": f"Chuyển từ {source.name} sang {agent.name}",
            "status": "done",
        })

    async def on_tool_start(self, context: RunContextWrapper, agent: Agent, tool) -> None:
        tool_name = tool.name
        await self._emit(context, {
            "type": "tool_started",
            "agent": agent.name,
            "tool_name": tool_name,
            "task": TOOL_LABELS.get(tool_name, f"Chạy tool {tool_name}"),
            "status": "running",
        })

    # async def on_tool_end(self, context: RunContextWrapper, agent: Agent, tool, result: str) -> None:
    #     tool_name = tool.name
    #     await self._emit(context, {
    #         "type": "tool_finished",
    #         "agent": agent.name,
    #         "tool_name": tool_name,
    #         "task": TOOL_LABELS.get(tool_name, f"Hoàn tất tool {tool_name}"),
    #         "status": "done",
    #         "summary": str(result)[:500],
    #     })
    async def on_tool_end(self, context: RunContextWrapper, agent: Agent, tool, result: str) -> None:
        tool_name = tool.name
        
        # ✅ Print đầu ra tool trực tiếp ra terminal
        print(f"\n{'='*60}")
        print(f"[TOOL OUTPUT] {tool_name}")
        print(f"[AGENT] {agent.name}")
        print(f"[RESULT]\n{str(result)[:2000]}")  # tăng limit để thấy đủ
        print(f"{'='*60}\n")

        await self._emit(context, {
            "type": "tool_finished",
            "agent": agent.name,
            "tool_name": tool_name,
            "task": TOOL_LABELS.get(tool_name, f"Hoàn tất tool {tool_name}"),
            "status": "done",
            "summary": str(result)[:500],
        })
