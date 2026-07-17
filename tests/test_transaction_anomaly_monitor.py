"""Tests for the stateless transaction anomaly monitor."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.schema.handoff_packs import FinanceFeaturePack, RiskAlert, Severity
from app.schema.risk_db_models import BankTransaction, RiskRule
from app.service import transaction_anomaly_monitor as monitor
from app.tools.RiskAgent import BuildRiskReport


def _rule(condition: str = "transaction_risk_score >= 85") -> RiskRule:
    return RiskRule(
        rule_id="RR-001",
        risk_type="Transaction anomaly",
        trigger_condition=condition,
        severity=Severity.CRITICAL,
        required_action="Require founder approval",
        owner_agent="Risk Agent",
    )


def _transaction(txn_id: str, score: int | None) -> BankTransaction:
    return BankTransaction(
        txn_id=txn_id,
        txn_date=date(2026, 7, 17),
        transaction_risk_score=score,
    )


@pytest.mark.parametrize(
    ("score", "status"),
    [(84, "NOT_TRIGGERED"), (85, "TRIGGERED"), (90, "TRIGGERED")],
)
def test_rule_boundary(score: int, status: str) -> None:
    result = monitor.evaluate_transaction_rule(_transaction("TXN-A", score), _rule())

    assert result.status == status
    assert result.severity == Severity.CRITICAL
    assert result.risk_score == score


def test_missing_score_is_insufficient_evidence() -> None:
    result = monitor.evaluate_transaction_rule(_transaction("TXN-A", None), _rule())

    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.missing_fields == ["transaction_risk_score"]


def test_malformed_rule_is_insufficient_evidence() -> None:
    result = monitor.evaluate_transaction_rule(
        _transaction("TXN-A", 90),
        _rule("not a supported condition"),
    )

    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.missing_fields == ["parseable_trigger_condition"]


@pytest.mark.parametrize(
    ("condition", "score", "status"),
    [
        ("transaction_risk_score > 85", 85, "NOT_TRIGGERED"),
        ("transaction_risk_score < 85", 84, "TRIGGERED"),
        ("transaction_risk_score <= 85", 85, "TRIGGERED"),
        ("transaction_risk_score = 85", 85, "TRIGGERED"),
    ],
)
def test_all_supported_operators(
    condition: str, score: int, status: str
) -> None:
    result = monitor.evaluate_transaction_rule(
        _transaction("TXN-A", score), _rule(condition)
    )

    assert result.status == status


def test_alert_uses_database_rule_metadata() -> None:
    rule = _rule()
    alert = monitor.build_transaction_alert(_transaction("TXN-A", 90), rule)

    assert alert.severity == rule.severity
    assert alert.recommended_action == rule.required_action
    assert alert.description == (
        "Transaction satisfies RR-001: transaction_risk_score >= 85."
    )
    assert alert.risk_score == 90


def test_deterministic_alert_id_is_stable_and_pair_specific() -> None:
    first = monitor.build_transaction_alert(_transaction("TXN-A", 90), _rule())
    repeated = monitor.build_transaction_alert(_transaction("TXN-A", 90), _rule())
    different = monitor.build_transaction_alert(_transaction("TXN-B", 90), _rule())

    assert first.alert_id == repeated.alert_id
    assert first.alert_id.startswith("AL-TXN-")
    assert first.alert_id != different.alert_id


def test_related_record_parser_supports_legacy_list() -> None:
    assert monitor._related_record_ids("TXN-006, TXN-007") == {
        "TXN-006",
        "TXN-007",
    }


def _patch_scan_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    transactions: list[BankTransaction],
    alerts: list[RiskAlert] | None = None,
) -> None:
    monkeypatch.setattr(monitor, "load_transaction_anomaly_rules", lambda: [_rule()])
    monkeypatch.setattr(
        monitor,
        "fetch_bank_transactions",
        lambda: [transaction.model_dump() for transaction in transactions],
    )
    monkeypatch.setattr(monitor, "get_alerts_impl", lambda: alerts or [])


def test_normal_transaction_does_not_write_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_scan_sources(monkeypatch, transactions=[_transaction("TXN-NORMAL", 20)])
    monkeypatch.setattr(
        monitor,
        "upsert_transaction_alert",
        lambda _alert: pytest.fail("normal transaction must not be persisted"),
    )

    report = monitor.scan_transaction_anomalies_once()

    assert report.evaluations_completed == 1
    assert report.anomalies_detected == 0
    assert report.alerts_created == 0


def test_first_scan_creates_deterministic_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = _transaction("TXN-NEW", 90)
    expected = monitor.build_transaction_alert(transaction, _rule())
    written: list[RiskAlert] = []
    _patch_scan_sources(monkeypatch, transactions=[transaction])

    def fake_upsert(alert: RiskAlert) -> monitor.AlertUpsertResult:
        written.append(alert)
        return monitor.AlertUpsertResult(alert_id=alert.alert_id, inserted=True)

    monkeypatch.setattr(monitor, "upsert_transaction_alert", fake_upsert)

    report = monitor.scan_transaction_anomalies_once()

    assert report.alerts_created == 1
    assert report.alerts_updated == 0
    assert written == [expected]


def test_legacy_alert_prevents_new_deterministic_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = RiskAlert(
        alert_id="AL-001",
        alert_date=date(2026, 7, 1),
        alert_type="Transaction anomaly",
        related_record="TXN-006, TXN-007",
        severity=Severity.CRITICAL,
        risk_score=90,
        description="Legacy alert",
        recommended_action="Review",
    )
    _patch_scan_sources(
        monkeypatch,
        transactions=[_transaction("TXN-006", 88), _transaction("TXN-007", 91)],
        alerts=[legacy],
    )
    monkeypatch.setattr(
        monitor,
        "upsert_transaction_alert",
        lambda _alert: pytest.fail("legacy-covered transactions must not be persisted"),
    )

    report = monitor.scan_transaction_anomalies_once()

    assert report.anomalies_detected == 2
    assert report.alerts_already_existing == 2
    assert report.alerts_created == 0


def test_unchanged_deterministic_alert_is_not_written_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = _transaction("TXN-NEW", 90)
    existing = monitor.build_transaction_alert(transaction, _rule())
    _patch_scan_sources(
        monkeypatch,
        transactions=[transaction],
        alerts=[existing],
    )
    monkeypatch.setattr(
        monitor,
        "upsert_transaction_alert",
        lambda _alert: pytest.fail("unchanged alert must not be persisted"),
    )

    report = monitor.scan_transaction_anomalies_once()

    assert report.alerts_already_existing == 1
    assert report.alerts_created == 0
    assert report.alerts_updated == 0


def test_changed_anomalous_score_updates_deterministic_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction = _transaction("TXN-NEW", 90)
    existing = monitor.build_transaction_alert(_transaction("TXN-NEW", 85), _rule())
    written: list[RiskAlert] = []
    _patch_scan_sources(
        monkeypatch,
        transactions=[transaction],
        alerts=[existing],
    )

    def fake_upsert(alert: RiskAlert) -> monitor.AlertUpsertResult:
        written.append(alert)
        return monitor.AlertUpsertResult(alert_id=alert.alert_id, inserted=False)

    monkeypatch.setattr(monitor, "upsert_transaction_alert", fake_upsert)

    report = monitor.scan_transaction_anomalies_once()

    assert report.alerts_updated == 1
    assert report.alerts_created == 0
    assert written[0].risk_score == 90


def test_invalid_transaction_does_not_abort_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(monitor, "load_transaction_anomaly_rules", lambda: [_rule()])
    monkeypatch.setattr(monitor, "get_alerts_impl", lambda: [])
    monkeypatch.setattr(
        monitor,
        "fetch_bank_transactions",
        lambda: [
            {"txn_id": "TXN-BAD", "transaction_risk_score": 101},
            _transaction("TXN-GOOD", 20).model_dump(),
        ],
    )

    report = monitor.scan_transaction_anomalies_once()

    assert report.transactions_scanned == 2
    assert report.evaluations_completed == 1
    assert len(report.errors) == 1
    assert "TXN-BAD" not in report.errors[0]
    assert "TOK-TXN-" in report.errors[0]


def test_upsert_is_parameterized_and_reports_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alert = monitor.build_transaction_alert(_transaction("TXN-NEW", 90), _rule())
    captured: dict[str, object] = {}

    def fake_query(query: str, params: tuple[object, ...]) -> list[dict[str, object]]:
        captured["query"] = query
        captured["params"] = params
        return [{"alert_id": alert.alert_id, "inserted": True}]

    monkeypatch.setattr(monitor, "query_db", fake_query)

    result = monitor.upsert_transaction_alert(alert)

    assert result.inserted is True
    assert "ON CONFLICT (alert_id)" in str(captured["query"])
    assert "TXN-NEW" not in str(captured["query"])
    assert "TXN-NEW" in captured["params"]


def test_contract_risk_pack_matches_and_masks_transaction_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule = _rule()
    transaction = _transaction("TXN-NEW", 90)
    alert = monitor.build_transaction_alert(transaction, rule)
    finance_pack = FinanceFeaturePack(
        case_id="CASE-001",
        contract_id="CON-001",
        company_id="OPC-001",
        generated_at=datetime.now(UTC),
        transaction_risk_score=90,
        source_record_ids=[transaction.txn_id],
    )
    monkeypatch.setattr(BuildRiskReport, "get_risk_rules_impl", lambda: [rule])
    monkeypatch.setattr(BuildRiskReport, "get_alerts_impl", lambda: [alert])

    risk_pack = BuildRiskReport.build_risk_pack_impl(finance_pack)

    assert risk_pack.triggered_rule_ids == ["RR-001"]
    assert len(risk_pack.alerts) == 1
    assert risk_pack.alerts[0].match_basis == "RELATED_RECORD"
    assert risk_pack.alerts[0].matched_rule_ids == ["RR-001"]
    assert risk_pack.alerts[0].alert.related_record != transaction.txn_id
    assert risk_pack.alerts[0].alert.related_record.startswith("TOK-TXN-")
