"""Stateless polling service for transaction anomaly alerts.

This module deliberately does not expose Agent SDK function tools. It scans
``bank_txn``, evaluates database-owned transaction rules, and writes
idempotent rows to ``alert`` independently from the contract Risk Agent.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import operator
import re
import signal
import threading
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Literal, Sequence

from pydantic import Field, ValidationError
from psycopg2 import Error as PsycopgError

from app.database.repository import close_db_pool, query_db
from app.schema.handoff_packs import RiskAlert, Severity, StrictModel
from app.schema.risk_db_models import BankTransaction, RiskRule
from app.tools.RiskAgent.GetRiskControls import get_alerts_impl
from app.tools.RiskAgent._helpers import parse_severity, require_rows
from app.tools.RiskAgent._masking import tokenize_identifier

logger = logging.getLogger(__name__)

EvaluationStatus = Literal[
    "TRIGGERED", "NOT_TRIGGERED", "INSUFFICIENT_EVIDENCE"
]

_TRANSACTION_METRIC = "transaction_risk_score"
_CONDITION = re.compile(
    r"^\s*(?P<metric>[a-z_]+)\s*(?P<operator>>=|<=|=|>|<)\s*"
    r"(?P<target>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$",
    re.I,
)
_OPERATORS: dict[str, Callable[[Decimal, Decimal], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "=": operator.eq,
}
_DETERMINISTIC_ALERT_PREFIX = "AL-TXN-"
_BACKOFF_SECONDS = (1, 2, 4, 8, 16, 30)


class TransactionRuleEvaluation(StrictModel):
    txn_token: str
    rule_id: str
    status: EvaluationStatus
    severity: Severity
    risk_score: int | None = Field(default=None, ge=0, le=100)
    message: str
    missing_fields: list[str] = Field(default_factory=list)


class TransactionMonitorReport(StrictModel):
    started_at: datetime
    completed_at: datetime | None = None
    rules_loaded: int = 0
    transactions_scanned: int = 0
    evaluations_completed: int = 0
    anomalies_detected: int = 0
    alerts_created: int = 0
    alerts_updated: int = 0
    alerts_already_existing: int = 0
    insufficient_evidence: int = 0
    errors: list[str] = Field(default_factory=list)


class AlertUpsertResult(StrictModel):
    alert_id: str
    inserted: bool


class ExistingTransactionAlerts(StrictModel):
    legacy_by_type_and_transaction: dict[tuple[str, str], RiskAlert] = Field(
        default_factory=dict
    )
    by_alert_id: dict[str, RiskAlert] = Field(default_factory=dict)


def _normalized_alert_type(value: str | None) -> str:
    return value.strip().casefold() if value else ""


def _related_record_ids(value: str | None) -> set[str]:
    """Parse legacy comma-separated alert record identifiers."""
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _transaction_alert_id(txn_id: str, rule_id: str) -> str:
    digest = hashlib.sha256(f"{txn_id}:{rule_id}".encode("utf-8")).hexdigest()[:12]
    return f"{_DETERMINISTIC_ALERT_PREFIX}{digest}"


def _safe_transaction_token(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return tokenize_identifier(value.strip())
    return "TOK-TXN-UNKNOWN"


def load_transaction_anomaly_rules() -> list[RiskRule]:
    """Load database rules that govern transaction risk score anomalies."""
    rows = query_db(
        """
        SELECT rule_id, risk_type, trigger_condition, severity,
               required_action, owner_agent
        FROM risk_rule
        WHERE lower(risk_type) = lower(%s)
           OR lower(trigger_condition) LIKE %s
        ORDER BY rule_id
        """,
        ("Transaction anomaly", f"%{_TRANSACTION_METRIC}%"),
    )
    rules: list[RiskRule] = []
    for row in require_rows(rows, "risk_rule"):
        try:
            rules.append(
                RiskRule(**{**row, "severity": parse_severity(row["severity"])})
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            logger.warning(
                "[TXN MONITOR] skipped invalid rule error=%s",
                type(exc).__name__,
            )
    return rules


def fetch_bank_transactions() -> list[dict[str, Any]]:
    """Fetch raw rows so one invalid transaction cannot abort the whole scan."""
    rows = query_db(
        """
        SELECT txn_id, txn_date, bank, account_id, direction, description,
               amount, counterparty_id, txn_status, transaction_risk_score
        FROM bank_txn
        ORDER BY txn_date, txn_id
        """
    )
    return require_rows(rows, "bank_txn")


def evaluate_transaction_rule(
    transaction: BankTransaction, rule: RiskRule
) -> TransactionRuleEvaluation:
    """Evaluate one transaction against one database-owned rule condition."""
    token = tokenize_identifier(transaction.txn_id)
    match = _CONDITION.match(rule.trigger_condition)
    if not match or match.group("metric").casefold() != _TRANSACTION_METRIC:
        return TransactionRuleEvaluation(
            txn_token=token,
            rule_id=rule.rule_id,
            status="INSUFFICIENT_EVIDENCE",
            severity=rule.severity,
            risk_score=transaction.transaction_risk_score,
            message="The transaction rule condition cannot be parsed safely.",
            missing_fields=["parseable_trigger_condition"],
        )

    score = transaction.transaction_risk_score
    if score is None:
        return TransactionRuleEvaluation(
            txn_token=token,
            rule_id=rule.rule_id,
            status="INSUFFICIENT_EVIDENCE",
            severity=rule.severity,
            risk_score=None,
            message="The transaction does not contain enough evidence.",
            missing_fields=[_TRANSACTION_METRIC],
        )

    try:
        target = Decimal(match.group("target"))
        observed = Decimal(score)
        triggered = _OPERATORS[match.group("operator")](observed, target)
    except (InvalidOperation, TypeError, ValueError):
        return TransactionRuleEvaluation(
            txn_token=token,
            rule_id=rule.rule_id,
            status="INSUFFICIENT_EVIDENCE",
            severity=rule.severity,
            risk_score=score,
            message="The transaction score and rule target are not comparable.",
            missing_fields=[f"comparable_{_TRANSACTION_METRIC}"],
        )

    return TransactionRuleEvaluation(
        txn_token=token,
        rule_id=rule.rule_id,
        status="TRIGGERED" if triggered else "NOT_TRIGGERED",
        severity=rule.severity,
        risk_score=score,
        message=(
            "The transaction satisfies the rule condition."
            if triggered
            else "The transaction does not satisfy the rule condition."
        ),
    )


def find_existing_transaction_alerts() -> ExistingTransactionAlerts:
    """Index deterministic and legacy alerts by raw internal transaction ID."""
    snapshot = ExistingTransactionAlerts()
    for alert in get_alerts_impl():
        snapshot.by_alert_id[alert.alert_id] = alert
        if alert.alert_id.startswith(_DETERMINISTIC_ALERT_PREFIX):
            continue
        alert_type = _normalized_alert_type(alert.alert_type)
        for txn_id in _related_record_ids(alert.related_record):
            snapshot.legacy_by_type_and_transaction[(alert_type, txn_id)] = alert
    return snapshot


def build_transaction_alert(
    transaction: BankTransaction, rule: RiskRule
) -> RiskAlert:
    """Build the internal database payload for a triggered transaction rule."""
    condition = rule.trigger_condition.strip().rstrip(".")
    return RiskAlert(
        alert_id=_transaction_alert_id(transaction.txn_id, rule.rule_id),
        alert_date=transaction.txn_date or datetime.now(UTC).date(),
        alert_type=rule.risk_type,
        related_record=transaction.txn_id,
        severity=rule.severity,
        risk_score=transaction.transaction_risk_score,
        description=(
            f"Transaction satisfies {rule.rule_id}: {condition}."
        ),
        recommended_action=rule.required_action,
    )


def upsert_transaction_alert(alert: RiskAlert) -> AlertUpsertResult:
    """Insert or update one deterministic alert atomically."""
    rows = query_db(
        """
        INSERT INTO public.alert (
            alert_id,
            alert_date,
            alert_type,
            related_record,
            severity,
            risk_score,
            description,
            recommended_action
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (alert_id)
        DO UPDATE SET
            alert_date = EXCLUDED.alert_date,
            alert_type = EXCLUDED.alert_type,
            related_record = EXCLUDED.related_record,
            severity = EXCLUDED.severity,
            risk_score = EXCLUDED.risk_score,
            description = EXCLUDED.description,
            recommended_action = EXCLUDED.recommended_action
        RETURNING alert_id, (xmax = 0) AS inserted
        """,
        (
            alert.alert_id,
            alert.alert_date,
            alert.alert_type,
            alert.related_record,
            alert.severity.value if alert.severity else None,
            alert.risk_score,
            alert.description,
            alert.recommended_action,
        ),
    )
    result_rows = require_rows(rows, "alert upsert")
    if len(result_rows) != 1:
        raise RuntimeError("Alert upsert did not return exactly one row")
    return AlertUpsertResult(**result_rows[0])


def _alert_payload_matches(existing: RiskAlert, candidate: RiskAlert) -> bool:
    fields = (
        "alert_date",
        "alert_type",
        "related_record",
        "severity",
        "risk_score",
        "description",
        "recommended_action",
    )
    return all(getattr(existing, field) == getattr(candidate, field) for field in fields)


def _record_scan_error(
    report: TransactionMonitorReport,
    *,
    txn_token: str,
    rule_id: str | None,
    category: str,
) -> None:
    rule_fragment = f" rule={rule_id}" if rule_id else ""
    report.errors.append(f"txn={txn_token}{rule_fragment} error={category}")


def scan_transaction_anomalies_once() -> TransactionMonitorReport:
    """Run one full stateless scan and return a redacted operational report."""
    report = TransactionMonitorReport(started_at=datetime.now(UTC))
    rules = load_transaction_anomaly_rules()
    existing_alerts = find_existing_transaction_alerts()
    transaction_rows = fetch_bank_transactions()
    report.rules_loaded = len(rules)
    report.transactions_scanned = len(transaction_rows)

    for row in transaction_rows:
        txn_token = _safe_transaction_token(row.get("txn_id"))
        try:
            transaction = BankTransaction(**row)
        except (ValidationError, TypeError, ValueError):
            _record_scan_error(
                report,
                txn_token=txn_token,
                rule_id=None,
                category="INVALID_TRANSACTION",
            )
            continue

        for rule in rules:
            try:
                evaluation = evaluate_transaction_rule(transaction, rule)
                report.evaluations_completed += 1
                if evaluation.status == "INSUFFICIENT_EVIDENCE":
                    report.insufficient_evidence += 1
                    continue
                if evaluation.status != "TRIGGERED":
                    continue

                report.anomalies_detected += 1
                candidate = build_transaction_alert(transaction, rule)
                key = (
                    _normalized_alert_type(rule.risk_type),
                    transaction.txn_id,
                )
                covered_alert = (
                    existing_alerts.legacy_by_type_and_transaction.get(key)
                )

                if covered_alert:
                    report.alerts_already_existing += 1
                    continue

                deterministic_alert = existing_alerts.by_alert_id.get(
                    candidate.alert_id
                )
                if deterministic_alert and _alert_payload_matches(
                    deterministic_alert, candidate
                ):
                    report.alerts_already_existing += 1
                    continue

                result = upsert_transaction_alert(candidate)
                if result.inserted:
                    report.alerts_created += 1
                    logger.info(
                        "[ANOMALY] txn=%s rule=%s severity=%s",
                        evaluation.txn_token,
                        rule.rule_id,
                        rule.severity.value,
                    )
                else:
                    report.alerts_updated += 1

                existing_alerts.by_alert_id[candidate.alert_id] = candidate
            except PsycopgError:
                # Infrastructure failures are retried by the outer polling loop.
                raise
            except Exception as exc:
                _record_scan_error(
                    report,
                    txn_token=txn_token,
                    rule_id=rule.rule_id,
                    category=type(exc).__name__.upper(),
                )

    report.completed_at = datetime.now(UTC)
    return report


def _log_report(report: TransactionMonitorReport) -> None:
    logger.info(
        "[TXN MONITOR] rules=%d scanned=%d triggered=%d created=%d "
        "updated=%d existing=%d insufficient=%d errors=%d",
        report.rules_loaded,
        report.transactions_scanned,
        report.anomalies_detected,
        report.alerts_created,
        report.alerts_updated,
        report.alerts_already_existing,
        report.insufficient_evidence,
        len(report.errors),
    )


def run_transaction_monitor(
    *, poll_seconds: float = 2.0, once: bool = False
) -> None:
    """Run the polling loop with redacted retry logging and graceful shutdown."""
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be greater than zero")

    stop_requested = threading.Event()

    def request_stop(_signum: int, _frame: Any) -> None:
        stop_requested.set()

    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, request_stop)
    backoff_index = 0

    try:
        while not stop_requested.is_set():
            try:
                report = scan_transaction_anomalies_once()
                _log_report(report)
                backoff_index = 0
            except Exception as exc:
                if once:
                    logger.error(
                        "[TXN MONITOR] scan failed error=%s",
                        type(exc).__name__,
                    )
                    raise
                delay = _BACKOFF_SECONDS[min(backoff_index, len(_BACKOFF_SECONDS) - 1)]
                backoff_index += 1
                logger.error(
                    "[TXN MONITOR] scan failed error=%s retry_in=%ds",
                    type(exc).__name__,
                    delay,
                )
                stop_requested.wait(delay)
                continue

            if once:
                break
            stop_requested.wait(poll_seconds)
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        close_db_pool()
        logger.info("[TXN MONITOR] shutdown complete")


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the stateless transaction anomaly monitor."
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Seconds between successful scans (default: 2).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one scan and exit.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_argument_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        run_transaction_monitor(
            poll_seconds=args.poll_seconds,
            once=args.once,
        )
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TransactionMonitorReport",
    "TransactionRuleEvaluation",
    "build_transaction_alert",
    "evaluate_transaction_rule",
    "fetch_bank_transactions",
    "find_existing_transaction_alerts",
    "load_transaction_anomaly_rules",
    "run_transaction_monitor",
    "scan_transaction_anomalies_once",
    "upsert_transaction_alert",
]
