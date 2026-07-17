"""Build one masked Risk Pack from a Finance Feature Pack."""

from __future__ import annotations

import operator
import re
from datetime import UTC, datetime
from typing import Any, Callable, Literal

from agents import function_tool

from app.schema.handoff_packs import (
    FinanceFeaturePack,
    RiskAlertMatch,
    RiskPack,
    RuleEvaluation,
    Severity,
)
from app.schema.risk_db_models import RiskRule
from app.tools.RiskAgent.GetRiskControls import (
    get_alerts_impl,
    get_risk_rules_impl,
)
from app.tools.RiskAgent._masking import mask_alert

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
_METRIC_FIELDS = {
    "transaction_risk_score": "transaction_risk_score",
    "closing_cash": "projected_closing_cash",
    "projected_closing_cash": "projected_closing_cash",
    "cash_reserve_minimum": "cash_reserve_minimum",
    "gross_margin": "gross_margin",
    "document_sent_to_partner": "document_sent_to_partner",
    "requested_amount": "requested_amount",
    "confidence_score": "confidence_score",
    "delivery_delay_days": "delivery_delay_days",
}
_CONFIDENTIAL_METRICS = {
    "closing_cash",
    "projected_closing_cash",
    "cash_reserve_minimum",
    "gross_margin",
    "requested_amount",
}
_SEVERITY_RANK = {
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
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


def _pack_value(finance_pack: FinanceFeaturePack, metric: str) -> Any:
    field_name = _METRIC_FIELDS.get(metric)
    return getattr(finance_pack, field_name) if field_name else None


def _masked_value(metric: str, value: Any) -> str | None:
    if value is None:
        return None
    if metric in _CONFIDENTIAL_METRICS:
        return "[CONFIDENTIAL_VALUE]"
    return str(value)


def _evaluate_finance_rule(
    rule: RiskRule, finance_pack: FinanceFeaturePack
) -> RuleEvaluation:
    match = _CONDITION.match(rule.trigger_condition)
    if not match:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            owner_agent=rule.owner_agent,
            severity=rule.severity,
            status="INSUFFICIENT_EVIDENCE",
            required_action=rule.required_action,
            missing_fields=["parseable_trigger_condition"],
            message="The rule condition cannot be parsed safely.",
        )

    metric = match.group("metric").lower()
    comparison_operator = match.group("operator")
    target_text = match.group("target")
    observed = _pack_value(finance_pack, metric)
    literal_target = _parse_literal(target_text)
    target = (
        _pack_value(finance_pack, literal_target)
        if isinstance(literal_target, str)
        else literal_target
    )

    missing_fields: list[str] = []
    if metric not in _METRIC_FIELDS or observed is None:
        missing_fields.append(_METRIC_FIELDS.get(metric, metric))
    if isinstance(literal_target, str) and target is None:
        missing_fields.append(_METRIC_FIELDS.get(literal_target, literal_target))
    if missing_fields:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            owner_agent=rule.owner_agent,
            severity=rule.severity,
            status="INSUFFICIENT_EVIDENCE",
            observed_value=_masked_value(metric, observed),
            required_action=rule.required_action,
            missing_fields=sorted(set(missing_fields)),
            message="Finance Feature Pack does not contain enough evidence.",
        )

    try:
        triggered = _OPERATORS[comparison_operator](observed, target)
    except TypeError:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            owner_agent=rule.owner_agent,
            severity=rule.severity,
            status="INSUFFICIENT_EVIDENCE",
            observed_value=_masked_value(metric, observed),
            required_action=rule.required_action,
            missing_fields=[f"comparable_{metric}"],
            message="The observed and comparison values are not comparable.",
        )

    return RuleEvaluation(
        rule_id=rule.rule_id,
        owner_agent=rule.owner_agent,
        severity=rule.severity,
        status="TRIGGERED" if triggered else "NOT_TRIGGERED",
        observed_value=_masked_value(metric, observed),
        required_action=rule.required_action,
        message=(
            "The Finance Feature Pack satisfies the rule condition."
            if triggered
            else "The Finance Feature Pack does not satisfy the rule condition."
        ),
    )


def _match_finance_pack_alerts(
    finance_pack: FinanceFeaturePack,
    rules: list[RiskRule],
    evaluations: list[RuleEvaluation],
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
            if alert.alert_type
            and alert.alert_type.casefold() == rule.risk_type.casefold()
        )
        if not record_match and not type_rule_ids:
            continue

        match_basis: Literal["RELATED_RECORD", "EXACT_RISK_TYPE"] = (
            "RELATED_RECORD" if record_match else "EXACT_RISK_TYPE"
        )
        matches.append(
            RiskAlertMatch(
                alert=mask_alert(alert),
                matched_rule_ids=type_rule_ids,
                match_basis=match_basis,
            )
        )
    return matches


def _requires_human_approval(evaluation: RuleEvaluation) -> bool:
    action = evaluation.required_action.casefold()
    return evaluation.status == "TRIGGERED" and (
        evaluation.severity in {Severity.HIGH, Severity.CRITICAL}
        or any(word in action for word in ("approval", "founder", "human"))
    )


def build_risk_pack_impl(finance_pack: FinanceFeaturePack) -> RiskPack:
    """Build one contract-scoped Risk Pack from a Finance Feature Pack."""
    rules = get_risk_rules_impl()
    evaluations = [_evaluate_finance_rule(rule, finance_pack) for rule in rules]
    triggered = [item for item in evaluations if item.status == "TRIGGERED"]
    severities = [item.severity for item in triggered if item.severity is not None]
    overall_risk_level = (
        max(severities, key=_SEVERITY_RANK.__getitem__) if severities else None
    )
    required_actions = list(
        dict.fromkeys(
            item.required_action for item in triggered if item.required_action
        )
    )
    insufficient_evidence = [
        f"{item.rule_id}:{field_name}"
        for item in evaluations
        if item.status == "INSUFFICIENT_EVIDENCE"
        for field_name in item.missing_fields
    ]

    return RiskPack(
        case_id=finance_pack.case_id,
        contract_id=finance_pack.contract_id,
        generated_at=datetime.now(UTC),
        overall_risk_level=overall_risk_level,
        rule_evaluations=evaluations,
        triggered_rule_ids=[item.rule_id for item in triggered],
        alerts=_match_finance_pack_alerts(finance_pack, rules, evaluations),
        required_actions=required_actions,
        insufficient_evidence=insufficient_evidence,
        human_approval_required=any(
            _requires_human_approval(item) for item in evaluations
        ),
        decision_made_by_risk_agent=False,
    )


@function_tool
def build_risk_pack(finance_pack: FinanceFeaturePack) -> str:
    """Build one masked RiskPack JSON for the supplied FinanceFeaturePack.

    The tool loads all organizer-provided RR rules and existing alerts from
    PostgreSQL, evaluates every rule against the supplied contract metrics, and
    reports triggered rules, missing evidence, required actions, overall
    severity, and whether human approval is required, then returns formatted
    JSON. Call it once per case.
    """
    return build_risk_pack_impl(finance_pack).model_dump_json(indent=2)
