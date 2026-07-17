import asyncio
import fcntl
import hashlib
import json
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.Agent.hooks import AppContext


PENDING_STATE_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "pending_states"
)

_RUN_LOCKS: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _state_path(run_id: str) -> Path:
    return PENDING_STATE_DIR / f"{run_id}.json"


@contextmanager
def _process_lock(run_id: str):
    """Serialize state transitions across separate CLI processes."""
    PENDING_STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = PENDING_STATE_DIR / f".{run_id}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_state(run_id: str, payload: dict[str, Any]) -> None:
    PENDING_STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = _state_path(run_id)
    temporary_path = path.with_suffix(".json.tmp")
    payload["revision"] = int(payload.get("revision", 0)) + 1
    payload["updated_at"] = _timestamp()
    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _read_state(run_id: str) -> dict[str, Any]:
    path = _state_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"No approval state found for run_id={run_id}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 2:
        raise ValueError(
            f"Run {run_id} uses a legacy approval format; start a new run"
        )
    return payload


def _approval_fingerprint(
    contract_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    source = json.dumps(
        {
            "contract_id": contract_id,
            "tool": tool_name,
            "arguments": arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


async def initialize_approval_state(
    run_id: str,
    context: AppContext,
    user_input: str,
    metadata: dict[str, object] | None = None,
) -> None:
    """Initialize application-level approval state before tools can run."""
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            path = _state_path(run_id)
            if path.exists():
                payload = _read_state(run_id)
                payload["context"] = asdict(context)
                payload["user_input"] = user_input
                payload.setdefault("metadata", {}).update(metadata or {})
                _write_state(run_id, payload)
                return

            now = _timestamp()
            _write_state(run_id, {
                "version": 2,
                "revision": 0,
                "run_id": run_id,
                "created_at": now,
                "updated_at": now,
                "workflow_status": "running",
                "context": asdict(context),
                "user_input": user_input,
                "metadata": dict(metadata or {}),
                "approval_requests": [],
                "decision_result": None,
                "conversation_items": None,
            })


async def register_approval_request(
    run_id: str,
    contract_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Create or return the request for this exact tool invocation."""
    fingerprint = _approval_fingerprint(contract_id, tool_name, arguments)
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            payload = _read_state(run_id)
            for request in payload["approval_requests"]:
                if request["fingerprint"] == fingerprint:
                    return dict(request)

            request = {
                "approval_id": str(uuid.uuid4()),
                "fingerprint": fingerprint,
                "contract_id": contract_id,
                "tool": tool_name,
                "arguments": arguments,
                "status": "pending",
                "requested_at": _timestamp(),
                "decided_at": None,
                "execution_started_at": None,
                "executed_at": None,
                "decision_applied_at": None,
                "result": None,
                "error": None,
            }
            payload["approval_requests"].append(request)
            payload["workflow_status"] = "review"
            _write_state(run_id, payload)
            return dict(request)


async def get_approval_state(run_id: str) -> dict[str, Any]:
    return _read_state(run_id)


async def list_approval_requests(run_id: str) -> list[dict[str, Any]]:
    return list(_read_state(run_id)["approval_requests"])


async def set_approval_decision(
    run_id: str,
    approval_id: str,
    approved: bool,
) -> dict[str, Any]:
    """Move one pending request to approved or rejected."""
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            payload = _read_state(run_id)
            for request in payload["approval_requests"]:
                if request["approval_id"] != approval_id:
                    continue
                if approved and request["status"] in {
                    "approved",
                    "executing",
                    "executed",
                }:
                    return dict(request)
                if not approved and request["status"] == "rejected":
                    return dict(request)
                if request["status"] != "pending":
                    raise ValueError(
                        f"Approval {approval_id} was already decided: {request['status']}"
                    )
                request["status"] = "approved" if approved else "rejected"
                request["decided_at"] = _timestamp()
                _write_state(run_id, payload)
                return dict(request)
    raise KeyError(f"Approval request not found: {approval_id}")


async def claim_approval_execution(
    run_id: str,
    approval_id: str,
) -> dict[str, Any]:
    """Atomically claim an approved request before making the external call."""
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            payload = _read_state(run_id)
            for request in payload["approval_requests"]:
                if request["approval_id"] != approval_id:
                    continue
                claimed = False
                if request["status"] == "approved":
                    request["status"] = "executing"
                    request["execution_started_at"] = _timestamp()
                    _write_state(run_id, payload)
                    claimed = True
                result = dict(request)
                result["claimed"] = claimed
                return result
    raise KeyError(f"Approval request not found: {approval_id}")


async def complete_approval_execution(
    run_id: str,
    approval_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            payload = _read_state(run_id)
            for request in payload["approval_requests"]:
                if request["approval_id"] != approval_id:
                    continue
                if request["status"] != "executing":
                    raise ValueError(
                        f"Approval {approval_id} cannot complete from {request['status']}"
                    )
                request["status"] = "executed"
                request["executed_at"] = _timestamp()
                request["result"] = result
                request["error"] = None
                _write_state(run_id, payload)
                return dict(request)
    raise KeyError(f"Approval request not found: {approval_id}")


async def fail_approval_execution(
    run_id: str,
    approval_id: str,
    error: str,
) -> None:
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            payload = _read_state(run_id)
            for request in payload["approval_requests"]:
                if request["approval_id"] == approval_id:
                    request["status"] = "failed"
                    request["error"] = error
                    _write_state(run_id, payload)
                    return
    raise KeyError(f"Approval request not found: {approval_id}")


async def commit_initial_result(
    run_id: str,
    decision_result: dict[str, Any],
    conversation_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Atomically store the complete first-turn result and continuation history."""
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            payload = _read_state(run_id)
            payload["decision_result"] = decision_result
            payload["conversation_items"] = conversation_items
            unresolved = any(
                request["status"] in {"pending", "approved", "executing", "failed"}
                for request in payload["approval_requests"]
            )
            payload["workflow_status"] = "review" if unresolved else "done"
            _write_state(run_id, payload)
            return payload


async def load_conversation_items(run_id: str) -> list[dict[str, Any]]:
    items = _read_state(run_id).get("conversation_items")
    if not isinstance(items, list):
        raise ValueError(f"Run {run_id} has no saved conversation history")
    return items


async def load_context(run_id: str) -> tuple[dict[str, Any], AppContext]:
    payload = _read_state(run_id)
    return payload, AppContext(**payload["context"])


async def commit_continuation_result(
    run_id: str,
    *,
    expected_revision: int,
    approval_id: str,
    decision_result: dict[str, Any],
    conversation_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Commit a guarded continuation result if no concurrent change occurred."""
    async with _RUN_LOCKS[run_id]:
        with _process_lock(run_id):
            payload = _read_state(run_id)
            if payload["revision"] != expected_revision:
                raise RuntimeError(
                    "Approval state changed concurrently: "
                    f"expected revision {expected_revision}, got {payload['revision']}"
                )
            payload["decision_result"] = decision_result
            payload["conversation_items"] = conversation_items
            for request in payload["approval_requests"]:
                if request["approval_id"] == approval_id:
                    request["decision_applied_at"] = _timestamp()
                    break
            else:
                raise KeyError(f"Approval request not found: {approval_id}")
            unresolved = any(
                request["status"] in {"pending", "approved", "executing", "failed"}
                for request in payload["approval_requests"]
            )
            payload["workflow_status"] = "review" if unresolved else "done"
            _write_state(run_id, payload)
            return payload
