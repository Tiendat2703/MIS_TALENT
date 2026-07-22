"""Build one masked Risk Pack from a Finance Feature Pack."""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Callable, Literal

from agents import function_tool

from app.schema.handoff_packs import (
    FinanceFeaturePack,
    MaskedDataSummary,
    ProposedAlert,
    RiskAlertMatch,
    RiskFinding,
    RiskPack,
    RiskPackSummary,
    RuleEvaluation,
    Severity,
)
from app.schema.risk_db_models import BankTransaction, OrderRecord, RiskRule
from app.tools.RiskAgent.GetRiskControls import (
    get_alerts_impl,
    get_data_classes_impl,
    get_risk_rules_impl,
    load_risk_source_evidence_impl,
)
from app.tools.RiskAgent._masking import Masker

_CONDITION = re.compile(
    r"^\s*(?P<metric>[a-z_]+)\s*(?P<operator>>=|<=|=|>|<)\s*(?P<target>.+?)\s*$",
    re.I,
)
_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "=": operator.eq,
}
_ACTIVE_EXECUTION_METRICS = {
    "invoiced_amount",
    "collected_amount",
    "open_receivable",
    "overdue_receivable",
    "remaining_estimated_cost",
    "current_margin_pct",
    "target_margin_pct",
    "projected_funding_need",
    "allocated_order_revenue",
    "allocated_order_estimated_cost",
    "allocated_order_estimated_margin_amount",
    "allocated_order_estimated_margin_rate",
}
_EXPLICIT_MARGIN_METRICS = {
    "expected_gross_margin_rate",
    "allocated_order_estimated_margin_rate",
    "actual_margin_rate",
}
_SEVERITY_RANK = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}

# Alias giữa risk_type của rule và alert_type trong 14_ALERTS (dữ liệu tổ chức đặt
# tên khác nhau cho cùng một loại rủi ro). Có thể mở rộng sau khi review.
_RISK_TYPE_ALIASES: dict[str, set[str]] = {
    "cash reserve breach": {"cashflow shortage"},
    "margin below target": {"margin pressure"},
}


def _related_records(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def _parse_literal(value: str) -> float | bool | str:
    normalized = value.strip()
    if normalized.lower() in {"true", "false"}:
        return normalized.lower() == "true"
    try:
        return float(normalized)
    except ValueError:
        return normalized


@dataclass(frozen=True)
class _MetricEvidence:
    value: Any = None
    sources: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    scope: str | None = None
    record_ids: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    observed_metrics: dict[str, Any] = field(default_factory=dict)
    configuration_error: bool = False
    message: str = ""


def _masked_record_ids(
    masker: Masker,
    record_ids: list[str],
) -> list[str]:
    return [
        masked
        for record_id in record_ids
        if (masked := masker.mask_identifier_text(record_id, "source_record"))
    ]


def _portfolio_metric(
    finance_pack: FinanceFeaturePack,
    metric: str,
) -> _MetricEvidence:
    details = finance_pack.finance_details or {}
    portfolio = details.get("portfolio_context") or {}
    key = (
        "projected_closing_cash"
        if metric in {"closing_cash", "projected_closing_cash"}
        else "cash_reserve_minimum"
    )
    value = portfolio.get(key)
    if value is None:
        # Legacy/new-opportunity packs can still contain the same value at the
        # top level. The explicit path remains recorded for auditability.
        value = getattr(finance_pack, key)
        path = key
    else:
        path = f"finance_details.portfolio_context.{key}"
    return _MetricEvidence(
        value=value,
        sources=["09_CASHFLOW"],
        paths=[path],
        scope="PORTFOLIO",
        missing_fields=[] if value is not None else [path],
        observed_metrics={
            "months_below_reserve": len(portfolio.get("months_below_reserve") or []),
            "negative_cash_months": len(portfolio.get("negative_cash_months") or []),
            "maximum_reserve_gap": portfolio.get("maximum_reserve_gap"),
            key: value,
        },
        message=(
            "Resolved from the scoped Finance portfolio context derived from 09_CASHFLOW."
            if value is not None
            else "09_CASHFLOW-derived portfolio evidence does not provide this metric."
        ),
    )


def _margin_metric(
    finance_pack: FinanceFeaturePack,
    metric: str,
) -> _MetricEvidence:
    details = finance_pack.finance_details or {}
    contract_finance = details.get("contract_finance") or {}
    contract_economics = (
        contract_finance.get("contract_economics")
        or details.get("contract_economics")
        or {}
    )
    order_allocation = (
        contract_finance.get("order_allocation")
        or details.get("order_allocation")
        or {}
    )
    execution = (
        contract_finance.get("execution_finance")
        or details.get("execution_finance")
        or {}
    )
    if metric == "gross_margin":
        # RR-003's workbook mapping is the contract baseline stored in
        # 04_CONTRACTS.gross_margin, not allocated-order or actual margin.
        metric = "expected_gross_margin_rate"
    if metric == "expected_gross_margin_rate":
        value = contract_economics.get("expected_gross_margin_rate")
        return _MetricEvidence(
            value=value,
            sources=["04_CONTRACTS"],
            paths=["finance_details.contract_economics.expected_gross_margin_rate"],
            scope="CONTRACT_BASELINE",
            record_ids=[finance_pack.contract_id],
            missing_fields=[] if value is not None else [metric],
            observed_metrics={"expected_gross_margin_rate": value},
            message="Resolved as the expected margin rate for the complete contract.",
        )
    if metric == "allocated_order_estimated_margin_rate":
        value = order_allocation.get("allocated_order_margin_rate")
        return _MetricEvidence(
            value=value,
            sources=["06_ORDERS"],
            paths=["finance_details.order_allocation.allocated_order_margin_rate"],
            scope="ALLOCATED_ORDER_ESTIMATE",
            record_ids=[
                value
                for value in finance_pack.source_record_ids
                if str(value).upper().startswith("ORD-")
            ],
            missing_fields=[] if value is not None else [metric],
            observed_metrics={"allocated_order_estimated_margin_rate": value},
            message="Resolved as the estimate for allocated orders only.",
        )
    value = execution.get("actual_margin_rate")
    if value is None:
        # Current packs used this earlier name while explicitly documenting that
        # the actual execution margin is unavailable.
        value = execution.get("current_margin_pct")
    return _MetricEvidence(
        value=value,
        sources=["EXECUTION_ACTUALS"],
        paths=["finance_details.execution_finance.actual_margin_rate"],
        scope="CONTRACT_ACTUAL",
        record_ids=[finance_pack.contract_id],
        missing_fields=[] if value is not None else [metric],
        observed_metrics={"actual_margin_rate": value},
        message=(
            "Resolved as actual execution margin."
            if value is not None
            else "Actual execution margin is not supplied by the current source tables."
        ),
    )


def _transaction_risk_metric(
    transactions: list[BankTransaction],
    *,
    scope: Literal["CONTRACT", "PORTFOLIO"],
) -> _MetricEvidence:
    scored = [
        item for item in transactions if item.transaction_risk_score is not None
    ]
    if not scored:
        return _MetricEvidence(
            sources=["08_BANK_TXN"],
            paths=["08_BANK_TXN.transaction_risk_score"],
            scope=(
                "RELATED_TRANSACTIONS" if scope == "CONTRACT" else "PORTFOLIO_TRANSACTIONS"
            ),
            missing_fields=[
                "related_transaction_risk_score"
                if scope == "CONTRACT"
                else "portfolio_transaction_risk_score"
            ],
            message=(
                "Transactions exist in the applicable scope, but none supplies "
                "transaction_risk_score in 08_BANK_TXN."
            ),
        )
    highest = max(scored, key=lambda item: int(item.transaction_risk_score or 0))
    return _MetricEvidence(
        value=highest.transaction_risk_score,
        sources=["08_BANK_TXN"],
        paths=["08_BANK_TXN.transaction_risk_score"],
        scope=(
            "RELATED_TRANSACTIONS_MAX"
            if scope == "CONTRACT"
            else "PORTFOLIO_TRANSACTIONS_MAX"
        ),
        record_ids=[
            item.txn_id
            for item in scored
            if int(item.transaction_risk_score or 0) >= 85
        ] or [highest.txn_id],
        observed_metrics={"maximum_transaction_risk_score": highest.transaction_risk_score},
        message="Resolved directly from the highest-scoring linked bank transaction.",
    )


def _delivery_delay_metric(
    orders: list[OrderRecord],
    reference_date: date,
) -> _MetricEvidence:
    unfinished = {
        "planned",
        "pending",
        "pending approval",
        "in progress",
        "at risk",
    }
    delayed = [
        (item, (reference_date - item.due_date).days)
        for item in orders
        if item.due_date is not None
        and str(item.status or "").strip().casefold() in unfinished
        and item.due_date < reference_date
    ]
    if not orders:
        return _MetricEvidence(
            sources=["06_ORDERS"],
            paths=["06_ORDERS.due_date", "06_ORDERS.status"],
            scope="CONTRACT_ORDERS",
            missing_fields=["contract_orders"],
            message="No order/progress row exists for this contract in 06_ORDERS.",
        )
    if delayed:
        order, days = max(delayed, key=lambda item: item[1])
        return _MetricEvidence(
            value=days,
            sources=["06_ORDERS"],
            paths=["06_ORDERS.due_date", "06_ORDERS.status"],
            scope="MAX_OPEN_ORDER_DELAY",
            record_ids=[order.order_id],
            message=(
                f"Derived from due_date and unfinished status as of {reference_date.isoformat()}."
            ),
        )
    return _MetricEvidence(
        value=0,
        sources=["06_ORDERS"],
        paths=["06_ORDERS.due_date", "06_ORDERS.status"],
        scope="MAX_OPEN_ORDER_DELAY",
        record_ids=[item.order_id for item in orders],
        message=f"No unfinished order was overdue as of {reference_date.isoformat()}.",
    )


def _resolve_metric(
    finance_pack: FinanceFeaturePack,
    metric: str,
    source_evidence: dict[str, Any],
    rule: RiskRule,
    scope: Literal["CONTRACT", "PORTFOLIO"],
) -> _MetricEvidence:
    if metric == "transaction_risk_score":
        transactions = source_evidence.get(
            "portfolio_bank_transactions"
            if scope == "PORTFOLIO"
            else "bank_transactions",
            [],
        )
        return _transaction_risk_metric(transactions, scope=scope)
    if metric in {"closing_cash", "projected_closing_cash", "cash_reserve_minimum"}:
        return _portfolio_metric(finance_pack, metric)
    if metric == "gross_margin" or metric in _EXPLICIT_MARGIN_METRICS:
        return _margin_metric(finance_pack, metric)
    if metric == "document_sent_to_partner":
        value = finance_pack.document_sent_to_partner
        return _MetricEvidence(
            value=value,
            sources=["BUSINESS_DOCUMENT_SOURCE"],
            paths=["document_sent_to_partner"],
            scope="CONTRACT_DOCUMENT",
            record_ids=[finance_pack.contract_id],
            missing_fields=[] if value is not None else ["document_sent_to_partner"],
            message=(
                "Resolved from supplied contract document evidence."
                if value is not None
                else "The current Supabase schema has no authoritative document_sent_to_partner field."
            ),
        )
    if metric == "requested_amount":
        details = finance_pack.finance_details or {}
        contract_finance = details.get("contract_finance") or {}
        funding_need = (
            contract_finance.get("funding_need")
            or details.get("funding_need")
            or {}
        )
        value = finance_pack.requested_amount
        return _MetricEvidence(
            value=value,
            sources=["FINANCE_FEATURE_PACK"],
            paths=["requested_amount"],
            scope="CONTRACT_FUNDING_NEED",
            record_ids=[finance_pack.contract_id],
            missing_fields=[] if value is not None else [metric],
            observed_metrics={
                "requested_amount": value,
                "requested_amount_status": funding_need.get("requested_amount_status"),
            },
            message="Resolved from the contract-scoped Finance funding need.",
        )
    if metric == "confidence_score":
        details = finance_pack.finance_details or {}
        recommendation = details.get("banking_recommendation") or {}
        value = recommendation.get("confidence_score")
        return _MetricEvidence(
            value=value,
            sources=["DECISION_BANKING_RECOMMENDATION"],
            paths=["finance_details.banking_recommendation.confidence_score"],
            scope="BANKING_RECOMMENDATION",
            record_ids=[finance_pack.contract_id],
            missing_fields=[] if value is not None else ["recommendation_confidence_score"],
            observed_metrics={"recommendation_confidence_score": value},
            configuration_error=value is None,
            message=(
                "Resolved from the generated banking recommendation."
                if value is not None
                else "A banking recommendation exists without its observed confidence score."
            ),
        )
    if metric == "delivery_delay_days":
        return _delivery_delay_metric(
            source_evidence.get("orders", []),
            finance_pack.generated_at.date(),
        )
    details = finance_pack.finance_details or {}
    contract_finance = details.get("contract_finance") or {}
    execution = (
        contract_finance.get("execution_finance")
        or details.get("execution_finance")
        or {}
    )
    if metric in _ACTIVE_EXECUTION_METRICS:
        value = execution.get(metric)
        return _MetricEvidence(
            value=value,
            sources=["FINANCE_FEATURE_PACK"],
            paths=[f"finance_details.execution_finance.{metric}"],
            scope="CONTRACT_EXECUTION",
            record_ids=[finance_pack.contract_id],
            missing_fields=[] if value is not None else [metric],
            message="Resolved from the explicitly scoped execution-finance branch.",
        )
    return _MetricEvidence(
        sources=["13_RISK_RULES"],
        paths=[metric],
        missing_fields=[metric],
        configuration_error=True,
        message="The rule metric has no governed evidence-source mapping.",
    )


def _alert_type_matches(alert_type: str | None, rule: RiskRule) -> bool:
    """Khớp alert_type với risk_type của rule, có tính alias."""
    if not alert_type:
        return False
    observed = alert_type.casefold()
    expected = rule.risk_type.casefold()
    if observed == expected:
        return True
    return observed in _RISK_TYPE_ALIASES.get(expected, set())


def _rule_scopes(rule: RiskRule) -> tuple[Literal["CONTRACT", "PORTFOLIO"], ...]:
    if rule.rule_id == "RR-001":
        return ("CONTRACT", "PORTFOLIO")
    if rule.rule_id == "RR-002":
        return ("PORTFOLIO",)
    return ("CONTRACT",)


def _approval_action(required_action: str) -> bool:
    action = required_action.casefold()
    return any(word in action for word in ("approval", "founder", "human"))


def _masked_metrics(masker: Masker, metrics: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "metric": key,
            "value": (
                masker.mask_field_value(key, value) if value is not None else None
            ),
        }
        for key, value in metrics.items()
    ]


def _applicability_result(
    rule: RiskRule,
    finance_pack: FinanceFeaturePack,
    source_evidence: dict[str, Any],
    scope: Literal["CONTRACT", "PORTFOLIO"],
) -> tuple[Literal["NOT_APPLICABLE", "RULE_CONFIGURATION_ERROR"], str] | None:
    """Check applicability before looking for a metric value."""
    if rule.rule_id == "RR-001":
        key = (
            "portfolio_bank_transactions"
            if scope == "PORTFOLIO"
            else "bank_transactions"
        )
        if not source_evidence.get(key):
            reason = (
                "No contract-linked transaction exists."
                if scope == "CONTRACT"
                else "No portfolio transaction exists."
            )
            return "NOT_APPLICABLE", reason
    if rule.rule_id == "RR-004" and finance_pack.document_sent_to_partner is None:
        details = finance_pack.finance_details or {}
        workflow = details.get("workflow_context") or {}
        if workflow.get("preparing_partner_submission") is True:
            return (
                "RULE_CONFIGURATION_ERROR",
                "Partner submission is being prepared but document_sent_to_partner "
                "has no governed source mapping.",
            )
        return "NOT_APPLICABLE", "No partner-document release action exists in this run."
    if rule.rule_id == "RR-005" and finance_pack.requested_amount is None:
        return "NOT_APPLICABLE", "No contract-specific funding request exists."
    if rule.rule_id == "RR-006":
        recommendation = (
            (finance_pack.finance_details or {}).get("banking_recommendation")
        )
        if not recommendation:
            return "NOT_APPLICABLE", "No banking recommendation has been generated."
        if recommendation.get("confidence_score") is None:
            return (
                "RULE_CONFIGURATION_ERROR",
                "A banking recommendation exists without an observed confidence score.",
            )
    if rule.rule_id == "RR-007" and not source_evidence.get("orders"):
        return "NOT_APPLICABLE", "No contract delivery/order exists to assess delay."
    return None


def _evaluate_finance_rule(
    rule: RiskRule,
    finance_pack: FinanceFeaturePack,
    masker: Masker,
    source_evidence: dict[str, Any],
    scope: Literal["CONTRACT", "PORTFOLIO"],
) -> RuleEvaluation:
    applicability = _applicability_result(
        rule,
        finance_pack,
        source_evidence,
        scope,
    )
    if applicability is not None:
        status, message = applicability
        return RuleEvaluation(
            rule_id=rule.rule_id,
            scope=scope,
            owner_agent=rule.owner_agent,
            severity=rule.severity,
            status=status,
            required_action=rule.required_action,
            evidence_sources=["13_RISK_RULES"],
            evidence_paths=["13_RISK_RULES.trigger_condition"],
            evidence_scope=scope,
            message=message,
        )
    match = _CONDITION.match(rule.trigger_condition)
    if not match:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            scope=scope,
            owner_agent=rule.owner_agent,
            severity=rule.severity,
            status="RULE_CONFIGURATION_ERROR",
            required_action=rule.required_action,
            missing_fields=["parseable_trigger_condition"],
            evidence_sources=["13_RISK_RULES"],
            evidence_paths=["13_RISK_RULES.trigger_condition"],
            evidence_scope="RULE_CONFIGURATION",
            message="The rule condition cannot be parsed safely.",
        )

    metric = match.group("metric").lower()
    comparison_operator = match.group("operator")
    target_text = match.group("target")
    observed_evidence = _resolve_metric(
        finance_pack,
        metric,
        source_evidence,
        rule,
        scope,
    )
    observed = observed_evidence.value
    literal_target = _parse_literal(target_text)
    target_evidence = (
        _resolve_metric(
            finance_pack,
            literal_target,
            source_evidence,
            rule,
            scope,
        )
        if isinstance(literal_target, str)
        else None
    )
    target = target_evidence.value if target_evidence is not None else literal_target

    missing_fields = list(observed_evidence.missing_fields)
    if observed is None and not missing_fields:
        missing_fields.append(metric)
    if target_evidence is not None:
        missing_fields.extend(target_evidence.missing_fields)
        if target is None and not target_evidence.missing_fields:
            missing_fields.append(literal_target)
    sources = list(dict.fromkeys([
        *observed_evidence.sources,
        *(target_evidence.sources if target_evidence else []),
    ]))
    paths = list(dict.fromkeys([
        *observed_evidence.paths,
        *(target_evidence.paths if target_evidence else []),
    ]))
    record_ids = list(dict.fromkeys([
        *observed_evidence.record_ids,
        *(target_evidence.record_ids if target_evidence else []),
    ]))
    configuration_error = observed_evidence.configuration_error or bool(
        target_evidence and target_evidence.configuration_error
    )
    if missing_fields:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            scope=scope,
            owner_agent=rule.owner_agent,
            severity=rule.severity,
            status=(
                "RULE_CONFIGURATION_ERROR"
                if configuration_error
                else "INSUFFICIENT_EVIDENCE"
            ),
            observed_value=masker.mask_field_value(metric, observed),
            required_action=rule.required_action,
            missing_fields=sorted(set(missing_fields)),
            evidence_sources=sources,
            evidence_paths=paths,
            evidence_scope=observed_evidence.scope,
            evidence_record_ids=_masked_record_ids(masker, record_ids),
            observed_metrics=_masked_metrics(
                masker,
                observed_evidence.observed_metrics,
            ),
            comparison_operator=comparison_operator,
            comparison_value=str(target) if target is not None else None,
            message=observed_evidence.message,
        )

    try:
        triggered = _OPERATORS[comparison_operator](observed, target)
    except TypeError:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            scope=scope,
            owner_agent=rule.owner_agent,
            severity=rule.severity,
            status="RULE_CONFIGURATION_ERROR",
            observed_value=masker.mask_field_value(metric, observed),
            required_action=rule.required_action,
            missing_fields=[f"comparable_{metric}"],
            evidence_sources=sources,
            evidence_paths=paths,
            evidence_scope=observed_evidence.scope,
            evidence_record_ids=_masked_record_ids(masker, record_ids),
            observed_metrics=_masked_metrics(
                masker,
                observed_evidence.observed_metrics,
            ),
            comparison_operator=comparison_operator,
            comparison_value=str(target),
            message="The observed and comparison values are not comparable.",
        )

    masked_observed = masker.mask_field_value(metric, observed)
    masked_record_ids = _masked_record_ids(masker, record_ids)
    findings = []
    if triggered:
        findings.append(RiskFinding(
            rule_id=rule.rule_id,
            risk_type=rule.risk_type,
            severity=rule.severity,
            trigger_condition=rule.trigger_condition,
            required_action=rule.required_action,
            owner_agent=rule.owner_agent,
            source_table=sources[0] if sources else "UNKNOWN",
            record_id=(
                ", ".join(masked_record_ids)
                or masker.mask_identifier_text(
                    finance_pack.contract_id,
                    "contract_id",
                )
                or finance_pack.contract_id
            ),
            observed_metric=metric,
            observed_value=str(masked_observed),
            comparison_operator=comparison_operator,
            comparison_value=str(target),
            human_approval_required=_approval_action(rule.required_action),
        ))
    return RuleEvaluation(
        rule_id=rule.rule_id,
        scope=scope,
        owner_agent=rule.owner_agent,
        severity=rule.severity,
        status="TRIGGERED" if triggered else "NOT_TRIGGERED",
        observed_value=masked_observed,
        required_action=rule.required_action,
        findings=findings,
        evidence_sources=sources,
        evidence_paths=paths,
        evidence_scope=observed_evidence.scope,
        evidence_record_ids=masked_record_ids,
        observed_metrics=_masked_metrics(
            masker,
            observed_evidence.observed_metrics,
        ),
        comparison_operator=comparison_operator,
        comparison_value=str(target),
        message=(
            f"{observed_evidence.message} The governed evidence satisfies the rule condition."
            if triggered
            else f"{observed_evidence.message} The governed evidence does not satisfy the rule condition."
        ),
    )


def _match_finance_pack_alerts(
    finance_pack: FinanceFeaturePack,
    rules: list[RiskRule],
    evaluations: list[RuleEvaluation],
    masker: Masker,
) -> list[RiskAlertMatch]:
    triggered_ids = {
        evaluation.rule_id
        for evaluation in evaluations
        if evaluation.status == "TRIGGERED"
    }
    triggered_rules = {rule.rule_id: rule for rule in rules if rule.rule_id in triggered_ids}
    source_ids = set(finance_pack.source_record_ids)
    matches: list[RiskAlertMatch] = []

    for alert in get_alerts_impl():
        record_match = bool(_related_records(alert.related_record) & source_ids)
        type_rule_ids = sorted(
            rule_id
            for rule_id, rule in triggered_rules.items()
            if _alert_type_matches(alert.alert_type, rule)
        )
        if not record_match and not type_rule_ids:
            continue

        match_basis: Literal["RELATED_RECORD", "EXACT_RISK_TYPE"] = (
            "RELATED_RECORD" if record_match else "EXACT_RISK_TYPE"
        )
        matches.append(
            RiskAlertMatch(
                alert=masker.mask_alert(alert),
                matched_rule_ids=type_rule_ids,
                match_basis=match_basis,
            )
        )
    return matches


def _build_proposed_alert(
    rule: RiskRule,
    evaluation: RuleEvaluation,
    finance_pack: FinanceFeaturePack,
    masker: Masker,
) -> ProposedAlert:
    """Tạo proposed alert cho một rule TRIGGERED chưa có alert khớp trong 14_ALERTS."""
    related = list(evaluation.evidence_record_ids)
    if not related:
        related = [
            masked
            for record in finance_pack.source_record_ids
            if (masked := masker.mask_identifier_text(record, "source_record"))
        ]
    contract_token = (
        masker.mask_identifier_text(finance_pack.contract_id, "contract_id")
        or finance_pack.contract_id
    )
    return ProposedAlert(
        proposed_alert_id=f"PAL-{contract_token}-{rule.rule_id}",
        rule_id=rule.rule_id,
        risk_type=rule.risk_type,
        severity=rule.severity,
        recommended_action=rule.required_action,
        reason_for_proposal="Rule triggered but no alert mapping found in 14_ALERTS",
        related_records=related,
    )


def _requires_human_approval(evaluation: RuleEvaluation) -> bool:
    return evaluation.status == "TRIGGERED" and _approval_action(
        evaluation.required_action
    )


def build_risk_pack_impl(
    finance_pack: FinanceFeaturePack,
    source_evidence: dict[str, Any] | None = None,
) -> RiskPack:
    """Build one contract-scoped Risk Pack from governed source evidence."""
    masker = Masker(get_data_classes_impl())
    rules = get_risk_rules_impl()
    if source_evidence is None:
        source_evidence = load_risk_source_evidence_impl(finance_pack)
    rule_by_id = {rule.rule_id: rule for rule in rules}
    evaluations = [
        _evaluate_finance_rule(
            rule,
            finance_pack,
            masker,
            source_evidence,
            scope,
        )
        for rule in rules
        for scope in _rule_scopes(rule)
    ]
    triggered = [item for item in evaluations if item.status == "TRIGGERED"]
    insufficient = [
        item for item in evaluations if item.status == "INSUFFICIENT_EVIDENCE"
    ]
    configuration_errors = [
        item for item in evaluations if item.status == "RULE_CONFIGURATION_ERROR"
    ]
    unresolved = [*insufficient, *configuration_errors]
    risk_assessment_status = "INCOMPLETE" if unresolved else "COMPLETE"
    contract_triggered = [item for item in triggered if item.scope == "CONTRACT"]
    portfolio_triggered = [item for item in triggered if item.scope == "PORTFOLIO"]
    contract_severities = [
        item.severity for item in contract_triggered if item.severity is not None
    ]
    portfolio_severities = [
        item.severity for item in portfolio_triggered if item.severity is not None
    ]
    severities = [*contract_severities, *portfolio_severities]
    highest_contract_severity = (
        max(contract_severities, key=_SEVERITY_RANK.__getitem__)
        if contract_severities
        else None
    )
    highest_portfolio_severity = (
        max(portfolio_severities, key=_SEVERITY_RANK.__getitem__)
        if portfolio_severities
        else None
    )
    # Contract and portfolio scopes are deliberately not collapsed into a
    # synthetic global risk conclusion.
    overall_risk_level = None
    required_actions = list(
        dict.fromkeys(
            item.required_action for item in triggered if item.required_action
        )
    )
    insufficient_evidence = [
        f"{item.rule_id}:{field_name}"
        for item in insufficient
        for field_name in item.missing_fields
    ]
    unresolved_severities = [
        item.severity for item in unresolved if item.severity is not None
    ]
    priority_candidates = [*severities, *unresolved_severities]
    review_priority = (
        max(priority_candidates, key=_SEVERITY_RANK.__getitem__)
        if priority_candidates
        else Severity.LOW
    )
    # Missing evidence for a Critical rule means urgent review, not a concluded
    # CRITICAL risk level. Cap the incomplete-assessment priority at HIGH.
    if risk_assessment_status == "INCOMPLETE" and review_priority is Severity.CRITICAL:
        review_priority = Severity.HIGH

    alert_matches = _match_finance_pack_alerts(finance_pack, rules, evaluations, masker)
    covered_rule_ids = {
        rule_id for match in alert_matches for rule_id in match.matched_rule_ids
    }
    uncovered = [item for item in triggered if item.rule_id not in covered_rule_ids]
    proposed_alerts = [
        _build_proposed_alert(
            rule_by_id[item.rule_id],
            item,
            finance_pack,
            masker,
        )
        for item in uncovered
        if item.rule_id in rule_by_id
    ]

    triggered_rule_approval_required = any(
        _requires_human_approval(item) for item in evaluations
    )
    portfolio_transaction_approval_evaluations = [
        item
        for item in portfolio_triggered
        if item.rule_id == "RR-001" and _requires_human_approval(item)
    ]
    portfolio_transaction_approval_object_ids = list(dict.fromkeys(
        record_id
        for item in portfolio_transaction_approval_evaluations
        for record_id in item.evidence_record_ids
    ))
    manual_evidence_review_required = bool(insufficient) or bool(proposed_alerts)

    triggered_rule_ids = list(dict.fromkeys(item.rule_id for item in triggered))
    contract_triggered_rule_ids = list(dict.fromkeys(
        item.rule_id for item in contract_triggered
    ))
    portfolio_triggered_rule_ids = list(dict.fromkeys(
        item.rule_id for item in portfolio_triggered
    ))
    highest_severity = (
        max(severities, key=_SEVERITY_RANK.__getitem__) if severities else None
    )

    summary = RiskPackSummary(
        total_rules_triggered=len(triggered),
        triggered_rule_ids=triggered_rule_ids,
        total_alerts_detected=len(alert_matches),
        total_proposed_alerts=len(proposed_alerts),
        unmapped_rule_ids=[item.rule_id for item in uncovered],
        highest_severity=highest_severity,
        highest_contract_triggered_severity=highest_contract_severity,
        highest_portfolio_triggered_severity=highest_portfolio_severity,
        human_review_required=(
            triggered_rule_approval_required or manual_evidence_review_required
        ),
        triggered_rule_approval_required=triggered_rule_approval_required,
        manual_evidence_review_required=manual_evidence_review_required,
    )
    masked_data = MaskedDataSummary(
        masking_applied=bool(masker.masked_fields),
        masked_fields=masker.masked_fields,
    )

    return RiskPack(
        case_id=finance_pack.case_id,
        contract_id=finance_pack.contract_id,
        generated_at=datetime.now(UTC),
        risk_assessment_status=risk_assessment_status,
        overall_risk_level=overall_risk_level,
        review_priority=review_priority,
        rule_evaluations=evaluations,
        triggered_rule_ids=triggered_rule_ids,
        contract_triggered_rule_ids=contract_triggered_rule_ids,
        portfolio_triggered_rule_ids=portfolio_triggered_rule_ids,
        highest_contract_triggered_severity=highest_contract_severity,
        highest_portfolio_triggered_severity=highest_portfolio_severity,
        alerts=alert_matches,
        proposed_alerts=proposed_alerts,
        required_actions=required_actions,
        insufficient_evidence=insufficient_evidence,
        rule_configuration_error_ids=list(dict.fromkeys(
            item.rule_id for item in configuration_errors
        )),
        portfolio_transaction_approval_required=bool(
            portfolio_transaction_approval_evaluations
        ),
        portfolio_transaction_approval_object_ids=(
            portfolio_transaction_approval_object_ids
        ),
        triggered_rule_approval_required=triggered_rule_approval_required,
        manual_evidence_review_required=manual_evidence_review_required,
        human_approval_required=triggered_rule_approval_required,
        masked_data=masked_data,
        summary=summary,
        handoff_summary=(
            f"Risk assessment {risk_assessment_status}; "
            "global risk level NOT_AGGREGATED; "
            f"contract severity "
            f"{highest_contract_severity.value if highest_contract_severity else 'NONE'}; "
            f"portfolio severity "
            f"{highest_portfolio_severity.value if highest_portfolio_severity else 'NONE'}; "
            f"review priority {review_priority.value}; "
            f"{len(triggered)} rules triggered; "
            f"{len(insufficient_evidence)} evidence gaps; "
            f"human review {'required' if summary.human_review_required else 'not required'}."
        ),
        decision_made_by_risk_agent=False,
    )


@function_tool(strict_mode=False)
def build_risk_pack(finance_pack: FinanceFeaturePack) -> str:
    """Build one masked RiskPack JSON for the supplied FinanceFeaturePack.

    The tool loads every organizer-provided RR rule, existing alerts, and
    data classification policy from PostgreSQL, evaluates every active rule
    against explicitly scoped Finance metrics plus contract-linked 08_BANK_TXN
    and 06_ORDERS evidence, matches existing alerts (with
    risk-type aliases),
    proposes alerts for triggered rules that have no mapping, masks restricted and
    confidential fields per 20_DATA_CLASS, and reports overall severity, required
    actions, missing evidence, a summary, and whether human approval is required,
    then returns formatted JSON. Call it once per case.
    """
    return build_risk_pack_impl(finance_pack).model_dump_json(indent=2)
