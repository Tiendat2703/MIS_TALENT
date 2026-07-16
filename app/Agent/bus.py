import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

class AgentEventBus:
    def __init__(self):
        self.subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self.seq_map: dict[str, int] = defaultdict(int)
        self.snapshots: dict[str, dict[str, Any]] = {}

    def next_seq(self, run_id: str) -> int:
        self.seq_map[run_id] += 1
        return self.seq_map[run_id]

    async def emit(self, run_id: str, payload: dict[str, Any]) -> None:
        event = {
            "run_id": run_id,
            "seq": self.next_seq(run_id),
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }

        self.snapshots.setdefault(run_id, {
            "status": "running",
            "current_agent": None,
            "current_task": None,
            "events": [],
            "result": None,
        })

        self.snapshots[run_id]["events"].append(event)

        if payload.get("agent"):
            self.snapshots[run_id]["current_agent"] = payload["agent"]

        if payload.get("task"):
            self.snapshots[run_id]["current_task"] = payload["task"]

        if payload.get("type") == "run_finished":
            self.snapshots[run_id]["status"] = "done"
            self.snapshots[run_id]["result"] = payload.get("data")

        if payload.get("type") == "run_error":
            self.snapshots[run_id]["status"] = "error"
            self.snapshots[run_id]["result"] = payload.get("data")

        for queue in self.subscribers[run_id]:
            await queue.put(event)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue) -> None:
        if queue in self.subscribers[run_id]:
            self.subscribers[run_id].remove(queue)

    def get_snapshot(self, run_id: str) -> dict[str, Any] | None:
        return self.snapshots.get(run_id)

event_bus = AgentEventBus()