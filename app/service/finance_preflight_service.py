"""Read-only Finance preflight gate for uploaded contract drafts."""

from __future__ import annotations

from typing import Any

from app.Agent.financeAgent import run_finance_preflight_agent
from app.Agent.hooks import AppContext
from app.schema.financeAgent import (
    FinancePreflightMissingField,
    FinancePreflightResult,
    ValidationIssue,
)
from app.schema.pipeline_input import ContractUploadPackage
from app.tools.FinanceAgent.validate_data import (
    UPLOAD_FIELD_REQUIREMENTS,
    validate_finance_data,
)


_DRAFT_CONTRACT_ID = "UPLOAD-DRAFT"


def _prepare_data(
    contract: ContractUploadPackage,
) -> tuple[dict[str, Any], str]:
    raw_upload = contract.model_dump(mode="json")
    record_id = contract.contract_id or _DRAFT_CONTRACT_ID
    analysis_contract = {**raw_upload, "contract_id": record_id}
    # Preflight intentionally receives no portfolio/database rows. Its only
    # responsibility is checking the eleven fields in the submitted draft.
    data = {
        "contracts": [analysis_contract],
        "orders": [],
        "invoices": [],
        "bank_txn": [],
        "cashflow": [],
        "customers": [],
        "services": [],
        "profile": {},
        "source": "upload-preflight",
        "scenario": None,
        "upload": raw_upload,
        "_preflight_upload_record_id": record_id,
        "_preflight_payload_only": True,
    }
    return data, record_id


def _ensure_validation(store: dict) -> None:
    if "validation" not in store:
        store["validation"] = validate_finance_data(store["data"])


def _missing_fields(
    issues: list[ValidationIssue],
    upload_record: str,
) -> list[FinancePreflightMissingField]:
    fields: list[FinancePreflightMissingField] = []
    observed: set[str] = set()
    for issue in issues:
        if (
            issue.kind != "missing_field"
            or issue.record != upload_record
            or issue.column not in UPLOAD_FIELD_REQUIREMENTS
            or issue.column in observed
        ):
            continue
        observed.add(issue.column)
        requirement = UPLOAD_FIELD_REQUIREMENTS[issue.column]
        fields.append(
            FinancePreflightMissingField(
                field=issue.column,
                label=str(requirement["label"]),
                reason=str(requirement["reason"]),
                data_type=str(requirement["data_type"]),
            )
        )
    return fields


def _build_summary(
    missing_fields: list[FinancePreflightMissingField],
) -> str:
    if not missing_fields:
        return "Payload đã có đầy đủ 11 trường để bắt đầu full pipeline."
    return f"Payload còn thiếu {len(missing_fields)} trường cần bổ sung."


async def check_finance_preflight(
    contract: ContractUploadPackage,
) -> FinancePreflightResult:
    """Check only payload completeness without loading portfolio/database data."""
    data, upload_record = _prepare_data(contract)
    context = AppContext(
        document_id=f"PREFLIGHT-{upload_record}",
        original_input="Finance preflight for an uploaded contract draft",
        run_id=0,
        contract_id=upload_record,
        contract_ids=[upload_record],
        finance_store={"data": data},
    )
    # The isolated agent still executes its two read-only tools, but no LLM text
    # is allowed to affect the public result or expand the validation scope.
    await run_finance_preflight_agent(context)
    _ensure_validation(context.finance_store)

    validation = context.finance_store["validation"]
    missing_fields = _missing_fields(
        validation.issues,
        upload_record,
    )
    can_start = not missing_fields

    return FinancePreflightResult(
        status="RUNNING" if can_start else "AWAITING_INPUT",
        can_start_pipeline=can_start,
        missing_fields=missing_fields,
        data_issues=[],
        summary=_build_summary(missing_fields),
    )


async def preflight_and_start_pipeline(
    contract: ContractUploadPackage,
) -> FinancePreflightResult:
    """Start the full pipeline only after the isolated Finance gate is clean."""
    result = await check_finance_preflight(contract)
    if not result.can_start_pipeline:
        return result

    from app.service.pipeline_service import start_pipeline_run

    started = await start_pipeline_run(contract=contract.model_dump(mode="json"))
    return result.model_copy(
        update={
            "status": "RUNNING",
            "can_start_pipeline": True,
            "session_id": started["session_id"],
        }
    )


__all__ = [
    "check_finance_preflight",
    "preflight_and_start_pipeline",
]
