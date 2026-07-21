from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.Agent import financeAgent as finance_agent_module
from app.Agent.financeAgent import build_finance_preflight_agent
from app.api import app
from app.schema.financeAgent import FinancePreflightResult, FinancePreflightSynthesis
from app.schema.pipeline_input import ContractUploadPackage
from app.service import contract_service, finance_preflight_service


client = TestClient(app)


def _complete_payload(**overrides) -> dict:
    payload = {
        "contract_id": "CON-006",
        "customer_id": "CUS-005",
        "start_date": "2026-08-01",
        "end_date": "2027-02-28",
        "description": "Triển khai hệ thống bán hàng số cho doanh nghiệp",
        "contract_value": 1_200_000_000,
        "gross_margin": 0.32,
        "payment_terms": "Milestone payment",
        "requested_amount": None,
        "funding_need_type": None,
        "tenor": None,
    }
    payload.update(overrides)
    return payload


def _service_row(
    service_id: str = "SVC-001",
    target_margin: float = 0.32,
    service_name: str = "Digital Sales Setup",
) -> dict:
    return {
        "service_id": service_id,
        "service_name": service_name,
        "pricing_model": "Initial setup",
        "target_margin": target_margin,
        "target_segment": "SME",
    }


def test_preflight_agent_exposes_only_read_only_finance_tools() -> None:
    agent = build_finance_preflight_agent()

    assert [tool.name for tool in agent.tools] == [
        "load_and_validate",
        "missing_data",
        "load_service_catalog",
    ]
    assert agent.handoffs == []
    assert agent.hooks is None


@pytest.mark.asyncio
async def test_preflight_agent_catches_llm_failure(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SKIP_LLM", "false")

    def fail_to_build_agent():
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(
        finance_agent_module,
        "_get_preflight_agent",
        fail_to_build_agent,
    )
    synthesis, execution = await finance_agent_module.run_finance_preflight_agent(
        object()
    )

    assert synthesis is None
    assert execution == "deterministic_fallback"


@pytest.mark.asyncio
async def test_empty_draft_returns_six_business_fields(monkeypatch) -> None:
    async def unexpected_agent(_context):
        raise AssertionError("recommendation must not run while required fields are missing")

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        unexpected_agent,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate({}),
    )

    assert result.status == "AWAITING_INPUT"
    assert result.can_start_pipeline is False
    assert result.session_id is None
    assert result.contract_id is None
    assert {item.field for item in result.missing_fields} == {
        "customer_id",
        "start_date",
        "end_date",
        "description",
        "contract_value",
        "payment_terms",
    }
    assert len(result.missing_fields) == 6
    assert result.gross_margin_recommendation is None


@pytest.mark.asyncio
async def test_partial_draft_returns_only_fields_still_missing(monkeypatch) -> None:
    payload = _complete_payload(end_date=None, payment_terms=None)

    async def unexpected_agent(_context):
        raise AssertionError("recommendation must not run while required fields are missing")

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        unexpected_agent,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(payload),
    )

    assert [item.field for item in result.missing_fields] == [
        "end_date",
        "payment_terms",
    ]
    assert result.can_start_pipeline is False


@pytest.mark.asyncio
async def test_user_margin_skips_agent_and_catalog(monkeypatch) -> None:
    async def unexpected_agent(_context):
        raise AssertionError("manual gross margin must bypass recommendation")

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        unexpected_agent,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(_complete_payload(gross_margin=0.05))
    )

    assert result.status == "RUNNING"
    assert result.can_start_pipeline is True
    assert result.gross_margin_recommendation is None


@pytest.mark.asyncio
async def test_description_maps_to_primary_catalog_margin(monkeypatch) -> None:
    async def agentic_mapping(context):
        context.finance_store["service_catalog"] = [
            _service_row(),
            _service_row("SVC-003", 0.38, "Customer Care Agent Pack"),
        ]
        return (
            FinancePreflightSynthesis(
                summary="Khớp dịch vụ bán hàng số.",
                primary_service_id="SVC-001",
                alternative_service_ids=["SVC-003"],
                confidence=0.91,
                reasoning="Phạm vi chính là thiết lập kênh bán hàng số; 99% chỉ là text.",
            ),
            "agentic",
        )

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        agentic_mapping,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(_complete_payload(gross_margin=None))
    )

    assert result.status == "AWAITING_CONFIRMATION"
    assert result.can_start_pipeline is False
    assert result.session_id is None
    assert result.contract_id is None
    recommendation = result.gross_margin_recommendation
    assert recommendation is not None
    assert recommendation.primary_service.service_id == "SVC-001"
    assert recommendation.recommended_gross_margin == 0.32
    assert [item.service_id for item in recommendation.alternative_services] == [
        "SVC-003"
    ]


@pytest.mark.asyncio
async def test_unknown_service_id_is_rejected_and_requires_manual_margin(monkeypatch) -> None:
    async def invalid_mapping(context):
        context.finance_store["service_catalog"] = [_service_row()]
        return (
            FinancePreflightSynthesis(
                summary="Invalid",
                primary_service_id="SVC-INVENTED",
                confidence=1,
                reasoning="Invented service",
            ),
            "agentic",
        )

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        invalid_mapping,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(_complete_payload(gross_margin=None))
    )

    assert result.status == "AWAITING_INPUT"
    assert [item.field for item in result.missing_fields] == ["gross_margin"]
    assert result.gross_margin_recommendation is None


@pytest.mark.asyncio
async def test_llm_failure_requires_manual_margin(monkeypatch) -> None:
    async def failed_llm(_context):
        return None, "deterministic_fallback"

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        failed_llm,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(_complete_payload(gross_margin=None))
    )

    assert result.status == "AWAITING_INPUT"
    assert [item.field for item in result.missing_fields] == ["gross_margin"]
    assert result.can_start_pipeline is False


@pytest.mark.asyncio
async def test_customer_reference_is_not_checked_before_persistence(monkeypatch) -> None:
    async def unexpected_agent(_context):
        raise AssertionError("manual margin must bypass recommendation")

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        unexpected_agent,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(
            _complete_payload(customer_id="CUS-UNKNOWN")
        ),
    )

    assert result.missing_fields == []
    assert result.can_start_pipeline is True
    assert result.status == "RUNNING"


@pytest.mark.asyncio
async def test_clean_preflight_persists_then_starts_pipeline_once(monkeypatch) -> None:
    starts: list[dict] = []
    persisted: list[ContractUploadPackage] = []

    def fake_create(contract: ContractUploadPackage) -> str:
        persisted.append(contract)
        return "CON-006"

    async def fake_start_pipeline_run(*, contract):
        starts.append(contract)
        return {"session_id": 321, "status": "running"}

    from app.service import pipeline_service

    monkeypatch.setattr(
        contract_service,
        "create_contract_with_generated_id",
        fake_create,
    )
    monkeypatch.setattr(pipeline_service, "start_pipeline_run", fake_start_pipeline_run)
    result = await finance_preflight_service.preflight_and_start_pipeline(
        ContractUploadPackage.model_validate(_complete_payload(contract_id="CON-PREVIEW"))
    )

    assert result.status == "RUNNING"
    assert result.can_start_pipeline is True
    assert result.session_id == 321
    assert result.contract_id == "CON-006"
    assert len(persisted) == 1
    assert len(starts) == 1
    assert starts[0]["contract_id"] == "CON-006"
    assert starts[0]["status"] == "Pending approval"
    assert starts[0]["requested_amount"] is None
    assert starts[0]["funding_need_type"] is None
    assert starts[0]["tenor"] is None


@pytest.mark.asyncio
async def test_unknown_customer_blocks_inserted_run(monkeypatch) -> None:
    starts = 0

    def missing_customer(_contract: ContractUploadPackage) -> str:
        raise contract_service.CustomerNotFoundError("CUS-UNKNOWN")

    async def unexpected_start(*, contract):
        nonlocal starts
        starts += 1

    from app.service import pipeline_service

    monkeypatch.setattr(
        contract_service,
        "create_contract_with_generated_id",
        missing_customer,
    )
    monkeypatch.setattr(pipeline_service, "start_pipeline_run", unexpected_start)
    result = await finance_preflight_service.preflight_and_start_pipeline(
        ContractUploadPackage.model_validate(
            _complete_payload(customer_id="CUS-UNKNOWN")
        )
    )

    assert result.status == "AWAITING_INPUT"
    assert [item.field for item in result.missing_fields] == ["customer_id"]
    assert result.session_id is None
    assert result.contract_id is None
    assert starts == 0


@pytest.mark.asyncio
async def test_preflight_does_not_persist_or_start_when_blocked(monkeypatch) -> None:
    def unexpected_create(_contract):
        raise AssertionError("blocked drafts must not be persisted")

    monkeypatch.setattr(
        contract_service,
        "create_contract_with_generated_id",
        unexpected_create,
    )
    result = await finance_preflight_service.preflight_and_start_pipeline(
        ContractUploadPackage.model_validate({})
    )

    assert result.status == "AWAITING_INPUT"
    assert result.session_id is None


def test_finance_preflight_endpoint_returns_structured_missing_fields() -> None:
    response = client.post("/finance/preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "status",
        "can_start_pipeline",
        "session_id",
        "contract_id",
        "missing_fields",
        "data_issues",
        "gross_margin_recommendation",
        "summary",
    }
    assert body["status"] == "AWAITING_INPUT"
    assert body["session_id"] is None
    assert len(body["missing_fields"]) == 6


def test_next_contract_id_endpoint_returns_preview(monkeypatch) -> None:
    monkeypatch.setattr(
        contract_service,
        "get_next_contract_id_preview",
        lambda: "CON-006",
    )

    response = client.get("/contracts/next-id")

    assert response.status_code == 200
    assert response.json() == {"contract_id": "CON-006"}


def test_runs_with_contract_body_uses_the_same_preflight_gate(monkeypatch) -> None:
    calls: list[ContractUploadPackage] = []

    async def fake_preflight(contract: ContractUploadPackage) -> FinancePreflightResult:
        calls.append(contract)
        return FinancePreflightResult(
            status="AWAITING_INPUT",
            can_start_pipeline=False,
            summary="blocked",
        )

    monkeypatch.setattr(
        finance_preflight_service,
        "preflight_and_start_pipeline",
        fake_preflight,
    )
    response = client.post("/runs", json=_complete_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "AWAITING_INPUT"
    assert len(calls) == 1
