"""Validate (QC) Agent — agentic reviewer đặt sau mỗi stage của pipeline.

Mỗi lần một agent chính (Finance / Risk / Decision) chạy xong, orchestrator gọi
``validate_stage(session_id, stage)``. Validator load đúng checklist của stage, đọc
run_log + output_pack đã persist, rồi trả một ``ValidationReport`` với verdict đóng
vai trò CỔNG: chỉ ``PASS`` mới cho pipeline đi tiếp.

Validator KHÔNG sửa số liệu; nó chỉ phán xử và tạo challenge ticket.

Chạy thử một stage đã có trong context:
    python -m app.Agent.validatorAgent <session_id> <finance|risk|decision>
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.Agent.bus import event_bus
from app.Agent.hooks import AppContext
from app.Agent.prompt_loader import load_prompt
from app.schema.validatorAgent import Stage, ValidationReport

PROMPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "validatorAgent.md"
AGENT_NAME = "Validator_Agent"

_VALID_STAGES: tuple[str, ...] = ("finance", "risk", "decision")
_STAGE_AGENT = {
    "finance": "Finance_Agent",
    "risk": "Risk_Agent",
    "decision": "Decision_Agent",
}

_STANDALONE_AGENT = None


def build_validator_agent(*, handoffs: Sequence[Any] = ()):
    """Create the Validate Agent. Handoffs bình thường không cần (validator là cổng)."""
    from agents import Agent, ModelSettings, OpenAIChatCompletionsModel

    from app.Agent.config import OPENAI_MODEL, get_openai_client
    from app.Agent.hooks import CustomAgentHooks
    from app.tools.ValidatorAgent import load_validation_evidence

    prompt = load_prompt(PROMPT_PATH)
    return Agent(
        name=AGENT_NAME,
        model=OpenAIChatCompletionsModel(
            model=OPENAI_MODEL,
            openai_client=get_openai_client(),
        ),
        instructions=prompt,
        handoff_description=(
            "QC reviewer. Reads one stage's run_log and persisted output pack, checks "
            "the matching checklist, and returns a gating verdict."
        ),
        output_type=ValidationReport,
        tools=[load_validation_evidence],
        handoffs=list(handoffs),
        model_settings=ModelSettings(parallel_tool_calls=False),
        hooks=CustomAgentHooks(AGENT_NAME),
    )


def get_validator_agent():
    global _STANDALONE_AGENT
    if _STANDALONE_AGENT is None:
        _STANDALONE_AGENT = build_validator_agent()
    return _STANDALONE_AGENT


def _normalize_report(
    report: ValidationReport,
    session_id: int,
    stage: str,
) -> ValidationReport:
    """Ghim session_id/stage/validated_at theo input, chạy lại validator schema."""
    data = report.model_dump()
    data["session_id"] = session_id
    data["stage"] = stage
    data["validated_at"] = datetime.now(timezone.utc)
    return ValidationReport.model_validate(data)


def persist_validator_reports(
    session_id: int,
    reports: Sequence[ValidationReport],
) -> None:
    """Ghi toàn bộ report validator của run vào cột ValidatorLogs (best-effort).

    Ghi cả danh sách để ba lần QC trong một run không đè lẫn nhau.
    """
    try:
        from app.tools.writeLogs import persist_agent_stage_log

        payload = {
            "reports": [report.model_dump(mode="json") for report in reports],
            "latest_verdict": reports[-1].verdict if reports else None,
        }
        persist_agent_stage_log(session_id, "validator", payload)
    except Exception as exc:  # log là phụ; không được làm hỏng gate
        print(f"[validator] Could not persist ValidatorLogs: {type(exc).__name__}: {exc}")


async def validate_stage(
    session_id: int,
    stage: Stage,
    *,
    context: AppContext | None = None,
    max_turns: int = 6,
) -> ValidationReport:
    """Chạy Validate Agent cho đúng một stage và trả về ValidationReport (gate)."""
    from agents import Runner

    if stage not in _VALID_STAGES:
        raise ValueError(f"Unknown validation stage: {stage!r}")

    if context is None:
        context = AppContext(
            document_id=f"VALIDATE-{session_id}-{stage}",
            original_input="",
            run_id=session_id,
        )
    if context.run_id != session_id:
        raise ValueError("Validator context.run_id must equal session_id")

    validator_input = json.dumps(
        {
            "session_id": session_id,
            "stage": stage,
            "instruction": (
                f"Kiểm tra {_STAGE_AGENT[stage]}. Gọi load_validation_evidence đúng một "
                f"lần với session_id={session_id}, stage={stage!r}, chấm checklist của "
                "stage rồi trả ValidationReport."
            ),
        },
        ensure_ascii=False,
    )

    await event_bus.emit(
        session_id,
        {
            "type": "validation_started",
            "agent": AGENT_NAME,
            "task": f"Validator kiểm tra {_STAGE_AGENT[stage]}",
            "status": "running",
            "data": {"stage": stage},
        },
    )

    result = await Runner.run(
        get_validator_agent(),
        input=validator_input,
        context=context,
        max_turns=max_turns,
    )
    if not isinstance(result.final_output, ValidationReport):
        raise TypeError("Validator did not return a ValidationReport")

    report = _normalize_report(result.final_output, session_id, stage)

    await event_bus.emit(
        session_id,
        {
            "type": "validation_finished" if report.passed else "validation_challenge",
            "agent": AGENT_NAME,
            "target_agent": _STAGE_AGENT[stage],
            "task": (
                f"{_STAGE_AGENT[stage]}: {report.verdict}"
                + ("" if report.passed else f" — {len(report.challenge_tickets)} ticket")
            ),
            "status": "done" if report.passed else "review",
            "summary": report.summary[:500],
            "data": report.model_dump(mode="json"),
        },
    )
    return report


async def _main() -> None:
    import sys

    if len(sys.argv) < 3:
        raise SystemExit(
            "Usage: python -m app.Agent.validatorAgent <session_id> "
            "<finance|risk|decision>"
        )
    session_id = int(sys.argv[1])
    stage = sys.argv[2]
    report = await validate_stage(session_id, stage)  # type: ignore[arg-type]
    persist_validator_reports(session_id, [report])
    print(report.model_dump_json(indent=2))


__all__ = [
    "AGENT_NAME",
    "build_validator_agent",
    "get_validator_agent",
    "persist_validator_reports",
    "validate_stage",
]


if __name__ == "__main__":
    asyncio.run(_main())
