"""Integration-contract tests that do not require OpenAI or Supabase."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.Agent.bus import event_bus
from app.database import context_store
from app.schema.decisionAgent import DecisionBatchOutput, DecisionCardOutput
from app.schema.financeAgent import (
    BankReconciliationSummary,
    FinanceAnalysisPack,
    InvoiceClassification,
    LiquidityBrief,
    LiquidityMonth,
    MarginAnalysis,
)
from app.schema.handoff_packs import (
    FinanceBatchPack,
    FinanceFeaturePack,
    RiskBatchPack,
    RiskPack,
)
from app.schema.pipeline_input import ContractUploadPackage
from app.service.finance_handoff import build_finance_handoff, infer_funding_need_type
from app.service import approval as approval_service
from app.service.decision_guard import (
    validate_decision_finance_consistency,
    validate_decision_prechecks,
)
from app.service.pipeline_input import (
    load_contract_package,
    merge_contract_package,
    select_pipeline_scope,
)
from app.service.pipeline_service import _effective_funding_need_type
from app.tools import writeLogs
from app.tools.DecisionAgent.GetBankProduct import _evaluate_product
from app.tools.DecisionAgent.PrecheckAPI import _call_api
from app.tools.FinanceAgent.finance_data import load_all


def _finance_pack() -> FinanceFeaturePack:
    return FinanceFeaturePack(
        case_id="CASE-CON-004",
        contract_id="CON-004",
        company_id="OPC-001",
        generated_at=datetime.now(UTC),
        requested_amount=420_000_000,
        funding_need_type="PERFORMANCE_BOND",
        source_record_ids=["CON-004"],
        handoff_summary="Finance handoff for CON-004.",
    )


def _decision_batch() -> DecisionBatchOutput:
    return DecisionBatchOutput(
        decisions=[
            DecisionCardOutput(
                contract_id="CON-004",
                accept_opportunity=False,
                recommended_option="APPROVE_WITH_CONDITION",
                protective_condition="Human review is required.",
                capital_need=420_000_000,
                risk_level="medium",
                decision_status="review",
                reasons=["Finance reason", "Risk reason", "Product reason"],
            )
        ],
    )


def _finance_analysis() -> FinanceAnalysisPack:
    return FinanceAnalysisPack(
        metadata={"scope": "portfolio"},
        liquidity_brief=LiquidityBrief(
            by_month=[
                LiquidityMonth(
                    month="2026-08",
                    projected_closing_cash=-155_000_000,
                    cash_reserve_minimum=550_000_000,
                    reserve_gap=705_000_000,
                    net_operating_flow=-460_000_000,
                )
            ],
            max_reserve_gap=705_000_000,
            minimum_liquidity_need=705_000_000,
            funding_need=705_000_000,
        ),
        invoice_classification=InvoiceClassification(
            paid_total=0,
            open_current_total=0,
            overdue_total=0,
            not_issued_total=1_600_000_000,
        ),
        bank_reconciliation_summary=BankReconciliationSummary(
            confirmed_cash_total=45_000_000
        ),
        margin_analysis=MarginAnalysis(
            portfolio_revenue=1_600_000_000,
            portfolio_cost=1_216_000_000,
            portfolio_margin_amount=384_000_000,
            portfolio_margin_pct=0.24,
            committed_revenue=1_600_000_000,
            committed_margin_pct=0.24,
            target_margin_pct=0.28,
            margin_gap=-0.04,
            margin_pressure_flag=True,
            by_contract=[{
                "contract_id": "CON-004",
                "revenue": 3_100_000_000,
                "cost": 2_356_000_000,
                "margin_amount": 744_000_000,
                "margin_pct": 0.24,
                "below_target": True,
            }],
        ),
        missing_data_request=[],
        key_facts={"funding_need": 705_000_000},
        handoff_summary="Finance facts only.",
    )


def test_handoff_schema_rejects_unknown_fields() -> None:
    payload = _finance_pack().model_dump(mode="json")
    payload["invented_metric"] = 123
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FinanceFeaturePack.model_validate(payload)


def test_finance_batch_requires_contract_order() -> None:
    second = _finance_pack().model_copy(
        update={"case_id": "CASE-CON-007", "contract_id": "CON-007"}
    )
    with pytest.raises(ValidationError, match="must match contract_ids in order"):
        FinanceBatchPack(
            contract_ids=["CON-007", "CON-004"],
            packs=[_finance_pack(), second],
        )


def test_contract_json_is_direct_input_and_merge_is_run_local(tmp_path) -> None:
    path = tmp_path / "contract.json"
    path.write_text(
        """{
          "contract_id": "CON-NEW-001",
          "customer_id": "CUS-005",
          "start_date": "2026-08-01",
          "end_date": "2027-02-28",
          "status": "Pending approval",
          "description": "New uploaded contract",
          "contract_value": 1200000000,
          "gross_margin": 0.25,
          "payment_terms": "Performance bond required",
          "requested_amount": 300000000,
          "funding_need_type": "PERFORMANCE_BOND",
          "tenor": "7 months"
        }""",
        encoding="utf-8",
    )
    package = load_contract_package(path)
    assert isinstance(package, ContractUploadPackage)
    assert package.contract_id == "CON-NEW-001"

    base = {
        "contracts": [{"contract_id": "CON-004", "contract_value": 1}],
        "source": "database",
    }
    merged = merge_contract_package(base, package)

    assert [row["contract_id"] for row in merged["contracts"]] == [
        "CON-004",
        "CON-NEW-001",
    ]
    assert merged["source"] == "database+upload"
    assert base == {
        "contracts": [{"contract_id": "CON-004", "contract_value": 1}],
        "source": "database",
    }


def test_finance_scenario_override_is_disabled_before_database_access(monkeypatch) -> None:
    monkeypatch.setenv("FINANCE_SCENARIO", "forbidden-simulation.json")
    with pytest.raises(RuntimeError, match="FINANCE_SCENARIO is disabled"):
        load_all()


def test_bank_precheck_never_falls_back_without_real_api_url() -> None:
    with pytest.raises(RuntimeError, match="Bank API base URL is not configured"):
        _call_api(None, "/precheck", {"contract_id": "CON-004"})


def test_contract_upload_rejects_package_wrapper() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ContractUploadPackage.model_validate(
            {
                "contract": {
                    "contract_id": "CON-NEW-001",
                }
            }
        )


def test_pipeline_scope_has_exactly_two_modes() -> None:
    base = {
        "contracts": [
            {"contract_id": "CON-001"},
            {"contract_id": "CON-002"},
        ],
        "source": "database",
    }
    data, contract_ids, mode = select_pipeline_scope(base)
    assert data is base
    assert contract_ids == ["CON-001", "CON-002"]
    assert mode == "automatic_batch"

    upload = ContractUploadPackage(
        contract_id="CON-UPLOAD-001",
        customer_id="CUS-005",
        start_date="2026-08-01",
        end_date="2027-02-28",
        status="Pending approval",
        description="Uploaded contract",
        contract_value=1_200_000_000,
        gross_margin=0.25,
        payment_terms="Performance bond required",
        requested_amount=300_000_000,
        funding_need_type="PERFORMANCE_BOND",
        tenor="7 months",
    )
    merged, contract_ids, mode = select_pipeline_scope(base, upload)
    assert contract_ids == ["CON-UPLOAD-001"]
    assert mode == "upload"
    assert [item["contract_id"] for item in merged["contracts"]] == [
        "CON-001",
        "CON-002",
        "CON-UPLOAD-001",
    ]


def test_contract_upload_rejects_precomputed_risk_fields() -> None:
    payload = load_contract_package(
        "decision_agent_sample/sample_data/new_contract_upload.json"
    ).model_dump(mode="json")
    payload["transaction_risk_score"] = 32
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ContractUploadPackage.model_validate(payload)


@pytest.mark.parametrize("payment_terms", [
    "Monthly payment",
    "Milestone payment",
    "Payment after acceptance",
    "",
])
def test_ordinary_payment_terms_do_not_imply_a_loan(payment_terms: str) -> None:
    assert infer_funding_need_type(payment_terms) is None


@pytest.mark.parametrize(("payment_terms", "expected"), [
    ("Performance bond required", "PERFORMANCE_BOND"),
    ("Possible LC/trade finance", "TRADE_FINANCE"),
    ("Working capital required", "WORKING_CAPITAL"),
])
def test_only_explicit_financing_terms_are_classified(
    payment_terms: str,
    expected: str,
) -> None:
    assert infer_funding_need_type(payment_terms) == expected


def test_legacy_default_working_capital_is_hidden_from_contract_api() -> None:
    assert _effective_funding_need_type({
        "funding_need_type": "WORKING_CAPITAL",
        "requested_amount": None,
        "finance_details": {"payment_terms": "Milestone payment"},
    }) is None

    assert _effective_funding_need_type({
        "funding_need_type": "WORKING_CAPITAL",
        "requested_amount": 250_000_000,
        "finance_details": {"payment_terms": "Milestone payment"},
    }) == "WORKING_CAPITAL"


def test_rich_finance_analysis_adapts_to_one_contract_case() -> None:
    source = {
        "profile": {"company_id": "OPC-001"},
        "contracts": [
            {
                "contract_id": "CON-004",
                "customer_id": "CUS-005",
                "contract_value": 4_200_000_000,
                "gross_margin": 0.24,
                "payment_terms": "Performance bond required",
            }
        ],
        "customers": [
            {"customer_id": "CUS-005", "customer_type": "Cooperative"}
        ],
        "orders": [{"order_id": "ORD-005", "contract_id": "CON-004"}],
        "invoices": [
            {
                "invoice_id": "INV-005",
                "order_id": "ORD-005",
                "status": "Not issued",
            }
        ],
    }
    handoff = build_finance_handoff("CON-004", _finance_analysis(), source)

    assert handoff.case_id == "CASE-CON-004"
    assert handoff.contract_id == "CON-004"
    assert handoff.funding_need_type == "PERFORMANCE_BOND"
    assert handoff.gross_margin == 0.24
    assert handoff.contract_value == 4_200_000_000
    assert handoff.requested_amount is None
    assert handoff.transaction_risk_score is None
    assert handoff.source_record_ids == ["CON-004", "ORD-005", "INV-005"]
    assert handoff.finance_details["contract_margin"]["margin_pct"] == 0.24
    assert handoff.finance_details["contract_economics"] == {
        "contract_value": 4_200_000_000.0,
        "expected_gross_margin_rate": 0.24,
        "expected_gross_margin_amount": 1_008_000_000.0,
    }
    assert handoff.finance_details["order_allocation"] == {
        "allocated_order_revenue": 3_100_000_000.0,
        "allocated_order_cost": 2_356_000_000.0,
        "allocated_order_margin_amount": 744_000_000.0,
        "allocated_order_margin_rate": 0.24,
        "allocated_order_ratio": pytest.approx(3_100_000_000 / 4_200_000_000),
        "unallocated_contract_value": 1_100_000_000.0,
    }


def test_decision_context_does_not_turn_portfolio_gap_into_contract_need(
    monkeypatch,
) -> None:
    handoff = build_finance_handoff(
        "CON-004",
        _finance_analysis(),
        {
            "profile": {"company_id": "OPC-001"},
            "contracts": [{
                "contract_id": "CON-004",
                "customer_id": "CUS-005",
                "contract_value": 4_200_000_000,
                "gross_margin": 0.24,
                "payment_terms": "Performance bond required",
            }],
            "customers": [],
            "orders": [],
            "invoices": [],
        },
    )
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[handoff],
        portfolio_analysis=_finance_analysis().model_dump(mode="json"),
    )
    risk_batch = RiskBatchPack(
        contract_ids=["CON-004"],
        packs=[RiskPack(
            case_id="CASE-CON-004",
            contract_id="CON-004",
            generated_at=datetime.now(UTC),
            rule_evaluations=[],
            triggered_rule_ids=[],
            human_approval_required=False,
            handoff_summary="No triggered rules.",
        )],
    )
    monkeypatch.setattr(
        context_store,
        "load_decision_inputs",
        lambda _session_id: (finance_batch, risk_batch),
    )

    payload = context_store.decision_input_payload(25)
    case = payload["cases"][0]

    assert payload["portfolio_finance"]["liquidity_brief"]["funding_need"] == 705_000_000
    reconciliation = payload["portfolio_finance"]["bank_reconciliation_summary"]
    assert reconciliation["confirmed_invoice_collections"] == 45_000_000
    assert "confirmed_cash_total" not in reconciliation
    assert case["funding_need"] == {
        "need_type": "PERFORMANCE_BOND",
        "requested_amount": None,
        "tenor": None,
        "basis": "contract.requested_amount",
        "scope": "contract",
        "amount_status": "MISSING",
    }
    assert case["contract_financials"]["contract_value"] == 4_200_000_000
    assert "contract_margin" not in case["finance"]["finance_details"]
    assert "not a contract bond/credit amount" in payload["portfolio_scope_note"]


def test_bank_product_can_match_need_type_before_amount_is_known() -> None:
    candidate = _evaluate_product(
        {"need_type": "PERFORMANCE_BOND", "requested_amount": None},
        {
            "bank_product_id": "BANKPROD-002",
            "bank": "VietinBank",
            "product_name": "Performance bond",
            "need_type": "PERFORMANCE_BOND",
            "minimum_amount": 300_000_000.0,
            "collateral_ratio": 0.2,
            "annual_rate_or_fee": 0.012,
            "automation_level": "Human approval",
        },
    )

    assert candidate is not None
    assert candidate["match_status"] == "NEEDS_AMOUNT"
    assert candidate["precheck_status"] == "MISSING_REQUESTED_AMOUNT"
    assert candidate["minimum_amount"] == 300_000_000
    assert "cannot be checked" in candidate["match_reasons"][1]


def test_decision_guard_rejects_portfolio_need_as_contract_capital() -> None:
    finance = _finance_pack().model_copy(update={"requested_amount": None})
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[finance],
    )
    decision = _decision_batch().model_copy(deep=True)
    decision.decisions[0].capital_need = 705_000_000

    with pytest.raises(ValueError, match="invented contract capital_need"):
        validate_decision_finance_consistency(decision, finance_batch)


def test_decision_guard_accepts_exact_contract_requested_amount() -> None:
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[_finance_pack()],
    )

    validate_decision_finance_consistency(_decision_batch(), finance_batch)


def test_decision_precheck_fields_are_guarded() -> None:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0]["eligible_score"] = 85
    with pytest.raises(ValidationError, match="must be null"):
        DecisionBatchOutput.model_validate(payload)


@pytest.mark.parametrize("legacy_field", ["risk_warnings", "missing_information"])
def test_decision_card_rejects_duplicated_source_fields(legacy_field: str) -> None:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0][legacy_field] = ["Must remain in Finance/Risk packs"]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionBatchOutput.model_validate(payload)


def test_context_store_uses_one_numeric_session_id(monkeypatch) -> None:
    captured: list[tuple[object, object]] = []

    def fake_query(statement, params=None):
        captured.append((statement, params))
        if "nextval" in str(statement):
            return [{"session_id": 73}]
        return [{"session_id": params[0] if "INSERT" in str(statement) else 73}]

    monkeypatch.setattr(context_store, "query_db", fake_query)
    session_id = context_store.allocate_session_id()
    context_store.insert_finance_pack(
        session_id,
        FinanceBatchPack(contract_ids=["CON-004"], packs=[_finance_pack()]),
    )

    assert session_id == 73
    insert_params = captured[1][1]
    assert insert_params[0] == 73
    assert isinstance(insert_params[0], int)
    assert '"contract_id":"CON-004"' in insert_params[1]


def test_pipeline_schema_guard_rejects_legacy_log_id(monkeypatch) -> None:
    monkeypatch.setattr(
        context_store,
        "query_db",
        lambda *_args, **_kwargs: [
            {
                "table_name": "context",
                "column_name": "session_id",
                "data_type": "bigint",
            },
            {
                "table_name": "LogsAgent",
                "column_name": "id",
                "data_type": "character varying",
            },
        ],
    )
    with pytest.raises(RuntimeError, match="Apply supabase/migrations"):
        context_store.validate_pipeline_schema()


def test_application_logging_uses_bigint_and_real_stage_events(monkeypatch) -> None:
    session_id = 91
    event_bus.snapshots[str(session_id)] = {
        "started_at": "2026-07-18T00:00:00Z",
        "updated_at": "2026-07-18T00:01:00Z",
        "events": [
            {"agent": "Finance_Agent", "type": "tool_finished"},
            {"agent": "Risk_Agent", "type": "tool_finished"},
        ],
    }
    calls: list[tuple[object, object]] = []

    def fake_query(statement, params=None):
        calls.append((statement, params))
        return [{"id": session_id}]

    monkeypatch.setattr(writeLogs, "query_db", fake_query)
    result = writeLogs.persist_agent_stage_log(
        session_id,
        "finance",
        _finance_pack(),
    )

    assert result["id"] == session_id
    assert calls[0][1][0] == session_id
    payload = writeLogs.build_agent_log_payload(
        session_id,
        "finance",
        _finance_pack(),
    )
    assert [event["agent"] for event in payload["agent_log"]["events"]] == [
        "Finance_Agent"
    ]


def test_log_writer_rejects_legacy_uuid_run_id() -> None:
    with pytest.raises(ValueError, match="positive bigint"):
        writeLogs.upsert_agent_logs_partial(
            "0c8a8ce5-281e-4c6f-a364-e9cd6dcd33a3",
            financelogs={"ok": True},
        )


def test_decision_guard_rejects_hallucinated_score() -> None:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0].update(
        approval_status=True,
        eligible_score=99,
        precheck_note="Invented",
    )
    batch = DecisionBatchOutput.model_validate(payload)
    state = {
        "approval_requests": [
            {
                "contract_id": "CON-004",
                "status": "executed",
                "result": {
                    "eligible_score": 85.0,
                    "precheck_note": "Actual tool result",
                },
            }
        ]
    }
    with pytest.raises(ValueError, match="do not match"):
        validate_decision_prechecks(batch, state)


@pytest.mark.asyncio
async def test_pending_approvals_fall_back_to_durable_decision_log(
    monkeypatch,
) -> None:
    async def missing_local_state(_run_id: int):
        raise FileNotFoundError

    monkeypatch.setattr(
        approval_service,
        "list_approval_requests",
        missing_local_state,
    )
    monkeypatch.setattr(
        approval_service,
        "fetch_decision_log",
        lambda _run_id: {
            "agent_log": {
                "events": [
                    {
                        "type": "run_review",
                        "data": {
                            "pending_approvals": [
                                {
                                    "approval_id": "approval-19",
                                    "contract_id": "CON-UPLOAD-001",
                                    "tool": "precheck_performance_bond",
                                    "arguments": {
                                        "contract_id": "CON-UPLOAD-001",
                                        "amount": 300_000_000,
                                    },
                                    "status": "pending",
                                }
                            ]
                        },
                    }
                ]
            }
        },
    )

    requests = await approval_service.get_pending_approvals(19)

    assert len(requests) == 1
    assert requests[0]["contract_id"] == "CON-UPLOAD-001"
    assert requests[0]["approval_id"] == "approval-19"


@pytest.mark.asyncio
async def test_missing_local_approval_state_is_rebuilt_for_submission(
    monkeypatch,
) -> None:
    async def missing_local_state(_run_id: int):
        raise FileNotFoundError

    restored: dict[str, object] = {}

    async def capture_restore(run_id: int, snapshot: dict):
        restored.update({"run_id": run_id, "snapshot": snapshot})
        return snapshot

    decision_log = {
        "response": {
            "decisions": [{
                "contract_id": "CON-UPLOAD-001",
                "capital_need": 300_000_000,
            }]
        },
        "agent_log": {
            "events": [{
                "type": "run_review",
                "data": {
                    "pending_approvals": [{
                        "approval_id": "approval-19",
                        "contract_id": "CON-UPLOAD-001",
                        "tool": "precheck_performance_bond",
                        "arguments": {
                            "contract_id": "CON-UPLOAD-001",
                            "amount": 300_000_000,
                        },
                        "status": "pending",
                    }]
                },
            }]
        },
    }
    monkeypatch.setattr(approval_service, "get_approval_state", missing_local_state)
    monkeypatch.setattr(
        approval_service,
        "fetch_decision_log",
        lambda _run_id: decision_log,
    )
    monkeypatch.setattr(
        approval_service,
        "fetch_context_row",
        lambda _run_id: {
            "finance_pack": {"contract_ids": ["CON-UPLOAD-001"]},
            "decision_pack": decision_log["response"],
        },
    )
    monkeypatch.setattr(approval_service, "restore_approval_state", capture_restore)

    state = await approval_service._ensure_approval_state(19)

    assert restored["run_id"] == 19
    assert state["context"]["contract_ids"] == ["CON-UPLOAD-001"]
    assert state["approval_requests"][0]["approval_id"] == "approval-19"
    assert state["decision_result"] == decision_log["response"]
