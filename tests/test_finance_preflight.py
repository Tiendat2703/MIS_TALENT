from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.Agent import financeAgent as finance_agent_module
from app.Agent.financeAgent import build_finance_preflight_agent
from app.api import app
from app.schema.financeAgent import FinancePreflightResult, FinancePreflightSynthesis
from app.schema.pipeline_input import ContractUploadPackage
from app.service import finance_preflight_service


client = TestClient(app)


def _complete_payload(**overrides) -> dict:
    payload = {
        "contract_id": "CON-UPLOAD-001",
        "customer_id": "CUS-005",
        "start_date": "2026-08-01",
        "end_date": "2027-02-28",
        "description": "New uploaded contract",
        "contract_value": 1_200_000_000,
        "gross_margin": 0.25,
        "payment_terms": "30% advance, 50% delivery, 20% acceptance",
        "requested_amount": 300_000_000,
        "funding_need_type": "PERFORMANCE_BOND",
        "tenor": "7 months",
    }
    payload.update(overrides)
    return payload


def test_preflight_agent_exposes_only_read_only_finance_tools() -> None:
    agent = build_finance_preflight_agent()

    assert [tool.name for tool in agent.tools] == [
        "load_and_validate",
        "missing_data",
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
async def test_empty_draft_returns_all_eleven_missing_fields(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SKIP_LLM", "true")

    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate({}),
    )

    assert result.status == "AWAITING_INPUT"
    assert result.can_start_pipeline is False
    assert result.session_id is None
    assert len(result.missing_fields) == 11
    assert {item.field for item in result.missing_fields} == {
        "contract_id",
        "customer_id",
        "start_date",
        "end_date",
        "description",
        "contract_value",
        "gross_margin",
        "payment_terms",
        "requested_amount",
        "funding_need_type",
        "tenor",
    }
    assert result.data_issues == []


@pytest.mark.asyncio
async def test_partial_draft_returns_only_fields_still_missing(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SKIP_LLM", "true")
    payload = _complete_payload()
    payload["requested_amount"] = None
    payload["tenor"] = None

    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(payload),
    )

    assert [item.field for item in result.missing_fields] == [
        "requested_amount",
        "tenor",
    ]
    assert result.can_start_pipeline is False


@pytest.mark.asyncio
async def test_customer_reference_is_not_checked_during_preflight(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SKIP_LLM", "true")

    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(
            _complete_payload(customer_id="CUS-UNKNOWN")
        ),
    )

    assert result.missing_fields == []
    assert result.data_issues == []
    assert result.can_start_pipeline is True
    assert result.status == "RUNNING"


@pytest.mark.asyncio
async def test_preflight_agent_receives_only_the_uploaded_payload(monkeypatch) -> None:
    captured_data: dict = {}

    async def capture_context(context):
        captured_data.update(context.finance_store["data"])
        return None, "deterministic_fallback"

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        capture_context,
    )
    result = await finance_preflight_service.check_finance_preflight(
        ContractUploadPackage.model_validate(_complete_payload())
    )

    assert captured_data["source"] == "upload-preflight"
    assert captured_data["customers"] == []
    assert captured_data["orders"] == []
    assert captured_data["invoices"] == []
    assert captured_data["bank_txn"] == []
    assert captured_data["cashflow"] == []
    assert captured_data["upload"]["contract_id"] == "CON-UPLOAD-001"
    assert result.can_start_pipeline is True
    assert result.data_issues == []


@pytest.mark.asyncio
async def test_clean_preflight_starts_pipeline_once(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SKIP_LLM", "true")
    starts: list[dict] = []

    async def fake_start_pipeline_run(*, contract):
        starts.append(contract)
        return {"session_id": 321, "status": "running"}

    from app.service import pipeline_service

    monkeypatch.setattr(pipeline_service, "start_pipeline_run", fake_start_pipeline_run)
    result = await finance_preflight_service.preflight_and_start_pipeline(
        ContractUploadPackage.model_validate(_complete_payload())
    )

    assert result.status == "RUNNING"
    assert result.can_start_pipeline is True
    assert result.session_id == 321
    assert len(starts) == 1
    assert starts[0]["contract_id"] == "CON-UPLOAD-001"


@pytest.mark.asyncio
async def test_llm_failure_uses_the_same_deterministic_gate(monkeypatch) -> None:
    contract = ContractUploadPackage.model_validate(
        _complete_payload(requested_amount=None)
    )

    async def agentic_summary(_context):
        return FinancePreflightSynthesis(summary="Agent summary"), "agentic"

    async def failed_llm(_context):
        return None, "deterministic_fallback"

    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        agentic_summary,
    )
    agentic = await finance_preflight_service.check_finance_preflight(
        contract,
    )
    monkeypatch.setattr(
        finance_preflight_service,
        "run_finance_preflight_agent",
        failed_llm,
    )
    fallback = await finance_preflight_service.check_finance_preflight(
        contract,
    )

    assert fallback.status == agentic.status == "AWAITING_INPUT"
    assert fallback.can_start_pipeline is agentic.can_start_pipeline is False
    assert fallback.missing_fields == agentic.missing_fields
    assert fallback.data_issues == agentic.data_issues
    assert fallback.summary == agentic.summary == "Payload còn thiếu 1 trường cần bổ sung."


@pytest.mark.asyncio
async def test_preflight_is_read_only_and_does_not_start_when_blocked(monkeypatch) -> None:
    starts = 0

    monkeypatch.setenv("FINANCE_SKIP_LLM", "true")

    async def unexpected_start(*, contract):
        nonlocal starts
        starts += 1

    from app.service import pipeline_service

    monkeypatch.setattr(pipeline_service, "start_pipeline_run", unexpected_start)
    result = await finance_preflight_service.preflight_and_start_pipeline(
        ContractUploadPackage.model_validate({})
    )

    assert result.status == "AWAITING_INPUT"
    assert result.session_id is None
    assert starts == 0


def test_finance_preflight_endpoint_returns_structured_missing_fields(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SKIP_LLM", "true")

    response = client.post("/finance/preflight", json={})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "status",
        "can_start_pipeline",
        "session_id",
        "missing_fields",
        "data_issues",
        "summary",
    }
    assert body["status"] == "AWAITING_INPUT"
    assert body["session_id"] is None
    assert len(body["missing_fields"]) == 11


def test_runs_with_contract_body_uses_the_same_preflight_gate(monkeypatch) -> None:
    calls: list[ContractUploadPackage] = []

    async def fake_preflight(contract: ContractUploadPackage) -> FinancePreflightResult:
        calls.append(contract)
        return FinancePreflightResult(
            status="AWAITING_INPUT",
            can_start_pipeline=False,
            missing_fields=[],
            data_issues=[],
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
