"""Finance preflight gate for uploaded contract drafts."""

from __future__ import annotations

import asyncio
from typing import Any

from app.Agent.financeAgent import run_finance_preflight_agent
from app.Agent.hooks import AppContext
from app.schema.financeAgent import (
    FinancePreflightMissingField,
    FinancePreflightResult,
    FinancePreflightSynthesis,
    FinanceServiceMatch,
    GrossMarginRecommendation,
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
    # Only the uploaded row is visible to validation.  The isolated catalog
    # tool may separately read public.service when a margin recommendation is
    # needed; no other portfolio rows are exposed to preflight.
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


def _ensure_validation(store: dict[str, Any]) -> None:
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


def _field_error(
    field: str,
    label: str,
    reason: str,
    data_type: str,
) -> FinancePreflightMissingField:
    return FinancePreflightMissingField(
        field=field,
        label=label,
        reason=reason,
        data_type=data_type,
    )


def _catalog_match(row: dict[str, Any] | None) -> FinanceServiceMatch | None:
    if not row or row.get("target_margin") is None:
        return None
    try:
        target_margin = float(row["target_margin"])
    except (TypeError, ValueError):
        return None
    if not 0 <= target_margin <= 1:
        return None

    service_id = str(row.get("service_id") or "").strip()
    if not service_id:
        return None
    return FinanceServiceMatch(
        service_id=service_id,
        service_name=str(row.get("service_name") or service_id),
        target_margin=target_margin,
    )


def _build_margin_recommendation(
    synthesis: FinancePreflightSynthesis | None,
    catalog: list[dict[str, Any]],
) -> GrossMarginRecommendation | None:
    if synthesis is None or not synthesis.primary_service_id:
        return None

    by_id = {
        str(row.get("service_id")): row
        for row in catalog
        if row.get("service_id")
    }
    primary = _catalog_match(by_id.get(synthesis.primary_service_id))
    if primary is None:
        return None

    alternatives: list[FinanceServiceMatch] = []
    observed = {primary.service_id}
    for service_id in synthesis.alternative_service_ids:
        if service_id in observed:
            continue
        match = _catalog_match(by_id.get(service_id))
        if match is None:
            continue
        observed.add(service_id)
        alternatives.append(match)

    reasoning = str(synthesis.reasoning or synthesis.summary).strip()
    if not reasoning:
        reasoning = "Finance Agent đã chọn dịch vụ chính từ catalog OPC."
    return GrossMarginRecommendation(
        primary_service=primary,
        alternative_services=alternatives,
        recommended_gross_margin=primary.target_margin,
        confidence=synthesis.confidence,
        reasoning=reasoning,
    )


def _missing_summary(missing_fields: list[FinancePreflightMissingField]) -> str:
    return f"Payload còn thiếu {len(missing_fields)} trường cần bổ sung."


async def check_finance_preflight(
    contract: ContractUploadPackage,
) -> FinancePreflightResult:
    """Validate input and optionally produce a human-confirmed margin proposal."""
    data, upload_record = _prepare_data(contract)
    context = AppContext(
        document_id=f"PREFLIGHT-{upload_record}",
        original_input="Finance preflight for an uploaded contract draft",
        run_id=0,
        contract_id=upload_record,
        contract_ids=[upload_record],
        finance_store={"data": data},
    )

    # The gate is always deterministic.  The LLM is invoked only after all six
    # contract fields are present and only when gross_margin still needs a
    # recommendation.
    _ensure_validation(context.finance_store)
    validation = context.finance_store["validation"]
    missing_fields = _missing_fields(validation.issues, upload_record)
    if missing_fields:
        return FinancePreflightResult(
            status="AWAITING_INPUT",
            can_start_pipeline=False,
            missing_fields=missing_fields,
            summary=_missing_summary(missing_fields),
        )

    # A user-provided margin is authoritative for this form flow.  Do not load
    # the service catalog or ask the LLM to compare it with catalog targets.
    if contract.gross_margin is not None:
        return FinancePreflightResult(
            status="RUNNING",
            can_start_pipeline=True,
            summary="Payload đã đủ thông tin để bắt đầu full pipeline.",
        )

    synthesis, _execution = await run_finance_preflight_agent(context)
    raw_catalog = context.finance_store.get("service_catalog")
    catalog = raw_catalog if isinstance(raw_catalog, list) else []
    recommendation = _build_margin_recommendation(synthesis, catalog)
    if recommendation is None:
        margin_error = _field_error(
            "gross_margin",
            "Biên lợi nhuận gộp",
            (
                "Finance Agent chưa xác định được dịch vụ chính từ mô tả. "
                "Vui lòng nhập biên lợi nhuận gộp thủ công."
            ),
            "number",
        )
        return FinancePreflightResult(
            status="AWAITING_INPUT",
            can_start_pipeline=False,
            missing_fields=[margin_error],
            summary="Cần nhập gross margin trước khi bắt đầu phân tích.",
        )

    return FinancePreflightResult(
        status="AWAITING_CONFIRMATION",
        can_start_pipeline=False,
        gross_margin_recommendation=recommendation,
        summary="Finance Agent đã đề xuất gross margin. Vui lòng xác nhận trước khi tiếp tục.",
    )


async def preflight_and_start_pipeline(
    contract: ContractUploadPackage,
) -> FinancePreflightResult:
    """Persist and start the gated pipeline only after preflight passes."""
    result = await check_finance_preflight(contract)
    if not result.can_start_pipeline:
        return result

    from app.service.contract_service import (
        CustomerNotFoundError,
        create_contract_with_generated_id,
    )

    try:
        contract_id = await asyncio.to_thread(
            create_contract_with_generated_id,
            contract,
        )
    except CustomerNotFoundError:
        customer_error = _field_error(
            "customer_id",
            "Mã khách hàng",
            "Mã khách hàng không tồn tại trong dữ liệu demo.",
            "text",
        )
        return result.model_copy(
            update={
                "status": "AWAITING_INPUT",
                "can_start_pipeline": False,
                "missing_fields": [customer_error],
                "summary": "Vui lòng chọn mã khách hàng đã tồn tại.",
            }
        )

    authoritative_contract = contract.model_copy(
        update={
            "contract_id": contract_id,
            "status": "Pending approval",
        }
    )

    from app.service.pipeline_service import start_validated_pipeline_run

    started = await start_validated_pipeline_run(
        contract=authoritative_contract.model_dump(mode="json")
    )
    return result.model_copy(
        update={
            "status": "RUNNING",
            "can_start_pipeline": True,
            "session_id": started["session_id"],
            "contract_id": contract_id,
            "summary": "Hợp đồng đã được lưu và pipeline có cổng Validator đang chạy.",
        }
    )


__all__ = [
    "check_finance_preflight",
    "preflight_and_start_pipeline",
]
