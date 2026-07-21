"""Tests for build_risk_pack_impl: proposed alerts, alias matching, summary, masking.

Không cần Supabase: monkeypatch các hàm đọc DB (get_risk_rules_impl,
get_alerts_impl, get_data_classes_impl) trong BuildRiskReport.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.schema.handoff_packs import FinanceFeaturePack, RiskAlert, Severity
from app.schema.risk_db_models import DataClassRule, RiskRule
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


def _patch(monkeypatch, *, rules, alerts, data_classes=_DATA_CLASSES) -> None:
    monkeypatch.setattr(BuildRiskReport, "get_risk_rules_impl", lambda: rules)
    monkeypatch.setattr(BuildRiskReport, "get_alerts_impl", lambda: alerts)
    monkeypatch.setattr(BuildRiskReport, "get_data_classes_impl", lambda: data_classes)


def test_triggered_rule_without_alert_becomes_proposed(monkeypatch) -> None:
    rule = _rule("RR-007", "Delivery delay",
                 "delivery_delay_days > 5", Severity.HIGH,
                 "Human approval required")
    _patch(monkeypatch, rules=[rule], alerts=[])

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
    _patch(monkeypatch, rules=[rule_detected, rule_proposed], alerts=[alert])

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
    rule = _rule("RR-003", "Margin below target", "gross_margin < 0.28",
                 Severity.MEDIUM)
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(
        _finance_pack(gross_margin=0.1, source_record_ids=["CON-001", "TXN-001"])
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


def test_rr005_is_disabled_even_when_large_amount_exceeds_threshold(monkeypatch) -> None:
    rule = _rule("RR-005", "Large financial decision",
                 "requested_amount > 300000000", Severity.HIGH,
                 "Human approval required")
    _patch(monkeypatch, rules=[rule], alerts=[])

    pack = BuildRiskReport.build_risk_pack_impl(
        _finance_pack(requested_amount=400_000_000)
    )

    assert pack.rule_evaluations == []
    assert pack.triggered_rule_ids == []
    assert pack.proposed_alerts == []
    assert pack.summary.total_rules_triggered == 0
    assert pack.summary.human_review_required is False
