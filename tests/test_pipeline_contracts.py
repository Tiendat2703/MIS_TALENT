"""Integration-contract tests that do not require OpenAI or Supabase."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import app
from app.Agent import state_store
from app.Agent.bus import AgentEventBus, event_bus
from app.Agent.hooks import AppContext
from app.database import context_store, repository
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
    Severity,
)
from app.schema.pipeline_input import ContractUploadPackage
from app.schema.bank_product import BankProduct
from app.schema.risk_db_models import CreditProfile
from app.service.finance_handoff import (
    build_finance_handoff,
    infer_funding_need_type,
    normalize_contract_lifecycle,
    resolve_funding_term_amount,
    resolve_performance_bond_amount,
)
from app.service import approval as approval_service
from app.service import decision_guard as decision_guard_service
from app.service import pipeline_service
from app.service.credit_profile import (
    map_credit_profiles_to_contracts,
    resolve_contract_funding_need,
)
from app.service.decision_guard import (
    apply_finance_approval_policy,
    apply_authoritative_precheck_state,
    apply_mandatory_risk_policy,
    validate_decision_finance_consistency,
    validate_decision_prechecks,
    validate_decision_risk_policy,
)
from app.service.pipeline_input import (
    load_contract_package,
    merge_contract_package,
    select_pipeline_scope,
)
from app.service.pipeline_service import _effective_funding_need_type
from app.service.precheck_approval import (
    build_precheck_approval_specs,
    ensure_precheck_approval_requests,
)
from app.tools import writeLogs
from app.tools.DecisionAgent.GetBankProduct import serialize_bank_product
from app.tools.DecisionAgent.PrecheckAPI import (
    _call_api,
    _micro_credit_call,
    _performance_bond_call,
    _trade_finance_call,
    _validate_micro_credit_arguments,
    _validate_trade_finance_arguments,
)
from app.tools.FinanceAgent.finance_data import load_all


client = TestClient(app)


@pytest.mark.asyncio
async def test_dashboard_bootstrap_collects_approvals_once_per_run(monkeypatch) -> None:
    contracts = [
        {
            "session_id": 11,
            "contract_id": "CON-001",
            "finance": {"contract_value": 100},
            "risk": {"overall_risk_level": "HIGH"},
            "decision": {"decision_status": "review", "approval_status": False},
        },
        {
            "session_id": 11,
            "contract_id": "CON-002",
            "finance": {"contract_value": 200},
            "risk": {"overall_risk_level": "LOW"},
            "decision": {"decision_status": "approve", "approval_status": True},
        },
        {
            "session_id": 12,
            "contract_id": "CON-003",
            "finance": {"contract_value": 300},
            "risk": None,
            "decision": None,
        },
    ]
    calls: list[int] = []

    async def fake_contracts(**_kwargs):
        return {"contracts": contracts, "count": len(contracts)}

    async def fake_approvals(run_id: int):
        calls.append(run_id)
        if run_id == 12:
            return []
        return [{
            "approval_id": "approval-1",
            "contract_id": "CON-001",
            "tool": "bank_precheck",
            "arguments": {"amount": 100},
        }]

    monkeypatch.setattr(pipeline_service, "list_processed_contracts", fake_contracts)
    monkeypatch.setattr(pipeline_service, "get_pending_approvals", fake_approvals)

    result = await pipeline_service.get_dashboard_data()

    assert sorted(calls) == [11, 12]
    assert result["pending_approvals"] == [{
        "approval_id": "approval-1",
        "contract_id": "CON-001",
        "tool": "bank_precheck",
        "arguments": {"amount": 100},
        "session_id": 11,
    }]
    assert result["metrics"] == {
        "total": 3,
        "awaiting": 2,
        "high_risk": 1,
        "total_value": 600,
    }


@pytest.mark.asyncio
async def test_run_detail_reads_decision_and_risk_in_one_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        pipeline_service,
        "fetch_context_row",
        lambda session_id: {
            "session_id": session_id,
            "decision_pack": {"decisions": [{"contract_id": "CON-001"}]},
            "risk_pack": {"packs": [{"contract_id": "CON-001"}]},
        },
    )

    result = await pipeline_service.get_run_detail(42)

    assert result == {
        "session_id": 42,
        "found": True,
        "decisions": [{"contract_id": "CON-001"}],
        "risk_pack": {"packs": [{"contract_id": "CON-001"}]},
    }


def test_dashboard_summary_preserves_contract_and_portfolio_risk_scopes() -> None:
    summarized = pipeline_service._summarize_context(
        {
            "session_id": 82,
            "finance_pack": {
                "packs": [{
                    "contract_id": "CON-005",
                    "contract_name": "Trade documentation",
                    "finance_details": {"funding_need": {"source": "none"}},
                }],
            },
            "risk_pack": {
                "packs": [{
                    "contract_id": "CON-005",
                    "contract_triggered_rule_ids": [],
                    "portfolio_triggered_rule_ids": ["RR-001", "RR-002"],
                    "highest_contract_triggered_severity": None,
                    "highest_portfolio_triggered_severity": "CRITICAL",
                    "portfolio_transaction_approval_required": True,
                    "rule_evaluations": [
                        {
                            "rule_id": "RR-001",
                            "scope": "CONTRACT",
                            "status": "NOT_APPLICABLE",
                            "severity": "CRITICAL",
                            "required_action": "Review linked transaction",
                            "message": "No contract-linked transaction exists.",
                        },
                        {
                            "rule_id": "RR-001",
                            "scope": "PORTFOLIO",
                            "status": "TRIGGERED",
                            "severity": "CRITICAL",
                            "required_action": "Hold portfolio transaction",
                            "message": "Portfolio anomaly detected.",
                        },
                        {
                            "rule_id": "RR-002",
                            "scope": "PORTFOLIO",
                            "status": "TRIGGERED",
                            "severity": "HIGH",
                            "required_action": "Review working capital",
                            "message": "Portfolio reserve breach detected.",
                        },
                    ],
                    "triggered_rule_ids": ["RR-001", "RR-002"],
                    "alerts": [],
                }],
            },
            "decision_pack": None,
        },
        {},
    )[0]["risk"]

    assert summarized["contract_triggered_rule_ids"] == []
    assert summarized["portfolio_triggered_rule_ids"] == ["RR-001", "RR-002"]
    assert summarized["highest_contract_triggered_severity"] is None
    assert summarized["highest_portfolio_triggered_severity"] == "CRITICAL"
    assert summarized["portfolio_transaction_approval_required"] is True
    assert [rule["scope"] for rule in summarized["triggered_rules"]] == [
        "PORTFOLIO",
        "PORTFOLIO",
    ]
    assert [rule["scope"] for rule in summarized["rule_evaluations"]] == [
        "CONTRACT",
        "PORTFOLIO",
        "PORTFOLIO",
    ]


def test_dashboard_and_detail_http_routes(monkeypatch) -> None:
    async def fake_dashboard(limit: int, offset: int, latest_only: bool):
        return {
            "limit": limit,
            "offset": offset,
            "latest_only": latest_only,
            "contracts": [],
            "pending_approvals": [],
        }

    async def fake_detail(session_id: int):
        return {"session_id": session_id, "found": True}

    monkeypatch.setattr(pipeline_service, "get_dashboard_data", fake_dashboard)
    monkeypatch.setattr(pipeline_service, "get_run_detail", fake_detail)

    dashboard_response = client.get(
        "/dashboard",
        params={"limit": 25, "offset": 5, "latest_only": False},
    )
    detail_response = client.get("/runs/42/detail")

    assert dashboard_response.status_code == 200
    assert dashboard_response.json() == {
        "limit": 25,
        "offset": 5,
        "latest_only": False,
        "contracts": [],
        "pending_approvals": [],
    }
    assert detail_response.status_code == 200
    assert detail_response.json() == {"session_id": 42, "found": True}


def test_database_pool_defaults_to_twenty_connections(monkeypatch) -> None:
    monkeypatch.delenv("DB_POOL_MIN", raising=False)
    monkeypatch.delenv("DB_POOL_MAX", raising=False)

    assert repository._pool_limits() == (1, 20)


def test_database_pool_rejects_invalid_limits(monkeypatch) -> None:
    monkeypatch.setenv("DB_POOL_MIN", "21")
    monkeypatch.setenv("DB_POOL_MAX", "20")

    with pytest.raises(RuntimeError, match="cannot be greater"):
        repository._pool_limits()


@pytest.mark.asyncio
async def test_global_event_subscriber_receives_pipeline_completion(tmp_path) -> None:
    bus = AgentEventBus(log_dir=tmp_path)
    queue = bus.subscribe_all()

    await bus.emit(
        42,
        {
            "type": "run_finished",
            "agent": "Decision_Agent",
            "status": "done",
        },
    )

    event = queue.get_nowait()
    assert event["run_id"] == "42"
    assert event["type"] == "run_finished"
    bus.unsubscribe_all(queue)
    assert bus.global_subscribers == []


@pytest.mark.asyncio
async def test_dashboard_waits_for_validator_terminal_event(
    monkeypatch,
    tmp_path,
) -> None:
    bus = AgentEventBus(log_dir=tmp_path)
    monkeypatch.setattr(pipeline_service, "event_bus", bus)
    stream = pipeline_service.stream_dashboard_events(poll_interval=0.1)

    ready = await anext(stream)
    assert ready["type"] == "dashboard_ready"

    await bus.emit(
        42,
        {
            "type": "decision_ready",
            "agent": "Decision_Agent",
            "status": "running",
        },
    )
    await bus.emit(
        42,
        {
            "type": "run_finished",
            "agent": "Validator_Agent",
            "status": "done",
        },
    )

    event = await anext(stream)
    assert event["type"] == "run_finished"
    assert event["agent"] == "Validator_Agent"
    await stream.aclose()


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


@pytest.mark.asyncio
async def test_failed_approval_can_be_retried(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(state_store, "PENDING_STATE_DIR", tmp_path)
    run_id = 9_001
    context = AppContext(
        document_id="BATCH-9001",
        original_input="{}",
        run_id=run_id,
        contract_id="CON-004",
        contract_ids=["CON-004"],
    )
    await state_store.initialize_approval_state(run_id, context, "{}")
    request = await state_store.register_approval_request(
        run_id,
        "CON-004",
        "precheck_performance_bond",
        {"contract_id": "CON-004", "amount": 800_000_000},
    )
    approval_id = request["approval_id"]

    await state_store.set_approval_decision(run_id, approval_id, True)
    claimed = await state_store.claim_approval_execution(run_id, approval_id)
    assert claimed["claimed"] is True
    await state_store.fail_approval_execution(
        run_id,
        approval_id,
        "RuntimeError: sandbox unavailable",
    )

    retried = await state_store.set_approval_decision(run_id, approval_id, True)

    assert retried["status"] == "approved"
    assert retried["execution_started_at"] is None
    assert retried["executed_at"] is None
    assert retried["result"] is None
    assert retried["error"] is None
    retry_claim = await state_store.claim_approval_execution(run_id, approval_id)
    assert retry_claim["claimed"] is True


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
                review_priority="MEDIUM",
                decision_status="review",
                reasons=["Finance reason", "Risk reason", "Product reason"],
            )
        ],
    )


def _active_decision_batch(
    recommended_option: str = "CONTINUE_WITH_ACTIONS",
) -> DecisionBatchOutput:
    return DecisionBatchOutput.model_validate({
        "decisions": [{
            "contract_id": "CON-004",
            "accept_opportunity": None,
            "recommended_option": recommended_option,
            "protective_condition": "Chỉ tiếp tục sau khi người phụ trách xác nhận.",
            "capital_need": None,
            "risk_level": "medium",
            "review_priority": "MEDIUM",
            "decision_status": "review",
            "reasons": [
                "Tình hình tài chính thực hiện dựa trên dữ liệu hiện có.",
                "Rủi ro và evidence được giữ nguyên từ Risk Pack.",
                "Hành động quản trị cần người có thẩm quyền xác nhận.",
            ],
            "requires_founder_confirmation": True,
            "approval_status": False,
            "is_preliminary": True,
            "contract_status": "ACTIVE",
            "assessment_type": "ONGOING_CONTRACT_REVIEW",
            "required_actions": [{
                "action": "Theo dõi khoản phải thu đang mở.",
                "owner": "Contract Owner",
            }],
            "human_confirmation_points": [
                "Xác nhận phương án tiếp tục thực hiện hợp đồng."
            ],
            "is_final_decision": False,
        }],
    })


def _risk_batch(*triggered_rule_ids: str) -> RiskBatchPack:
    active_rule_ids = [
        rule_id for rule_id in triggered_rule_ids if rule_id != "RR-005"
    ]
    overall = (
        "HIGH"
        if any(rule_id != "RR-003" for rule_id in active_rule_ids)
        else ("MEDIUM" if active_rule_ids else None)
    )
    return RiskBatchPack.model_validate(
        {
            "contract_ids": ["CON-004"],
            "packs": [
                {
                    "case_id": "CASE-CON-004",
                    "contract_id": "CON-004",
                    "generated_at": datetime.now(UTC),
                    "overall_risk_level": overall,
                    "review_priority": overall or "LOW",
                    "rule_evaluations": [
                        {
                            "rule_id": rule_id,
                            "status": (
                                "RULE_INACTIVE"
                                if rule_id == "RR-005"
                                else "TRIGGERED"
                            ),
                            "owner_agent": "Risk & Compliance Agent",
                            "severity": (
                                "MEDIUM" if rule_id == "RR-003" else "HIGH"
                            ),
                            "required_action": "Review before acceptance",
                            "message": "Rule triggered for this contract.",
                        }
                        for rule_id in triggered_rule_ids
                    ],
                    "triggered_rule_ids": active_rule_ids,
                    "required_actions": ["Review before acceptance"],
                    "human_approval_required": bool(active_rule_ids),
                    "handoff_summary": "Risk policy test pack.",
                    "decision_made_by_risk_agent": False,
                }
            ],
        }
    )


def _temporary_risk_rejection(*rule_ids: str) -> DecisionBatchOutput:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0].update(
        {
            "accept_opportunity": False,
            "recommended_option": "TEMPORARY_REJECT_RISK",
            "decision_status": "reject",
            "protective_condition": (
                f"Khắc phục các rule {', '.join(rule_ids)} trước khi chạy lại hồ sơ."
            ),
            "reasons": [
                "Finance reason",
                f"Tạm từ chối do các rule {', '.join(rule_ids)}.",
                "Product reason",
            ],
        }
    )
    return DecisionBatchOutput.model_validate(payload)


def test_rr003_requires_temporary_risk_rejection() -> None:
    with pytest.raises(ValueError, match="must be temporarily rejected"):
        validate_decision_risk_policy(_decision_batch(), _risk_batch("RR-003"))

    validate_decision_risk_policy(
        _temporary_risk_rejection("RR-003"),
        _risk_batch("RR-003"),
    )


def test_approval_continuation_cannot_override_rr003_rejection() -> None:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0].update(
        approval_status=True,
        eligible_score=85,
        precheck_note="Hồ sơ đủ điều kiện sơ bộ.",
        accept_opportunity=True,
        recommended_option="APPROVE_WITH_CONDITION",
        decision_status="approve",
    )
    continuation = DecisionBatchOutput.model_validate(payload)

    corrected = apply_mandatory_risk_policy(
        continuation,
        _risk_batch("RR-003"),
        contract_id="CON-004",
    )

    decision = corrected.decisions[0]
    assert decision.accept_opportunity is False
    assert decision.recommended_option.value == "TEMPORARY_REJECT_RISK"
    assert decision.decision_status.value == "reject"
    assert decision.external_api_submission_approval_status == "EXECUTED"
    assert decision.eligibility_score == 85
    assert "rr-003" in " ".join([
        decision.protective_condition,
        *decision.reasons,
    ]).casefold()
    validate_decision_risk_policy(corrected, _risk_batch("RR-003"))


def test_large_amount_alone_does_not_force_temporary_rejection() -> None:
    risk_batch = _risk_batch("RR-005")
    corrected = apply_mandatory_risk_policy(_decision_batch(), risk_batch)
    validate_decision_risk_policy(corrected, risk_batch)
    assert corrected.decisions[0].recommended_option.value == "APPROVE_WITH_CONDITION"


def test_large_amount_with_another_nonblocking_risk_does_not_force_rejection() -> None:
    risk_batch = _risk_batch("RR-002", "RR-005")
    decision = apply_mandatory_risk_policy(_decision_batch(), risk_batch)

    validate_decision_risk_policy(decision, risk_batch)
    assert decision.decisions[0].recommended_option.value == "APPROVE_WITH_CONDITION"


def _incomplete_risk_batch() -> RiskBatchPack:
    return RiskBatchPack.model_validate({
        "contract_ids": ["CON-004"],
        "packs": [{
            "case_id": "CASE-CON-004",
            "contract_id": "CON-004",
            "generated_at": datetime.now(UTC),
            "risk_assessment_status": "INCOMPLETE",
            "overall_risk_level": None,
            "review_priority": "HIGH",
            "rule_evaluations": [{
                "rule_id": "RR-001",
                "status": "INSUFFICIENT_EVIDENCE",
                "severity": "CRITICAL",
                "missing_fields": ["related_transaction_risk_score"],
                "message": "No linked 08_BANK_TXN score.",
            }],
            "triggered_rule_ids": [],
            "manual_evidence_review_required": True,
            "triggered_rule_approval_required": False,
            "handoff_summary": "Risk assessment INCOMPLETE.",
        }],
    })


def test_incomplete_active_risk_stays_null_and_blocks_bank_precheck() -> None:
    risk_batch = _incomplete_risk_batch()
    corrected = apply_mandatory_risk_policy(_active_decision_batch(), risk_batch)
    decision = corrected.decisions[0]

    assert decision.recommended_option.value == "NEED_MORE_DATA"
    assert decision.risk_assessment_status == "INCOMPLETE"
    assert decision.risk_level is None
    assert decision.review_priority == Severity.HIGH
    assert decision.human_confirmation_status == "PENDING"
    assert decision.external_api_submission_approval_status == "NOT_REQUESTED"
    assert decision.bank_precheck_status == "NOT_ELIGIBLE_TO_RUN"
    assert decision.eligibility_score is None
    validate_decision_risk_policy(corrected, risk_batch)
    assert build_precheck_approval_specs(
        corrected,
        FinanceBatchPack(contract_ids=["CON-004"], packs=[_finance_pack()]),
        {},
    ) == []


def test_incomplete_nonactive_risk_still_creates_precheck_request() -> None:
    corrected = apply_mandatory_risk_policy(
        _decision_batch(),
        _incomplete_risk_batch(),
    )

    assert corrected.decisions[0].recommended_option.value == "REJECT_MISSING_EVIDENCE"
    assert build_precheck_approval_specs(
        corrected,
        FinanceBatchPack(contract_ids=["CON-004"], packs=[_finance_pack()]),
        {},
    ) == [{
        "contract_id": "CON-004",
        "tool": "precheck_performance_bond",
        "arguments": {
            "contract_id": "CON-004",
            "amount": 420_000_000.0,
        },
    }]


def test_schema_allows_nonactive_incomplete_risk_pending_precheck() -> None:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0].update({
        "accept_opportunity": True,
        "contract_status": "PENDING_EXPANSION",
        "assessment_type": "NEW_CONTRACT_REVIEW",
        "funding_need_type": "PERFORMANCE_BOND",
        "selected_bank_product_id": "BANKPROD-002",
        "selected_bank_product_name": "Performance bond",
        "risk_assessment_status": "INCOMPLETE",
        "risk_level": None,
        "review_priority": "HIGH",
        "external_api_submission_approval_status": "PENDING",
        "bank_precheck_status": "ELIGIBLE_AWAITING_APPROVAL",
        "eligibility_score": None,
        "precheck_note": None,
    })

    decision = DecisionBatchOutput.model_validate(payload).decisions[0]

    assert decision.external_api_submission_approval_status == "PENDING"
    assert decision.bank_precheck_status == "ELIGIBLE_AWAITING_APPROVAL"


def test_schema_allows_executed_precheck_while_nonactive_risk_is_incomplete() -> None:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0].update({
        "contract_status": "PENDING_EXPANSION",
        "assessment_type": "NEW_CONTRACT_REVIEW",
        "risk_assessment_status": "INCOMPLETE",
        "risk_level": None,
        "review_priority": "HIGH",
        "external_api_submission_approval_status": "EXECUTED",
        "bank_precheck_status": "COMPLETED",
        "eligibility_score": 82,
        "precheck_note": "Bank precheck completed after human approval.",
    })

    decision = DecisionBatchOutput.model_validate(payload).decisions[0]

    assert decision.eligibility_score == 82
    assert decision.precheck_note == "Bank precheck completed after human approval."


def test_schema_still_blocks_incomplete_active_risk_precheck() -> None:
    payload = _active_decision_batch().model_dump(mode="json")
    payload["decisions"][0].update({
        "risk_assessment_status": "INCOMPLETE",
        "risk_level": None,
        "review_priority": "HIGH",
        "external_api_submission_approval_status": "PENDING",
        "bank_precheck_status": "ELIGIBLE_AWAITING_APPROVAL",
    })

    with pytest.raises(
        ValidationError,
        match="Incomplete ACTIVE risk cannot request external API approval",
    ):
        DecisionBatchOutput.model_validate(payload)


def test_continuation_restores_executed_state_after_incomplete_risk_policy() -> None:
    approval_id = "approval-CON-004"
    pending_state = {
        "approval_requests": [{
            "approval_id": approval_id,
            "contract_id": "CON-004",
            "status": "pending",
            "result": None,
        }],
    }
    batch_before = apply_authoritative_precheck_state(
        apply_mandatory_risk_policy(
            _decision_batch(),
            _incomplete_risk_batch(),
        ),
        pending_state,
    )
    executed_result = {
        "eligible_score": 85.0,
        "precheck_note": "Hồ sơ đầy đủ và đủ điều kiện sơ bộ.",
    }
    executed_request = {
        "approval_id": approval_id,
        "contract_id": "CON-004",
        "status": "executed",
        "result": executed_result,
    }
    executed_state = {"approval_requests": [executed_request]}

    reconciled = approval_service._reconcile_continuation_output(
        _decision_batch(),
        risk_batch=_incomplete_risk_batch(),
        contract_id="CON-004",
        approval_state=executed_state,
    )
    decision = reconciled.decisions[0]

    assert decision.recommended_option.value == "REJECT_MISSING_EVIDENCE"
    assert decision.risk_assessment_status == "INCOMPLETE"
    assert decision.external_api_submission_approval_status == "EXECUTED"
    assert decision.bank_precheck_status == "COMPLETED"
    assert decision.eligibility_score == 85.0
    assert decision.precheck_note == "Hồ sơ đầy đủ và đủ điều kiện sơ bộ."
    approval_service._guard_continuation_result(
        batch_before=batch_before.model_dump(mode="json"),
        batch_after=reconciled.model_dump(mode="json"),
        contract_id="CON-004",
        approved=True,
        approval_request=executed_request,
        request_ids_before={approval_id},
        request_ids_after={approval_id},
    )


@pytest.mark.asyncio
async def test_incomplete_nonactive_risk_registers_pending_request(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(state_store, "PENDING_STATE_DIR", tmp_path)
    run_id = 9_077
    context = AppContext(
        document_id="BATCH-9077",
        original_input="{}",
        run_id=run_id,
        contract_id="CON-004",
        contract_ids=["CON-004"],
    )
    await state_store.initialize_approval_state(run_id, context, "{}")

    async def ignore_event(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        "app.service.precheck_approval.event_bus.emit",
        ignore_event,
    )
    corrected = apply_mandatory_risk_policy(
        _decision_batch(),
        _incomplete_risk_batch(),
    )

    requests = await ensure_precheck_approval_requests(
        run_id,
        corrected,
        FinanceBatchPack(contract_ids=["CON-004"], packs=[_finance_pack()]),
        {},
    )

    assert len(requests) == 1
    assert requests[0]["status"] == "pending"
    assert requests[0]["tool"] == "precheck_performance_bond"
    assert requests[0]["arguments"] == {
        "contract_id": "CON-004",
        "amount": 420_000_000.0,
    }


def test_nonactive_temporary_risk_rejection_still_creates_precheck_request() -> None:
    decision = _temporary_risk_rejection("RR-003")
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[_finance_pack()],
    )

    assert build_precheck_approval_specs(decision, finance_batch, {}) == [{
        "contract_id": "CON-004",
        "tool": "precheck_performance_bond",
        "arguments": {
            "contract_id": "CON-004",
            "amount": 420_000_000.0,
        },
    }]


def test_pending_precheck_preserves_preliminary_nonactive_risk_rejection() -> None:
    decision = _temporary_risk_rejection("RR-003")
    approval_state = {
        "approval_requests": [{
            "contract_id": "CON-004",
            "status": "pending",
            "result": None,
        }],
    }

    projected = apply_authoritative_precheck_state(decision, approval_state)
    card = projected.decisions[0]

    assert card.recommended_option.value == "TEMPORARY_REJECT_RISK"
    assert card.decision_status.value == "reject"
    assert card.external_api_submission_approval_status == "PENDING"
    assert card.bank_precheck_status == "ELIGIBLE_AWAITING_APPROVAL"
    validate_decision_prechecks(projected, approval_state)


def test_active_contract_rejects_new_opportunity_decision_options() -> None:
    payload = _active_decision_batch().model_dump(mode="json")
    payload["decisions"][0]["recommended_option"] = "APPROVE_WITH_CONDITION"

    with pytest.raises(
        ValidationError,
        match="ongoing-contract recommendation",
    ):
        DecisionBatchOutput.model_validate(payload)


def test_active_contract_recommendation_is_always_human_review() -> None:
    payload = _active_decision_batch().model_dump(mode="json")
    payload["decisions"][0]["decision_status"] = "approve"

    with pytest.raises(ValidationError, match="decision_status=review"):
        DecisionBatchOutput.model_validate(payload)


def test_active_rr003_preserves_management_option_and_adds_action() -> None:
    corrected = apply_mandatory_risk_policy(
        _active_decision_batch(),
        _risk_batch("RR-003"),
    )

    decision = corrected.decisions[0]
    assert decision.recommended_option.value == "CONTINUE_WITH_ACTIONS"
    assert decision.decision_status.value == "review"
    assert decision.accept_opportunity is None
    assert decision.required_actions
    assert any("rr-003" in item.action.casefold() for item in decision.required_actions)
    assert decision.human_confirmation_points
    assert "rr-003" in " ".join([
        decision.protective_condition,
        *decision.reasons,
    ]).casefold()
    validate_decision_risk_policy(corrected, _risk_batch("RR-003"))


def test_decision_keeps_three_approval_flows_separate() -> None:
    finance = _finance_pack().model_copy(update={
        "contract_value": 980_000_000,
        "finance_details": {
            "contract_finance": {
                "scope": "contract",
                "contract_economics": {"contract_value": 980_000_000},
            },
            "governance_context": {
                "scope": "company_policy",
                "contract_final_action_approval_threshold": 300_000_000,
            },
        },
    })
    risk_payload = _risk_batch("RR-001").model_dump(mode="json")
    risk_payload["packs"][0].update({
        "contract_triggered_rule_ids": [],
        "portfolio_triggered_rule_ids": ["RR-001"],
        "portfolio_transaction_approval_required": True,
        "portfolio_transaction_approval_object_ids": [
            "TOK-TXN-006",
            "TOK-TXN-007",
        ],
    })
    risk_batch = RiskBatchPack.model_validate(risk_payload)

    decision_batch = apply_finance_approval_policy(
        _active_decision_batch(),
        FinanceBatchPack(contract_ids=["CON-004"], packs=[finance]),
    )
    decision = apply_mandatory_risk_policy(
        decision_batch,
        risk_batch,
    ).decisions[0]

    assert decision.portfolio_transaction_approval.model_dump() == {
        "required": True,
        "source": "RR-001",
        "status": "NOT_REQUESTED",
        "object_ids": ["TOK-TXN-006", "TOK-TXN-007"],
    }
    assert decision.contract_final_action_approval.model_dump() == {
        "required": True,
        "source": "CONTRACT_VALUE_POLICY",
        "status": "NOT_REQUESTED",
        "object_ids": ["CON-004"],
    }
    assert decision.external_api_submission_approval.model_dump() == {
        "required": False,
        "source": None,
        "status": "NOT_REQUIRED",
        "object_ids": [],
    }


def test_active_review_with_concrete_funding_need_creates_pending_precheck_spec() -> None:
    finance = _finance_pack().model_copy(update={
        "finance_details": {
            "contract_status": "Active",
            "contract_lifecycle": "ACTIVE",
            "assessment_type": "ONGOING_CONTRACT_REVIEW",
            "payment_terms": "Performance bond 10%",
            "funding_need": {"requested_amount_source": "contract"},
        },
    })
    decision_payload = _active_decision_batch().model_dump(mode="json")
    decision_payload["decisions"][0].update({
        "capital_need": 420_000_000,
        "funding_need_type": "PERFORMANCE_BOND",
        "selected_bank_product_id": "BANKPROD-002",
        "selected_bank_product_name": "Performance bond",
    })

    assert build_precheck_approval_specs(
        DecisionBatchOutput.model_validate(decision_payload),
        FinanceBatchPack(contract_ids=["CON-004"], packs=[finance]),
        {},
    ) == [{
        "contract_id": "CON-004",
        "tool": "precheck_performance_bond",
        "arguments": {
            "contract_id": "CON-004",
            "amount": 420_000_000.0,
        },
    }]


def test_active_hold_does_not_create_bank_precheck_request() -> None:
    assert build_precheck_approval_specs(
        _active_decision_batch("RECOMMEND_HOLD"),
        FinanceBatchPack(contract_ids=["CON-004"], packs=[_finance_pack()]),
        {},
    ) == []


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
          "requested_amount": null,
          "funding_need_type": null,
          "tenor": null
        }""",
        encoding="utf-8",
    )
    package = load_contract_package(path)
    assert isinstance(package, ContractUploadPackage)
    assert package.contract_id == "CON-NEW-001"
    assert package.requested_amount is None
    assert package.funding_need_type is None
    assert package.tenor is None

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


def test_real_bank_api_helper_requires_base_url() -> None:
    with pytest.raises(RuntimeError, match="Bank API base URL is not configured"):
        _call_api(None, "/precheck", {"contract_id": "CON-004"})


def test_contract_upload_defaults_and_enforces_pending_status() -> None:
    payload = load_contract_package(
        "decision_agent_sample/sample_data/new_contract_upload.json"
    ).model_dump(mode="json")

    payload.pop("status")
    assert ContractUploadPackage.model_validate(payload).status == "Pending approval"

    payload["status"] = "Active"
    assert ContractUploadPackage.model_validate(payload).status == "Pending approval"


def test_contract_validate_endpoint_echoes_normalized_form_payload() -> None:
    payload = load_contract_package(
        "decision_agent_sample/sample_data/new_contract_upload.json"
    ).model_dump(mode="json")
    payload["status"] = "Active"

    response = client.post("/contracts/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] is True
    assert body["contract"]["contract_id"] == payload["contract_id"]
    assert body["contract"]["status"] == "Pending approval"


def test_contract_upload_rejects_package_wrapper() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ContractUploadPackage.model_validate(
            {
                "contract": {
                    "contract_id": "CON-NEW-001",
                }
            }
        )


def test_pipeline_scope_supports_batch_upload_and_existing_contract() -> None:
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
        requested_amount=None,
        funding_need_type=None,
        tenor=None,
    )
    merged, contract_ids, mode = select_pipeline_scope(base, upload)
    assert contract_ids == ["CON-UPLOAD-001"]
    assert mode == "upload"
    assert [item["contract_id"] for item in merged["contracts"]] == [
        "CON-001",
        "CON-002",
        "CON-UPLOAD-001",
    ]

    selected, contract_ids, mode = select_pipeline_scope(
        base,
        existing_contract_id="CON-002",
    )
    assert selected is base
    assert contract_ids == ["CON-002"]
    assert mode == "existing_contract"

    with pytest.raises(LookupError, match="CON-404"):
        select_pipeline_scope(base, existing_contract_id="CON-404")

    with pytest.raises(ValueError, match="either"):
        select_pipeline_scope(base, upload, "CON-001")


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


@pytest.mark.parametrize(
    ("payment_terms", "expected_amount", "expected_source", "expected_percentage"),
    [
        (
            "PERORMANCE BOND",
            120_000_000,
            "payment_terms_full_contract_fallback",
            100.0,
        ),
        (
            "PERFORMANCE_BOND",
            120_000_000,
            "payment_terms_full_contract_fallback",
            100.0,
        ),
        (
            "Performance bond 10%",
            12_000_000,
            "payment_terms_percentage",
            10.0,
        ),
        (
            "10% performance bond",
            12_000_000,
            "payment_terms_percentage",
            10.0,
        ),
        (
            "Performance bond amount 20,000,000 VND",
            20_000_000,
            "payment_terms_explicit_amount",
            None,
        ),
    ],
)
def test_performance_bond_amount_follows_contract_term(
    payment_terms: str,
    expected_amount: float,
    expected_source: str,
    expected_percentage: float | None,
) -> None:
    result = resolve_performance_bond_amount(payment_terms, 120_000_000)

    assert result is not None
    assert result["amount"] == expected_amount
    assert result["source"] == expected_source
    assert result["percentage"] == expected_percentage


def test_payment_schedule_percentage_is_not_used_as_bond_percentage() -> None:
    result = resolve_performance_bond_amount(
        "Performance bond required; 30% advance, 50% delivery, 20% acceptance",
        120_000_000,
    )

    assert result is not None
    assert result["amount"] == 120_000_000
    assert result["source"] == "payment_terms_full_contract_fallback"


@pytest.mark.parametrize(
    ("payment_terms", "expected_amount", "expected_percentage"),
    [
        ("WORKING CAPITAL", 1_200_000_000, 100.0),
        ("WORKING CAPITAL 25%", 300_000_000, 25.0),
        ("25% vốn lưu động", 300_000_000, 25.0),
        ("TRADE FINANCE", 1_200_000_000, 100.0),
    ],
)
def test_all_financing_terms_use_contract_percentage_not_default_schedule(
    payment_terms: str,
    expected_amount: float,
    expected_percentage: float,
) -> None:
    result = resolve_funding_term_amount(payment_terms, 1_200_000_000)

    assert result is not None
    assert result["amount"] == expected_amount
    assert result["percentage"] == expected_percentage


def test_non_bond_payment_terms_do_not_use_full_contract_fallback() -> None:
    assert resolve_performance_bond_amount(
        "Monthly payments",
        120_000_000,
    ) is None


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
    assert handoff.funding_need_type is None
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


def test_active_finance_review_uses_only_contract_scoped_execution_facts() -> None:
    analysis = _finance_analysis().model_copy(update={
        "invoice_classification": InvoiceClassification(
            paid_total=45_000_000,
            open_current_total=80_000_000,
            overdue_total=120_000_000,
            not_issued_total=300_000_000,
            buckets={
                "paid": [{"invoice_id": "INV-PAID", "amount": 45_000_000}],
                "open_current": [{"invoice_id": "INV-OPEN", "amount": 80_000_000}],
                "overdue": [{
                    "invoice_id": "INV-LATE",
                    "amount": 120_000_000,
                    "days_overdue": 12,
                }],
                "not_issued": [{
                    "invoice_id": "INV-DRAFT",
                    "amount": 300_000_000,
                }],
            },
        ),
        "bank_reconciliation_summary": BankReconciliationSummary(
            confirmed_cash_total=45_000_000,
            matched=[{
                "invoice_id": "INV-PAID",
                "txn_id": "TXN-PAID",
                "amount": 45_000_000,
            }],
        ),
    })
    source = {
        "profile": {"company_id": "OPC-001"},
        "contracts": [{
            "contract_id": "CON-004",
            "customer_id": "CUS-005",
            "contract_value": 4_200_000_000,
            "gross_margin": 0.25,
            "payment_terms": "Monthly payment",
            "status": "Active",
        }],
        "customers": [{"customer_id": "CUS-005"}],
        "orders": [{"order_id": "ORD-005", "contract_id": "CON-004"}],
        "invoices": [
            {"invoice_id": invoice_id, "order_id": "ORD-005", "status": status}
            for invoice_id, status in (
                ("INV-PAID", "Paid"),
                ("INV-OPEN", "Open"),
                ("INV-LATE", "Open"),
                ("INV-DRAFT", "Not issued"),
            )
        ],
    }

    handoff = build_finance_handoff("CON-004", analysis, source)
    details = handoff.finance_details
    execution = details["execution_finance"]

    assert normalize_contract_lifecycle("Active") == "ACTIVE"
    assert details["assessment_type"] == "ONGOING_CONTRACT_REVIEW"
    assert details["financial_assessment_type"] == "ONGOING_CONTRACT_REVIEW"
    assert details["finance_status"] == "ACTION_REQUIRED"
    assert handoff.projected_closing_cash is None
    assert handoff.cash_reserve_minimum is None
    assert details["portfolio_context"] == {
        "scope": "portfolio",
        "lowest_liquidity_month": "2026-08",
        "projected_closing_cash": -155_000_000.0,
        "cash_reserve_minimum": 550_000_000.0,
        "reserve_gap": 705_000_000.0,
        "funding_need": 705_000_000.0,
        "months_below_reserve": [],
        "negative_cash_months": [],
        "maximum_reserve_gap": 705_000_000.0,
    }
    assert details["contract_finance"]["scope"] == "contract"
    assert "portfolio_context" not in details["contract_finance"]
    assert details["contract_finance"]["execution_finance"] == execution
    assert execution["invoice_totals"] == {
        "invoice_count": 4,
        "paid_invoice_total": 45_000_000.0,
        "open_current_invoice_total": 80_000_000.0,
        "overdue_invoice_total": 120_000_000.0,
        "open_receivable_total": 200_000_000.0,
        "not_issued_invoice_total": 300_000_000.0,
        "max_days_overdue": 12,
        "confirmed_collection_total": 45_000_000.0,
        "matched_invoice_ids": ["INV-PAID"],
        "matched_transaction_ids": ["TXN-PAID"],
    }
    assert "TXN-PAID" in handoff.source_record_ids
    assert execution["finance_status"] == "ACTION_REQUIRED"
    assert execution["invoiced_amount"] == 245_000_000
    assert execution["collected_amount"] == 45_000_000
    assert execution["open_receivable"] == 200_000_000
    assert execution["overdue_receivable"] == 120_000_000
    assert execution["remaining_estimated_cost"] is None
    assert execution["current_margin_pct"] is None
    assert execution["projected_funding_need"] is None
    assert execution["unavailable_metrics"] == [
        "actual_margin_rate",
        "remaining_estimated_cost",
    ]


def test_active_finance_review_reflects_latest_cashflow_snapshot() -> None:
    source = {
        "profile": {"company_id": "OPC-001"},
        "contracts": [{
            "contract_id": "CON-004",
            "contract_value": 4_200_000_000,
            "gross_margin": 0.24,
            "payment_terms": "Monthly payment",
            "status": "Active",
        }],
        "customers": [],
        "orders": [],
        "invoices": [],
    }
    first = build_finance_handoff("CON-004", _finance_analysis(), source)
    updated_analysis = _finance_analysis().model_copy(update={
        "liquidity_brief": LiquidityBrief(
            by_month=[LiquidityMonth(
                month="2026-08",
                projected_closing_cash=125_000_000,
                cash_reserve_minimum=550_000_000,
                reserve_gap=425_000_000,
                net_operating_flow=-180_000_000,
            )],
            max_reserve_gap=425_000_000,
            minimum_liquidity_need=425_000_000,
            funding_need=425_000_000,
        ),
    })
    second = build_finance_handoff("CON-004", updated_analysis, source)

    assert first.finance_details["portfolio_context"]["projected_closing_cash"] == (
        -155_000_000
    )
    assert second.finance_details["portfolio_context"]["projected_closing_cash"] == (
        125_000_000
    )
    assert second.finance_details["portfolio_context"]["funding_need"] == 425_000_000


def test_db_performance_bond_without_amount_does_not_fallback_to_contract_value(
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
                "status": "Active",
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
    monkeypatch.setattr(
        context_store,
        "load_contract_credit_profiles",
        lambda _contract_ids: {},
    )

    payload = context_store.decision_input_payload(25)
    case = payload["cases"][0]

    assert case["contract_lifecycle"] == "ACTIVE"
    assert case["assessment_type"] == "ONGOING_CONTRACT_REVIEW"
    assert case["execution_finance"]["scope"] == "contract"
    assert case["portfolio_context"]["scope"] == "portfolio"
    assert any(
        "must stay missing" in rule
        for rule in case["scope_rules"]
    )
    assert payload["portfolio_finance"]["liquidity_brief"]["funding_need"] == 705_000_000
    reconciliation = payload["portfolio_finance"]["bank_reconciliation_summary"]
    assert reconciliation["confirmed_invoice_collections"] == 45_000_000
    assert "confirmed_cash_total" not in reconciliation
    assert handoff.requested_amount is None
    assert handoff.finance_details["funding_need"] == {
        "type": None,
        "source": "decision_required",
        "requested_amount_source": "missing",
        "requested_amount_status": "MISSING",
        "requested_amount_formula": None,
        "requested_amount_percentage": None,
        "requested_amount_term": None,
        "performance_bond_percentage": None,
    }
    assert case["funding_need"] is None
    assert case["product_search"] == {
        "requested_amount": None,
        "payment_terms": "Performance bond required",
        "tenor": None,
    }
    assert case["credit_profile"] is None
    assert case["contract_financials"]["contract_value"] == 4_200_000_000
    assert "contract_margin" not in case["finance"]["finance_details"]
    assert "not a contract bond/credit amount" in payload["portfolio_scope_note"]


def test_db_performance_bond_keeps_explicit_percentage() -> None:
    source = {
        "profile": {"company_id": "OPC-001"},
        "contracts": [{
            "contract_id": "CON-004",
            "customer_id": "CUS-005",
            "contract_value": 4_200_000_000,
            "gross_margin": 0.24,
            "payment_terms": "Performance bond 10%",
        }],
        "customers": [],
        "orders": [],
        "invoices": [],
        "source": "database",
    }

    handoff = build_finance_handoff("CON-004", _finance_analysis(), source)

    assert handoff.requested_amount == 420_000_000
    assert handoff.finance_details["funding_need"]["requested_amount_source"] == (
        "payment_terms_percentage"
    )
    assert handoff.finance_details["funding_need"]["performance_bond_percentage"] == 10.0


def test_active_db_working_capital_without_amount_does_not_use_full_value() -> None:
    handoff = build_finance_handoff(
        "CON-004",
        _finance_analysis(),
        {
            "profile": {"company_id": "OPC-001"},
            "contracts": [{
                "contract_id": "CON-004",
                "contract_value": 4_200_000_000,
                "payment_terms": "Working capital required",
                "status": "Active",
            }],
            "customers": [],
            "orders": [],
            "invoices": [],
            "source": "database",
        },
    )

    assert handoff.requested_amount is None
    assert handoff.finance_details["execution_finance"]["projected_funding_need"] is None


def test_credit_profile_maps_only_an_explicit_contract_reference() -> None:
    profiles = [
        CreditProfile(
            credit_case_id="CR-001",
            company_id="OPC-001",
            request_type="Working capital line",
            requested_amount=950_000_000,
            collateral_or_basis="Open invoices + founder guarantee",
        ),
        CreditProfile(
            credit_case_id="CR-002",
            company_id="OPC-001",
            request_type="Performance bond",
            requested_amount=420_000_000,
            collateral_or_basis="Contract CON-004",
        ),
    ]

    matches = map_credit_profiles_to_contracts(
        profiles,
        ["CON-001", "CON-004"],
    )

    assert list(matches) == ["CON-004"]
    assert matches["CON-004"].credit_case_id == "CR-002"


def test_credit_profile_amount_precedes_contract_funding_need() -> None:
    profile = CreditProfile(
        credit_case_id="CR-002",
        company_id="OPC-001",
        request_type="Performance bond",
        requested_amount=420_000_000,
        tenor="Until contract acceptance",
        collateral_or_basis="Contract CON-004",
    )
    finance = _finance_pack().model_copy(update={"requested_amount": 300_000_000})

    resolved = resolve_contract_funding_need(finance, profile)

    assert resolved == {
        "need_type": "PERFORMANCE_BOND",
        "requested_amount": 420_000_000.0,
        "tenor": "Until contract acceptance",
        "basis": "credit_profile.requested_amount",
        "scope": "contract",
        "source": "credit_profile",
        "credit_case_id": "CR-002",
        "amount_status": "PROVIDED",
    }


def test_new_contract_without_credit_profile_uses_its_own_funding_need() -> None:
    finance = _finance_pack().model_copy(
        update={
            "contract_id": "CON-UPLOAD-001",
            "case_id": "CASE-CON-UPLOAD-001",
            "requested_amount": 300_000_000,
        }
    )

    resolved = resolve_contract_funding_need(finance, None)

    assert resolved is not None
    assert resolved["requested_amount"] == 300_000_000
    assert resolved["source"] == "contract_funding_need"
    assert resolved["credit_case_id"] is None


def test_finance_uses_full_contract_for_bond_without_its_own_rate() -> None:
    package = ContractUploadPackage(
        contract_id="CON-UPLOAD-001",
        customer_id="CUS-005",
        start_date="2026-08-01",
        end_date="2027-02-28",
        description="Uploaded contract",
        contract_value=1_200_000_000,
        gross_margin=0.25,
        payment_terms=(
            "Performance bond required; 30% advance, 50% delivery, "
            "20% acceptance"
        ),
        requested_amount=None,
        funding_need_type=None,
        tenor=None,
    )
    source = merge_contract_package(
        {
            "profile": {"company_id": "OPC-001"},
            "contracts": [],
            "customers": [],
            "orders": [],
            "invoices": [],
            "source": "database",
        },
        package,
    )

    finance = build_finance_handoff(
        package.contract_id,
        _finance_analysis(),
        source,
    )

    assert finance.requested_amount == 1_200_000_000
    assert finance.funding_need_type is None
    assert finance.tenor == "2026-08-01 to 2027-02-28"
    assert finance.cash_impact is not None
    assert finance.cash_impact["peak_contract_cash_deficit"] == 315_000_000
    assert finance.cash_impact["requested_financing_amount"] == 1_200_000_000
    assert finance.finance_details["funding_need"] == {
        "type": None,
        "source": "decision_required",
        "requested_amount_source": "payment_terms_full_contract_fallback",
        "requested_amount_status": "ESTIMATED",
        "requested_amount_formula": "contract_value × 100%",
        "requested_amount_percentage": 100.0,
        "requested_amount_term": "performance_bond",
        "performance_bond_percentage": 100.0,
    }

    resolved = resolve_contract_funding_need(finance, None)
    assert resolved is not None
    assert resolved["requested_amount"] == 1_200_000_000
    assert resolved["need_type"] is None
    assert resolved["source"] == "finance_inference"
    assert resolved["amount_status"] == "ESTIMATED"


def test_finance_uses_full_contract_for_working_capital_without_rate() -> None:
    package = ContractUploadPackage(
        contract_id="CON-UPLOAD-WC",
        customer_id="CUS-005",
        start_date="2026-07-01",
        end_date="2027-07-31",
        description="Working-capital contract",
        contract_value=1_200_000_000,
        gross_margin=0.29,
        payment_terms="WORKING CAPITAL",
        requested_amount=None,
        funding_need_type=None,
        tenor=None,
    )
    source = merge_contract_package(
        {
            "profile": {"company_id": "OPC-001"},
            "contracts": [],
            "customers": [],
            "orders": [],
            "invoices": [],
            "source": "database",
        },
        package,
    )

    finance = build_finance_handoff(
        package.contract_id,
        _finance_analysis(),
        source,
    )

    assert finance.requested_amount == 1_200_000_000
    assert finance.cash_impact is not None
    assert finance.cash_impact["peak_contract_cash_deficit"] == 370_285_714.26
    assert finance.cash_impact["requested_financing_amount"] == 1_200_000_000
    assert finance.finance_details["funding_need"] == {
        "type": None,
        "source": "decision_required",
        "requested_amount_source": "payment_terms_full_contract_fallback",
        "requested_amount_status": "ESTIMATED",
        "requested_amount_formula": "contract_value × 100%",
        "requested_amount_percentage": 100.0,
        "requested_amount_term": "working_capital",
        "performance_bond_percentage": None,
    }


def test_credit_profile_with_missing_amount_does_not_fall_back_to_contract() -> None:
    profile = CreditProfile(
        credit_case_id="CR-002",
        request_type="Performance bond",
        requested_amount=None,
        collateral_or_basis="Contract CON-004",
    )

    resolved = resolve_contract_funding_need(_finance_pack(), profile)

    assert resolved is not None
    assert resolved["requested_amount"] is None
    assert resolved["amount_status"] == "MISSING"
    assert resolved["source"] == "credit_profile"


def test_decision_guard_uses_credit_profile_amount_as_authority() -> None:
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[_finance_pack().model_copy(update={"requested_amount": 300_000_000})],
    )
    profile = CreditProfile(
        credit_case_id="CR-002",
        request_type="Performance bond",
        requested_amount=420_000_000,
        collateral_or_basis="Contract CON-004",
    )
    decision = _decision_batch()

    validate_decision_finance_consistency(
        decision,
        finance_batch,
        {"CON-004": profile},
    )


def test_decision_guard_requires_active_lifecycle_card_for_active_finance() -> None:
    finance = _finance_pack().model_copy(update={
        "requested_amount": None,
        "funding_need_type": None,
        "finance_details": {
            "contract_status": "Active",
            "contract_lifecycle": "ACTIVE",
            "assessment_type": "ONGOING_CONTRACT_REVIEW",
            "payment_terms": "Monthly payment",
        },
    })
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[finance],
    )

    with pytest.raises(ValueError, match="must be an ACTIVE"):
        validate_decision_finance_consistency(_decision_batch(), finance_batch, {})

    validate_decision_finance_consistency(
        _active_decision_batch(),
        finance_batch,
        {},
    )


def test_trade_finance_with_empty_docs_still_creates_approval_spec() -> None:
    finance = _finance_pack().model_copy(
        update={
            "case_id": "CASE-CON-005",
            "contract_id": "CON-005",
            "requested_amount": None,
            "funding_need_type": "TRADE_FINANCE",
            "supplier_docs": [],
        }
    )
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-005"],
        packs=[finance],
    )
    decision = _decision_batch().model_copy(deep=True)
    decision.decisions[0].contract_id = "CON-005"
    decision.decisions[0].capital_need = 650_000_000
    profile = CreditProfile(
        credit_case_id="CR-003",
        request_type="Trade finance/LC support",
        requested_amount=650_000_000,
        collateral_or_basis="CON-005 documentation",
    )

    specs = build_precheck_approval_specs(
        decision,
        finance_batch,
        {"CON-005": profile},
    )

    assert specs == [{
        "contract_id": "CON-005",
        "tool": "precheck_trade_finance",
        "arguments": {
            "contract_id": "CON-005",
            "supplier_docs": [],
            "amount": 650_000_000.0,
        },
    }]


def test_working_capital_does_not_require_customer_type_for_approval_spec() -> None:
    finance = _finance_pack().model_copy(
        update={
            "case_id": "CASE-CON-009",
            "contract_id": "CON-009",
            "requested_amount": 400_000_000,
            "funding_need_type": "WORKING_CAPITAL",
            "customer_type": None,
            "receivable_list": [],
        }
    )
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-009"],
        packs=[finance],
    )
    decision = _decision_batch().model_copy(deep=True)
    decision.decisions[0].contract_id = "CON-009"
    decision.decisions[0].capital_need = 400_000_000

    assert build_precheck_approval_specs(decision, finance_batch, {}) == [{
        "contract_id": "CON-009",
        "tool": "precheck_micro_credit",
        "arguments": {
            "contract_id": "CON-009",
            "amount": 400_000_000.0,
            "receivable_list": [],
        },
    }]


def test_precheck_uses_decision_selected_type_when_finance_type_is_null() -> None:
    finance = _finance_pack().model_copy(
        update={
            "funding_need_type": None,
            "finance_details": {
                "payment_terms": "Performance bond required",
                "funding_need": {"requested_amount_source": "contract"},
            },
        }
    )
    decision_payload = _decision_batch().model_dump(mode="json")
    decision_payload["decisions"][0].update({
        "funding_need_type": "PERFORMANCE_BOND",
        "selected_bank_product_id": "BANKPROD-002",
        "selected_bank_product_name": "Performance bond",
    })
    decision = DecisionBatchOutput.model_validate(decision_payload)

    assert build_precheck_approval_specs(
        decision,
        FinanceBatchPack(contract_ids=["CON-004"], packs=[finance]),
        {},
    ) == [{
        "contract_id": "CON-004",
        "tool": "precheck_performance_bond",
        "arguments": {
            "contract_id": "CON-004",
            "amount": 420_000_000.0,
        },
    }]


def _catalog_product(*, minimum_amount: int = 300_000_000) -> BankProduct:
    return BankProduct(
        bank_product_id="BANKPROD-002",
        bank="VietinBank",
        product_name="Performance bond",
        target_segment="Contractors",
        description="Guarantee for contract performance obligations.",
        annual_rate_or_fee=Decimal("0.012"),
        processing_fee_rate=Decimal("0"),
        collateral_ratio=Decimal("0.2"),
        minimum_amount=Decimal(minimum_amount),
        automation_level="Human approval",
        fit_note="Use when a customer contract requires a performance guarantee.",
    )


def test_bank_catalog_exposes_raw_services_without_script_matching() -> None:
    product = serialize_bank_product(_catalog_product())

    assert product == {
        "bank_product_id": "BANKPROD-002",
        "bank": "VietinBank",
        "product_name": "Performance bond",
        "target_segment": "Contractors",
        "description": "Guarantee for contract performance obligations.",
        "annual_rate_or_fee": 0.012,
        "processing_fee_rate": 0.0,
        "collateral_ratio": 0.2,
        "minimum_amount": 300_000_000.0,
        "automation_level": "Human approval",
        "fit_note": (
            "Use when a customer contract requires a performance guarantee."
        ),
    }
    assert "need_type" not in product
    assert "match_status" not in product


def test_decision_guard_verifies_agent_selected_catalog_row(monkeypatch) -> None:
    monkeypatch.setattr(
        decision_guard_service,
        "load_bank_product_catalog",
        lambda: [serialize_bank_product(_catalog_product())],
    )
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0].update({
        "funding_need_type": "PERFORMANCE_BOND",
        "selected_bank_product_id": "BANKPROD-002",
        "selected_bank_product_name": "Performance bond",
    })

    validate_decision_finance_consistency(
        DecisionBatchOutput.model_validate(payload),
        FinanceBatchPack(contract_ids=["CON-004"], packs=[_finance_pack()]),
        {},
    )


def test_decision_guard_rejects_product_above_finance_amount(monkeypatch) -> None:
    monkeypatch.setattr(
        decision_guard_service,
        "load_bank_product_catalog",
        lambda: [
            serialize_bank_product(_catalog_product(minimum_amount=500_000_000))
        ],
    )
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0].update({
        "funding_need_type": "PERFORMANCE_BOND",
        "selected_bank_product_id": "BANKPROD-002",
        "selected_bank_product_name": "Performance bond",
    })

    with pytest.raises(ValueError, match="minimum_amount=500000000"):
        validate_decision_finance_consistency(
            DecisionBatchOutput.model_validate(payload),
            FinanceBatchPack(contract_ids=["CON-004"], packs=[_finance_pack()]),
            {},
        )


def test_decision_guard_rejects_portfolio_need_as_contract_capital() -> None:
    finance = _finance_pack().model_copy(update={"requested_amount": None})
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[finance],
    )
    decision = _decision_batch().model_copy(deep=True)
    decision.decisions[0].capital_need = 705_000_000

    with pytest.raises(ValueError, match="invented contract capital_need"):
        validate_decision_finance_consistency(decision, finance_batch, {})


def test_decision_guard_accepts_exact_contract_requested_amount() -> None:
    finance_batch = FinanceBatchPack(
        contract_ids=["CON-004"],
        packs=[_finance_pack()],
    )

    validate_decision_finance_consistency(_decision_batch(), finance_batch, {})


def test_decision_precheck_fields_are_guarded() -> None:
    payload = _decision_batch().model_dump(mode="json")
    payload["decisions"][0]["eligible_score"] = 85
    with pytest.raises(ValidationError, match="must be null"):
        DecisionBatchOutput.model_validate(payload)


def test_pending_state_is_projected_into_decision_card() -> None:
    projected = apply_authoritative_precheck_state(
        _decision_batch(),
        {"approval_requests": [{
            "contract_id": "CON-004",
            "status": "pending",
        }]},
    )
    decision = projected.decisions[0]
    assert decision.external_api_submission_approval_status == "PENDING"
    assert decision.bank_precheck_status == "ELIGIBLE_AWAITING_APPROVAL"
    assert decision.eligibility_score is None
    validate_decision_prechecks(
        projected,
        {"approval_requests": [{
            "contract_id": "CON-004",
            "status": "pending",
        }]},
    )


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
async def test_executed_but_unapplied_approval_remains_retryable(monkeypatch) -> None:
    requests = [
        {
            "approval_id": "approval-retry",
            "contract_id": "CON-012",
            "status": "executed",
            "decision_applied_at": None,
        },
        {
            "approval_id": "approval-done",
            "contract_id": "CON-013",
            "status": "executed",
            "decision_applied_at": "2026-07-21T00:00:00+00:00",
        },
    ]

    async def list_requests(_run_id: int):
        return requests

    monkeypatch.setattr(approval_service, "list_approval_requests", list_requests)
    monkeypatch.setattr(
        approval_service,
        "load_pipeline_context",
        lambda _run_id: (_ for _ in ()).throw(LookupError),
    )

    pending = await approval_service.get_pending_approvals(54)

    assert [request["approval_id"] for request in pending] == ["approval-retry"]


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
