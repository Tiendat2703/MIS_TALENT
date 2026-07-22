"""Tests for build_risk_pack_impl: proposed alerts, alias matching, summary, masking.

Không cần Supabase: monkeypatch các hàm đọc DB (get_risk_rules_impl,
get_alerts_impl, get_data_classes_impl) trong BuildRiskReport.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.schema.handoff_packs import FinanceFeaturePack, RiskAlert, Severity
from app.schema.risk_db_models import BankTransaction, DataClassRule, OrderRecord, RiskRule
from app.tools.RiskAgent import BuildRiskReport
from app.tools.RiskAgent._masking import Masker


def _rule(rule_id: str, risk_type: str, condition: str, severity: Severity,
          action: str = "Review") -> RiskRule:
    return RiskRule(
        rule_id=rule_id,
        risk_type=risk_type,
        trigger_condition=condition,
        severity=severity,
        required_action=action,
        owner_agent="Risk & Compliance Agent",
    )


def _alert(alert_id: str, alert_type: str, related_record: str,
           severity: Severity) -> RiskAlert:
    return RiskAlert(
        alert_id=alert_id,
        alert_date=date(2026, 7, 1),
        alert_type=alert_type,
        related_record=related_record,
        severity=severity,
        risk_score=80,
        description="x",
        recommended_action="y",
    )


def _finance_pack(**overrides) -> FinanceFeaturePack:
    base = dict(
        case_id="CASE-001",
        contract_id="CON-001",
        company_id="OPC-001",
        generated_at=datetime.now(UTC),
        source_record_ids=["CON-001"],
        handoff_summary="Deterministic finance handoff for tests.",
    )
    base.update(overrides)
    return FinanceFeaturePack(**base)


_DATA_CLASSES = [
    DataClassRule(
        data_pattern="Restricted identifier",
        example_field="company_id, customer_id, account_id, counterparty_id",
        classification="restricted",
        masking_or_tokenization="Tokenize deterministically",
    ),
    DataClassRule(
        data_pattern="Business confidential",
        example_field="contract_value, cashflow, eligibility_score",
        classification="confidential",
        masking_or_tokenization="Round/aggregate or tokenize",
    ),
]


def _patch(
    monkeypatch,
    *,
    rules,
    alerts,
    data_classes=_DATA_CLASSES,
    bank_transactions=None,
    portfolio_bank_transactions=None,
    orders=None,
) -> None:
    monkeypatch.setattr(BuildRiskReport, "get_risk_rules_impl", lambda: rules)
    monkeypatch.setattr(BuildRiskReport, "get_alerts_impl", lambda: alerts)
    monkeypatch.setattr(BuildRiskReport, "get_data_classes_impl", lambda: data_classes)
    monkeypatch.setattr(
        BuildRiskReport,
        "load_risk_source_evidence_impl",
        lambda _pack: {
            "bank_transactions": bank_transactions or [],
            "portfolio_bank_transactions": portfolio_bank_transactions or [],
            "orders": orders or [],
        },
    )


def test_triggered_rule_without_alert_becomes_proposed(monkeypatch) -> None:
    rule = _rule("RR-007", "Delivery delay",
                 "delivery_delay_days > 5", Severity.HIGH,
                 "Human approval required")
    _patch(
        monkeypatch,
        rules=[rule],
        alerts=[],
        orders=[OrderRecord(
            order_id="ORD-001",
            contract_id="CON-001",
            due_date=date.today() - timedelta(days=10),
            status="In progress",
        )],
    )

    pack = BuildRiskReport.build_risk_pack_impl(
        _finance_pack(delivery_delay_days=10)
    )

    assert pack.triggered_rule_ids == ["RR-007"]
    assert len(pack.proposed_alerts) == 1
    proposed = pack.proposed_alerts[0]
    assert proposed.rule_id == "RR-007"
    assert proposed.requires_human_review is True
    assert proposed.alert_source == "AGENT_PROPOSED"
    assert "CON-001" not in proposed.proposed_alert_id  # contract id đã mask
    assert pack.summary.unmapped_rule_ids == ["RR-007"]
    assert pack.summary.total_proposed_alerts == 1
    assert pack.summary.human_review_required is True


def test_alias_matches_alert_as_detected(monkeypatch) -> None:
    rule = _rule("RR-002", "Cash reserve breach",
                 "closing_cash < cash_reserve_minimum", Severity.HIGH)
    alert = _alert("AL-002", "Cashflow shortage", "2026-07", Severity.HIGH)
    _patch(monkeypatch, rules=[rule], alerts=[alert])

    pack = BuildRiskReport.build_risk_pack_impl(
        _finance_pack(
            projected_closing_cash=100_000_000,
            cash_reserve_minimum=550_000_000,
            source_record_ids=["CON-002"],  # không trùng related_record
        )
    )

    assert pack.triggered_rule_ids == ["RR-002"]
    assert len(pack.alerts) == 1
    assert pack.alerts[0].matched_rule_ids == ["RR-002"]
    assert pack.alerts[0].match_basis == "EXACT_RISK_TYPE"
    assert pack.proposed_alerts == []
    assert pack.summary.total_alerts_detected == 1
    assert pack.summary.unmapped_rule_ids == []


def test_summary_counts_detected_and_proposed(monkeypatch) -> None:
    rule_detected = _rule("RR-002", "Cash reserve breach",
                          "closing_cash < cash_reserve_minimum", Severity.HIGH)
    rule_proposed = _rule("RR-007", "Delivery delay",
                          "delivery_delay_days > 5", Severity.HIGH,
                          "Human approval required")
    alert = _alert("AL-002", "Cashflow shortage", "2026-07", Severity.HIGH)
    _patch(
        monkeypatch,
        rules=[rule_detected, rule_proposed],
        alerts=[alert],
        orders=[OrderRecord(
            order_id="ORD-001",
            contract_id="CON-001",
            due_date=date.today() - timedelta(days=10),
            status="In progress",
        )],
    )

    pack = BuildRiskReport.build_risk_pack_impl(
        _finance_pack(
            projected_closing_cash=100_000_000,
            cash_reserve_minimum=550_000_000,
            requested_amount=400_000_000,
            delivery_delay_days=10,
            source_record_ids=["CON-002"],
        )
    )

    assert pack.summary.total_rules_triggered == 2
    assert pack.summary.total_alerts_detected == 1
    assert pack.summary.total_proposed_alerts == 1
    assert pack.summary.unmapped_rule_ids == ["RR-007"]
    assert pack.summary.highest_severity == Severity.HIGH
    assert pack.summary.human_review_required is True


def test_masking_confidential_value_and_identifiers(monkeypatch) -> None:
    rule = _rule(
        "RR-003",
        "Margin below target",
        "expected_gross_margin_rate < 0.28",
        Severity.MEDIUM,
    )
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(
        _finance_pack(
            source_record_ids=["CON-001", "TXN-001"],
            finance_details={
                "contract_economics": {"expected_gross_margin_rate": 0.1}
            },
        )
    )

    # gross_margin là confidential -> observed_value bị che
    evaluation = pack.rule_evaluations[0]
    assert evaluation.status == "TRIGGERED"
    assert evaluation.observed_value == "[CONFIDENTIAL_VALUE]"

    # masked_data có dữ liệu, không lộ raw
    assert pack.masked_data.masking_applied is True
    assert pack.masked_data.masked_fields
    masked_values = {f.masked_value for f in pack.masked_data.masked_fields}
    assert "[CONFIDENTIAL_VALUE]" in masked_values
    assert all("CON-001" != mv for mv in masked_values)

    # proposed alert (RR-003 không có alert) có related_records đã tokenize
    assert len(pack.proposed_alerts) == 1
    assert all(rec.startswith("TOK-") for rec in pack.proposed_alerts[0].related_records)


def test_rr003_maps_workbook_gross_margin_to_contract_baseline(
    monkeypatch,
) -> None:
    rule = _rule(
        "RR-003",
        "Margin below target",
        "gross_margin < 0.28",
        Severity.MEDIUM,
    )
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(_finance_pack(
        gross_margin=None,
        finance_details={
            "contract_lifecycle": "ACTIVE",
            "contract_economics": {"expected_gross_margin_rate": 0.18},
            "execution_finance": {"current_margin_pct": None},
        },
    ))

    assert pack.rule_evaluations[0].status == "TRIGGERED"
    assert pack.rule_evaluations[0].evidence_scope == "CONTRACT_BASELINE"
    assert pack.triggered_rule_ids == ["RR-003"]
    assert pack.insufficient_evidence == []
    assert pack.risk_assessment_status == "COMPLETE"
    assert pack.overall_risk_level is None
    assert pack.review_priority == Severity.MEDIUM
    assert pack.manual_evidence_review_required is True  # proposed alert review


def test_active_risk_can_evaluate_contract_scoped_overdue_receivable(
    monkeypatch,
) -> None:
    rule = _rule(
        "RR-008",
        "Overdue receivable",
        "overdue_receivable > 0",
        Severity.HIGH,
        "Escalate collection action",
    )
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(_finance_pack(
        finance_details={
            "contract_lifecycle": "ACTIVE",
            "execution_finance": {"overdue_receivable": 120_000_000},
        },
    ))

    assert pack.triggered_rule_ids == ["RR-008"]
    assert pack.rule_evaluations[0].status == "TRIGGERED"
    assert pack.human_approval_required is False


def test_masker_tokenizes_by_field_type() -> None:
    dc = [DataClassRule(
        data_pattern="Restricted identifier",
        example_field="company_id, customer_id, account_id, counterparty_id",
        classification="restricted",
        masking_or_tokenization="Tokenize deterministically",
    )]
    m = Masker(dc)
    assert m.mask_field_value("account_id", "OPC_MAIN").startswith("TOK-ACC-")
    assert m.mask_field_value("customer_id", "CUS-005").startswith("TOK-CUS-")
    assert m.mask_field_value("company_id", "OPC-001").startswith("TOK-ORG-")
    # cùng giá trị -> cùng token (deterministic để liên kết được)
    assert m.mask_field_value("account_id", "OPC_MAIN") == m.mask_field_value("account_id", "OPC_MAIN")
    # không lộ raw
    assert "OPC_MAIN" not in m.mask_field_value("account_id", "OPC_MAIN")


def test_rr005_is_active_but_only_creates_an_approval_gate(monkeypatch) -> None:
    rule = _rule("RR-005", "Large financial decision",
                 "requested_amount > 300000000", Severity.HIGH,
                 "Human approval required")
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(
        _finance_pack(requested_amount=400_000_000)
    )

    assert len(pack.rule_evaluations) == 1
    assert pack.rule_evaluations[0].rule_id == "RR-005"
    assert pack.rule_evaluations[0].status == "TRIGGERED"
    assert pack.triggered_rule_ids == ["RR-005"]
    assert pack.summary.total_rules_triggered == 1
    assert pack.triggered_rule_approval_required is True


def test_transaction_score_comes_from_linked_bank_transaction(monkeypatch) -> None:
    rule = _rule(
        "RR-001",
        "Transaction anomaly",
        "transaction_risk_score >= 85",
        Severity.CRITICAL,
    )
    _patch(
        monkeypatch,
        rules=[rule],
        alerts=[],
        bank_transactions=[BankTransaction(
            txn_id="TXN-004",
            transaction_risk_score=88,
        )],
    )

    pack = BuildRiskReport.build_risk_pack_impl(_finance_pack(
        transaction_risk_score=None,
        source_record_ids=["CON-001", "INV-001", "TXN-004"],
    ))

    evaluation = pack.rule_evaluations[0]
    assert evaluation.status == "TRIGGERED"
    assert evaluation.evidence_sources == ["08_BANK_TXN"]
    assert evaluation.evidence_paths == ["08_BANK_TXN.transaction_risk_score"]
    assert evaluation.evidence_record_ids


def test_applicable_rules_can_complete_without_a_global_risk_level(monkeypatch) -> None:
    _patch(
        monkeypatch,
        rules=[
            _rule(
                "RR-002",
                "Cash reserve breach",
                "closing_cash < cash_reserve_minimum",
                Severity.HIGH,
            ),
            _rule(
                "RR-003",
                "Margin below target",
                "gross_margin < 0.28",
                Severity.MEDIUM,
            ),
        ],
        alerts=[],
    )
    pack = BuildRiskReport.build_risk_pack_impl(_finance_pack(
        finance_details={
            "portfolio_context": {
                "projected_closing_cash": -160_000_000,
                "cash_reserve_minimum": 550_000_000,
            },
            "contract_economics": {"expected_gross_margin_rate": 0.30},
            "order_allocation": {"allocated_order_margin_rate": 0.6815},
        },
    ))

    assert pack.triggered_rule_ids == ["RR-002"]
    assert pack.risk_assessment_status == "COMPLETE"
    assert pack.overall_risk_level is None
    assert pack.review_priority == Severity.HIGH
    assert pack.portfolio_triggered_rule_ids == ["RR-002"]
    assert pack.contract_triggered_rule_ids == []


def test_rr006_is_not_applicable_before_banking_recommendation(monkeypatch) -> None:
    rule = _rule(
        "RR-006",
        "Banking recommendation confidence",
        "confidence_score < 0.65",
        Severity.MEDIUM,
    ).model_copy(update={"confidence_score": 0.5})
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(_finance_pack(confidence_score=0.99))

    evaluation = pack.rule_evaluations[0]
    assert evaluation.status == "NOT_APPLICABLE"
    assert evaluation.message == "No banking recommendation has been generated."


def test_rr006_reads_observed_confidence_from_banking_recommendation(
    monkeypatch,
) -> None:
    rule = _rule(
        "RR-006",
        "Banking recommendation confidence",
        "confidence_score < 0.65",
        Severity.MEDIUM,
    ).model_copy(update={"confidence_score": 0.99})
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(_finance_pack(
        finance_details={
            "banking_recommendation": {
                "product_id": "BANKPROD-001",
                "confidence_score": 0.5,
            },
        },
    ))

    evaluation = pack.rule_evaluations[0]
    assert evaluation.status == "TRIGGERED"
    assert evaluation.evidence_sources == ["DECISION_BANKING_RECOMMENDATION"]
    assert evaluation.evidence_paths == [
        "finance_details.banking_recommendation.confidence_score"
    ]


def test_con002_rules_are_scoped_and_complete_after_applicability(monkeypatch) -> None:
    rules = [
        _rule(
            "RR-001",
            "Transaction anomaly",
            "transaction_risk_score >= 85",
            Severity.CRITICAL,
            "Temporarily hold transaction and require founder approval",
        ),
        _rule(
            "RR-002",
            "Cash reserve breach",
            "closing_cash < cash_reserve_minimum",
            Severity.HIGH,
            "Recommend working capital option or phase delivery",
        ),
        _rule(
            "RR-003",
            "Margin below target",
            "gross_margin < 0.28",
            Severity.MEDIUM,
            "Flag pricing/cost review",
        ),
        _rule(
            "RR-004",
            "External document release",
            "document_sent_to_partner = true",
            Severity.HIGH,
            "Human approval required",
        ),
        _rule(
            "RR-005",
            "Large financial decision",
            "requested_amount > 300000000",
            Severity.HIGH,
            "Human approval required",
        ),
        _rule(
            "RR-006",
            "Banking recommendation confidence",
            "confidence_score < 0.65",
            Severity.MEDIUM,
            "Ask for missing data or provide no-recommendation",
        ),
        _rule(
            "RR-007",
            "Late delivery penalty",
            "delivery_delay_days > 7",
            Severity.HIGH,
            "Escalate operations plan and penalty exposure",
        ),
    ]
    portfolio_transactions = [
        BankTransaction(txn_id="TXN-006", transaction_risk_score=88),
        BankTransaction(txn_id="TXN-007", transaction_risk_score=91),
    ]
    orders = [
        OrderRecord(
            order_id="ORD-003",
            contract_id="CON-002",
            due_date=date(2026, 6, 10),
            status="Delivered",
        ),
        OrderRecord(
            order_id="ORD-009",
            contract_id="CON-002",
            due_date=date(2026, 7, 30),
            status="In progress",
        ),
    ]
    alerts = [
        _alert(
            "AL-001",
            "Transaction anomaly",
            "TXN-006, TXN-007",
            Severity.CRITICAL,
        ),
        _alert("AL-002", "Cashflow shortage", "2026-07", Severity.HIGH),
        _alert("AL-005", "Margin pressure", "ORD-003", Severity.MEDIUM),
    ]
    _patch(
        monkeypatch,
        rules=rules,
        alerts=alerts,
        bank_transactions=[],
        portfolio_bank_transactions=portfolio_transactions,
        orders=orders,
    )

    pack = BuildRiskReport.build_risk_pack_impl(_finance_pack(
        contract_id="CON-002",
        case_id="CASE-CON-002",
        generated_at=datetime(2026, 7, 22, tzinfo=UTC),
        requested_amount=None,
        document_sent_to_partner=None,
        source_record_ids=["CON-002", "ORD-003", "ORD-009", "INV-002", "INV-007"],
        finance_details={
            "contract_finance": {
                "scope": "contract",
                "contract_economics": {
                    "contract_value": 980_000_000,
                    "expected_gross_margin_rate": 0.26,
                },
                "order_allocation": {},
                "execution_finance": {},
                "invoice_metrics": {},
                "funding_need": {"requested_amount_status": "MISSING"},
            },
            "portfolio_context": {
                "scope": "portfolio",
                "projected_closing_cash": -160_000_000,
                "cash_reserve_minimum": 550_000_000,
                "months_below_reserve": [
                    "2026-06", "2026-07", "2026-08",
                    "2026-09", "2026-10", "2026-11",
                ],
                "negative_cash_months": ["2026-06", "2026-07", "2026-08"],
                "maximum_reserve_gap": 710_000_000,
            },
        },
    ))

    evaluations = {(item.rule_id, item.scope): item for item in pack.rule_evaluations}
    assert evaluations[("RR-001", "CONTRACT")].status == "NOT_APPLICABLE"
    assert evaluations[("RR-001", "PORTFOLIO")].status == "TRIGGERED"
    assert evaluations[("RR-002", "PORTFOLIO")].status == "TRIGGERED"
    assert evaluations[("RR-003", "CONTRACT")].status == "TRIGGERED"
    assert evaluations[("RR-004", "CONTRACT")].status == "NOT_APPLICABLE"
    assert evaluations[("RR-005", "CONTRACT")].status == "NOT_APPLICABLE"
    assert evaluations[("RR-006", "CONTRACT")].status == "NOT_APPLICABLE"
    assert evaluations[("RR-007", "CONTRACT")].status == "NOT_TRIGGERED"
    assert all(
        item.findings
        for item in pack.rule_evaluations
        if item.status == "TRIGGERED"
    )
    assert pack.risk_assessment_status == "COMPLETE"
    assert pack.overall_risk_level is None
    assert pack.contract_triggered_rule_ids == ["RR-003"]
    assert pack.portfolio_triggered_rule_ids == ["RR-001", "RR-002"]
    assert pack.highest_contract_triggered_severity == Severity.MEDIUM
    assert pack.highest_portfolio_triggered_severity == Severity.CRITICAL
    matched = {
        item.alert.alert_id: item.matched_rule_ids for item in pack.alerts
    }
    assert matched["AL-001"] == ["RR-001"]
    assert matched["AL-002"] == ["RR-002"]
    assert matched["AL-005"] == ["RR-003"]
    assert pack.portfolio_transaction_approval_required is True
    assert len(pack.portfolio_transaction_approval_object_ids) == 2
