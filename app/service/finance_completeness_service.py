"""Read-only Finance completeness gate for existing Team Pack contracts."""

from __future__ import annotations

import asyncio
from typing import Any

from app.Agent.financeAgent import run_finance_completeness_agent
from app.Agent.hooks import AppContext
from app.schema.financeAgent import (
    FinanceCompletenessIssue,
    FinanceCompletenessResult,
    FinanceCompletenessSynthesis,
)
from app.tools.FinanceAgent.completeness import (
    check_selected_contract_completeness,
    scope_data_to_contract,
)
from app.tools.FinanceAgent.finance_data import load_all


def _fallback_summary(
    contract_id: str,
    issues: list[FinanceCompletenessIssue],
) -> str:
    if not issues:
        return f"Finance Agent xác nhận dữ liệu của {contract_id} đã đầy đủ."
    return f"Finance Agent phát hiện {contract_id} còn thiếu dữ liệu."


def _trusted_agent_summary(
    synthesis: FinanceCompletenessSynthesis | None,
    issues: list[FinanceCompletenessIssue],
) -> str | None:
    if synthesis is None:
        return None
    expected_ids = [issue.issue_id for issue in issues]
    if synthesis.detected_issue_ids != expected_ids:
        return None
    summary = synthesis.summary.strip()
    return summary or None


async def check_existing_finance_completeness(
    contract_id: str,
) -> FinanceCompletenessResult | None:
    """Return a blocking report or ``None`` when linked contract rows are clean."""
    data = await asyncio.to_thread(load_all)
    normalized_id = contract_id.strip()
    # Resolve the deterministic relationship before invoking the model so an
    # unknown contract returns 404 without any agent or pipeline activity.
    scope_data_to_contract(data, normalized_id)

    context = AppContext(
        document_id=f"COMPLETENESS-{normalized_id}",
        original_input="Read-only Finance completeness preflight",
        run_id=0,
        contract_id=normalized_id,
        contract_ids=[normalized_id],
        finance_store={"data": data},
    )
    synthesis, execution_mode = await run_finance_completeness_agent(context)

    # Always recompute from the immutable snapshot. The model and its tool
    # output can influence wording only, never the authoritative issue list.
    issues = check_selected_contract_completeness(data, normalized_id)
    summary = _trusted_agent_summary(synthesis, issues)
    if summary is None:
        execution_mode = "deterministic_fallback"
        summary = _fallback_summary(normalized_id, issues)

    if not issues:
        return None
    return FinanceCompletenessResult(
        contract_id=normalized_id,
        execution_mode=execution_mode,
        summary=summary,
        missing_fields=issues,
    )


async def preflight_and_start_existing_contract(
    contract_id: str,
) -> dict[str, Any]:
    """Start the validated pipeline once, and only after a clean preflight."""
    blocked = await check_existing_finance_completeness(contract_id)
    if blocked is not None:
        return blocked.model_dump(mode="json")

    from app.service.pipeline_service import start_validated_pipeline_run

    return await start_validated_pipeline_run(
        contract=None,
        existing_contract_id=contract_id,
    )


__all__ = [
    "check_existing_finance_completeness",
    "preflight_and_start_existing_contract",
]
