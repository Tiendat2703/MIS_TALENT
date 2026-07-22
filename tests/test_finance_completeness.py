"""Deterministic and API tests for the Team Pack Finance completeness gate."""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.Agent import financeAgent as finance_agent_module
from app.Agent.financeAgent import build_finance_completeness_agent
from app.api import app
from app.schema.financeAgent import (
    FinanceCompletenessIssue,
    FinanceCompletenessResult,
    FinanceCompletenessSynthesis,
)
from app.service import finance_completeness_service, pipeline_service
from app.tools.FinanceAgent.completeness import (
    check_selected_contract_completeness,
)


client = TestClient(app)


def _complete_data() -> dict:
    return {
        "contracts": [{
            "contract_id": "CON-004",
            "customer_id": "CUS-004",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "status": "Active",
            "description": "ERP implementation",
            "contract_value": 3_100_000_000,
            "gross_margin": 0.24,
            "payment_terms": "Milestone",
        }],
        "orders": [{
            "order_id": "ORD-005",
            "contract_id": "CON-004",
            "customer_id": "CUS-004",
            "order_date": "2026-01-02",
            "due_date": "2026-08-31",
            "status": "Pending approval",
            "service_id": "SVC-004",
            "order_revenue": 1_600_000_000,
            "estimated_cost": 1_216_000_000,
            "delivery_note": "Awaiting kickoff",
        }],
        "invoices": [{
            "invoice_id": "INV-005",
            "order_id": "ORD-005",
            "customer_id": "CUS-004",
            "issue_date": "2026-07-01",
            "due_date": "2026-09-29",
            "status": "Open",
            "invoice_amount": 1_600_000_000,
            "paid_date": None,
        }],
        "bank_txn": [{
            "txn_id": "TXN-005",
            "txn_date": "2026-07-02",
            "bank": "VCB",
            "account_id": "ACC-001",
            "direction": "Credit",
            "description": "Customer deposit",
            "amount": 100_000_000,
            "counterparty_id": "CUS-004",
            "txn_status": "Posted",
            "transaction_risk_score": 0,
        }],
        "cashflow": [{
            "month": "2026-07",
            "expected_cash_in": 0,
            "expected_cash_out": 300_000_000,
            "direct_cost": 120_000_000,
            "opex": 80_000_000,
            "cash_reserve_minimum": 550_000_000,
            "projected_closing_cash": 0,
            "management_note": "Monitor collection",
        }],
        "customers": [],
        "services": [],
        "profile": {},
        "source": "test",
        "scenario": None,
    }


@pytest.mark.parametrize(
    ("table_key", "column", "expected_id"),
    [
        ("contracts", "description", "contract|CON-004|description"),
        ("orders", "estimated_cost", "orders|ORD-005|estimated_cost"),
        ("invoices", "invoice_amount", "invoice|INV-005|invoice_amount"),
    ],
)
def test_detects_missing_cell_in_each_contract_scoped_table(
    table_key: str,
    column: str,
    expected_id: str,
) -> None:
    data = _complete_data()
    data[table_key][0][column] = None

    issues = check_selected_contract_completeness(data, "CON-004")

    assert [issue.issue_id for issue in issues] == [expected_id]
    assert issues[0].column == column


def test_zero_false_and_non_empty_values_are_valid() -> None:
    data = _complete_data()
    data["orders"][0]["estimated_cost"] = 0
    data["orders"][0]["reviewed"] = False

    assert check_selected_contract_completeness(data, "CON-004") == []


def test_unpaid_invoice_may_have_no_paid_date() -> None:
    data = _complete_data()
    data["invoices"][0]["status"] = "Not issued"

    assert check_selected_contract_completeness(data, "CON-004") == []


def test_paid_invoice_requires_paid_date() -> None:
    data = _complete_data()
    data["invoices"][0]["status"] = "Paid"

    issues = check_selected_contract_completeness(data, "CON-004")

    assert [issue.issue_id for issue in issues] == [
        "invoice|INV-005|paid_date"
    ]
    assert issues[0].data_type == "date"


def test_missing_fields_from_another_contract_are_ignored() -> None:
    data = _complete_data()
    data["contracts"].append({
        **data["contracts"][0],
        "contract_id": "CON-999",
        "description": None,
    })
    data["orders"].append({
        **data["orders"][0],
        "order_id": "ORD-999",
        "contract_id": "CON-999",
        "estimated_cost": None,
    })
    data["invoices"].append({
        **data["invoices"][0],
        "invoice_id": "INV-999",
        "order_id": "ORD-999",
        "invoice_amount": None,
    })

    assert check_selected_contract_completeness(data, "CON-004") == []


def test_bank_transactions_and_cashflow_are_not_contract_scoped() -> None:
    data = _complete_data()
    data["bank_txn"][0]["description"] = None
    data["cashflow"][0]["management_note"] = "   "

    assert check_selected_contract_completeness(data, "CON-004") == []


def test_completeness_agent_exposes_only_one_read_tool() -> None:
    agent = build_finance_completeness_agent()

    assert [tool.name for tool in agent.tools] == [
        "check_selected_contract_completeness"
    ]
    assert agent.handoffs == []
    assert agent.hooks is None


@pytest.mark.asyncio
async def test_completeness_agent_catches_llm_failure(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SKIP_LLM", "false")

    def fail_to_build_agent():
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(
        finance_agent_module,
        "_get_completeness_agent",
        fail_to_build_agent,
    )
    synthesis, execution = await finance_agent_module.run_finance_completeness_agent(
        object()
    )

    assert synthesis is None
    assert execution == "deterministic_fallback"


@pytest.mark.asyncio
async def test_missing_data_blocks_pipeline_and_returns_exact_report(monkeypatch) -> None:
    data = _complete_data()
    data["orders"][0]["estimated_cost"] = None
    starts = 0

    async def agentic(context):
        issue_id = "orders|ORD-005|estimated_cost"
        context.finance_store["completeness"] = []
        return (
            FinanceCompletenessSynthesis(
                summary="Finance Agent phát hiện dữ liệu đầu vào chưa đầy đủ.",
                detected_issue_ids=[issue_id],
            ),
            "agentic",
        )

    async def unexpected_start(**_kwargs):
        nonlocal starts
        starts += 1

    monkeypatch.setattr(finance_completeness_service, "load_all", lambda: deepcopy(data))
    monkeypatch.setattr(
        finance_completeness_service,
        "run_finance_completeness_agent",
        agentic,
    )
    monkeypatch.setattr(
        pipeline_service,
        "start_validated_pipeline_run",
        unexpected_start,
    )

    result = await finance_completeness_service.preflight_and_start_existing_contract(
        "CON-004"
    )

    assert result == {
        "status": "AWAITING_INPUT",
        "can_start_pipeline": False,
        "session_id": None,
        "contract_id": "CON-004",
        "execution_mode": "agentic",
        "summary": "Finance Agent phát hiện dữ liệu đầu vào chưa đầy đủ.",
        "missing_fields": [{
            "issue_id": "orders|ORD-005|estimated_cost",
            "table": "orders",
            "table_label": "06_ORDERS",
            "record_id": "ORD-005",
            "column": "estimated_cost",
            "data_type": "number",
            "reason": "Thiếu estimated_cost của ORD-005",
        }],
    }
    assert starts == 0


@pytest.mark.asyncio
async def test_clean_data_starts_pipeline_exactly_once(monkeypatch) -> None:
    starts: list[dict] = []
    data = _complete_data()
    data["contracts"].append({
        **data["contracts"][0],
        "contract_id": "CON-999",
        "description": None,
    })
    data["bank_txn"][0]["description"] = None
    data["cashflow"][0]["management_note"] = None

    async def clean_agent(context):
        context.finance_store["completeness"] = []
        return (
            FinanceCompletenessSynthesis(
                summary="Năm bảng baseline đã đầy đủ.",
                detected_issue_ids=[],
            ),
            "agentic",
        )

    async def fake_start(**kwargs):
        starts.append(kwargs)
        return {
            "session_id": 321,
            "status": "running",
            "gated": True,
            "contract_id": kwargs["existing_contract_id"],
        }

    monkeypatch.setattr(finance_completeness_service, "load_all", lambda: data)
    monkeypatch.setattr(
        finance_completeness_service,
        "run_finance_completeness_agent",
        clean_agent,
    )
    monkeypatch.setattr(pipeline_service, "start_validated_pipeline_run", fake_start)

    result = await finance_completeness_service.preflight_and_start_existing_contract(
        "CON-004"
    )

    assert result["session_id"] == 321
    assert starts == [{"contract": None, "existing_contract_id": "CON-004"}]


@pytest.mark.asyncio
async def test_unknown_contract_stops_before_agent_and_pipeline(monkeypatch) -> None:
    async def unexpected(*_args, **_kwargs):
        raise AssertionError("agent and pipeline must not run")

    monkeypatch.setattr(finance_completeness_service, "load_all", _complete_data)
    monkeypatch.setattr(
        finance_completeness_service,
        "run_finance_completeness_agent",
        unexpected,
    )
    monkeypatch.setattr(pipeline_service, "start_validated_pipeline_run", unexpected)

    with pytest.raises(LookupError, match="CON-404"):
        await finance_completeness_service.preflight_and_start_existing_contract(
            "CON-404"
        )


def test_validated_run_returns_404_for_unknown_contract(monkeypatch) -> None:
    async def unknown(_contract_id: str):
        raise LookupError("Contract does not exist: CON-404")

    monkeypatch.setattr(
        finance_completeness_service,
        "preflight_and_start_existing_contract",
        unknown,
    )

    response = client.post("/runs/validated", params={"contract_id": "CON-404"})

    assert response.status_code == 404
    assert "CON-404" in response.json()["detail"]


def test_validated_run_api_returns_awaiting_input_without_starting(monkeypatch) -> None:
    starts = 0
    blocked = FinanceCompletenessResult(
        contract_id="CON-004",
        execution_mode="deterministic_fallback",
        summary="Finance Agent phát hiện dữ liệu đầu vào chưa đầy đủ.",
        missing_fields=[FinanceCompletenessIssue(
            issue_id="orders|ORD-005|estimated_cost",
            table="orders",
            table_label="06_ORDERS",
            record_id="ORD-005",
            column="estimated_cost",
            data_type="number",
            reason="Thiếu estimated_cost của ORD-005",
        )],
    )

    async def blocked_preflight(_contract_id: str):
        return blocked

    async def unexpected_start(**_kwargs):
        nonlocal starts
        starts += 1

    monkeypatch.setattr(
        finance_completeness_service,
        "check_existing_finance_completeness",
        blocked_preflight,
    )
    monkeypatch.setattr(
        pipeline_service,
        "start_validated_pipeline_run",
        unexpected_start,
    )

    response = client.post("/runs/validated", params={"contract_id": "CON-004"})

    assert response.status_code == 200
    assert response.json()["status"] == "AWAITING_INPUT"
    assert response.json()["session_id"] is None
    assert response.json()["missing_fields"][0]["issue_id"] == (
        "orders|ORD-005|estimated_cost"
    )
    assert starts == 0


@pytest.mark.asyncio
async def test_llm_failure_keeps_deterministic_blocking_result(monkeypatch) -> None:
    data = _complete_data()
    data["orders"][0]["delivery_note"] = None

    async def failed_agent(_context):
        return None, "deterministic_fallback"

    monkeypatch.setattr(finance_completeness_service, "load_all", lambda: data)
    monkeypatch.setattr(
        finance_completeness_service,
        "run_finance_completeness_agent",
        failed_agent,
    )

    result = await finance_completeness_service.check_existing_finance_completeness(
        "CON-004"
    )

    assert result is not None
    assert result.execution_mode == "deterministic_fallback"
    assert [issue.issue_id for issue in result.missing_fields] == [
        "orders|ORD-005|delivery_note"
    ]
