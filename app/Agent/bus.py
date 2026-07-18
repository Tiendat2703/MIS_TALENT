import asyncio
import json
import os
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


DEFAULT_LOG_DIR = Path(
    os.getenv(
        "AGENT_LOG_DIR",
        Path(__file__).resolve().parents[2] / "logs" / "agent_runs",
    )
)


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    return str(value)


class AgentEventBus:
    def __init__(self, log_dir: str | Path = DEFAULT_LOG_DIR):
        self.subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self.seq_map: dict[str, int] = defaultdict(int)
        self.snapshots: dict[str, dict[str, Any]] = {}
        self.log_dir = Path(log_dir)

    def next_seq(self, run_id: str | int) -> int:
        run_id = str(run_id)
        self.seq_map[run_id] += 1
        return self.seq_map[run_id]

    async def emit(self, run_id: str | int, payload: dict[str, Any]) -> None:
        run_id = str(run_id)
        if run_id not in self.snapshots:
            self.restore_snapshot(run_id)

        timestamp = datetime.now(timezone.utc).isoformat()
        event = {
            "run_id": run_id,
            "seq": self.next_seq(run_id),
            "ts": timestamp,
            **payload,
        }

        self.snapshots.setdefault(run_id, {
            "run_id": run_id,
            "started_at": timestamp,
            "updated_at": timestamp,
            "status": "running",
            "current_agent": None,
            "current_task": None,
            "events": [],
            "result": None,
        })

        snapshot = self.snapshots[run_id]
        snapshot["updated_at"] = timestamp
        snapshot["events"].append(event)

        if payload.get("agent"):
            snapshot["current_agent"] = payload["agent"]

        if payload.get("task"):
            snapshot["current_task"] = payload["task"]

        if payload.get("type") in {"run_started", "run_resumed"}:
            snapshot["status"] = "running"

        if payload.get("type") == "awaiting_approval":
            snapshot["status"] = "paused"

        if payload.get("type") == "run_review":
            snapshot["status"] = "review"
            data = payload.get("data") or {}
            snapshot["result"] = data.get("decision_result")

        if payload.get("type") == "decision_updated":
            snapshot["status"] = payload.get("status", "done")
            snapshot["result"] = payload.get("data")

        if payload.get("type") == "run_finished":
            snapshot["status"] = "done"
            snapshot["result"] = payload.get("data")

        if payload.get("type") in {"run_error", "decision_update_rejected"}:
            snapshot["status"] = "error"
            snapshot["result"] = payload.get("data")

        if payload.get("type") == "run_cancelled":
            snapshot["status"] = "cancelled"
            snapshot["result"] = payload.get("data")

        # Persist every event so an abrupt stop still leaves the latest snapshot.
        self.persist_snapshot(run_id)

        for queue in self.subscribers[run_id]:
            await queue.put(event)

    def restore_snapshot(self, run_id: str | int) -> None:
        """Continue an existing log when a paused run resumes in a new process."""
        run_id = str(run_id)
        log_path = self.log_dir / f"{run_id}.json"
        if not log_path.exists():
            return

        snapshot = json.loads(log_path.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise ValueError(f"Invalid agent log snapshot: {log_path}")
        events = snapshot.get("events")
        if not isinstance(events, list):
            raise ValueError(f"Invalid agent log snapshot: {log_path}")

        self.snapshots[run_id] = snapshot
        self.seq_map[run_id] = max(
            (event.get("seq", 0) for event in events if isinstance(event, dict)),
            default=0,
        )

    def persist_snapshot(self, run_id: str | int) -> Path:
        run_id = str(run_id)
        snapshot = self.snapshots.get(run_id)
        if snapshot is None:
            raise ValueError(f"No agent log found for run_id={run_id}")

        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.log_dir / f"{run_id}.json"
        temporary_path = log_path.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        temporary_path.replace(log_path)
        return log_path

    def subscribe(self, run_id: str | int) -> asyncio.Queue:
        run_id = str(run_id)
        queue = asyncio.Queue()
        self.subscribers[run_id].append(queue)
        return queue

    def unsubscribe(self, run_id: str | int, queue: asyncio.Queue) -> None:
        run_id = str(run_id)
        if queue in self.subscribers[run_id]:
            self.subscribers[run_id].remove(queue)

    def get_snapshot(self, run_id: str | int) -> dict[str, Any] | None:
        return self.snapshots.get(str(run_id))

event_bus = AgentEventBus()
