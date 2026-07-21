"""Build one masked Risk Pack from a Finance Feature Pack."""

from __future__ import annotations

import operator
import re
from datetime import UTC, datetime
from typing import Any, Callable, Literal

from agents import function_tool

from app.schema.handoff_packs import (
    FinanceFeaturePack,
    MaskedDataSummary,
    ProposedAlert,
    RiskAlertMatch,
    RiskPack,
    RiskPackSummary,
    RuleEvaluation,
    Severity,
)
from app.schema.risk_db_models import RiskRule
from app.tools.RiskAgent.GetRiskControls import (
    DISABLED_RISK_RULE_IDS,
    get_alerts_impl,
    get_data_classes_impl,
    get_risk_rules_impl,
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


def _pack_value(finance_pack: FinanceFeaturePack, metric: str) -> Any:
    field_name = _METRIC_FIELDS.get(metric)
    return getattr(finance_pack, field_name) if field_name else None


def _alert_type_matches(alert_type: str | None, rule: RiskRule) -> bool:
    """Khớp alert_type với risk_type của rule, có tính alias."""
    if not alert_type:
        return False
    observed = alert_type.casefold()
    expected = rule.risk_type.casefold()
    if observed == expected:
        return True
    return observed in _RISK_TYPE_ALIASES.get(expected, set())


def _evaluate_finance_rule(
    rule: RiskRule, finance_pack: FinanceFeaturePack, masker: Masker
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
            observed_value=masker.mask_field_value(metric, observed),
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
            observed_value=masker.mask_field_value(metric, observed),
            required_action=rule.required_action,
            missing_fields=[f"comparable_{metric}"],
            message="The observed and comparison values are not comparable.",
        )

    return RuleEvaluation(
        rule_id=rule.rule_id,
        owner_agent=rule.owner_agent,
        severity=rule.severity,
        status="TRIGGERED" if triggered else "NOT_TRIGGERED",
        observed_value=masker.mask_field_value(metric, observed),
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
    rule: RiskRule, finance_pack: FinanceFeaturePack, masker: Masker
) -> ProposedAlert:
    """Tạo proposed alert cho một rule TRIGGERED chưa có alert khớp trong 14_ALERTS."""
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
    action = evaluation.required_action.casefold()
    return evaluation.status == "TRIGGERED" and (
        evaluation.severity in {Severity.HIGH, Severity.CRITICAL}
        or any(word in action for word in ("approval", "founder", "human"))
    )


def build_risk_pack_impl(finance_pack: FinanceFeaturePack) -> RiskPack:
    """Build one contract-scoped Risk Pack from a Finance Feature Pack."""
    masker = Masker(get_data_classes_impl())
    rules = [
        rule
        for rule in get_risk_rules_impl()
        if rule.rule_id not in DISABLED_RISK_RULE_IDS
    ]
    rule_by_id = {rule.rule_id: rule for rule in rules}
    evaluations = [_evaluate_finance_rule(rule, finance_pack, masker) for rule in rules]
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

    alert_matches = _match_finance_pack_alerts(finance_pack, rules, evaluations, masker)
    covered_rule_ids = {
        rule_id for match in alert_matches for rule_id in match.matched_rule_ids
    }
    uncovered = [item for item in triggered if item.rule_id not in covered_rule_ids]
    proposed_alerts = [
        _build_proposed_alert(rule_by_id[item.rule_id], finance_pack, masker)
        for item in uncovered
        if item.rule_id in rule_by_id
    ]

    human_approval_required = any(_requires_human_approval(item) for item in evaluations)

    summary = RiskPackSummary(
        total_rules_triggered=len(triggered),
        triggered_rule_ids=[item.rule_id for item in triggered],
        total_alerts_detected=len(alert_matches),
        total_proposed_alerts=len(proposed_alerts),
        unmapped_rule_ids=[item.rule_id for item in uncovered],
        highest_severity=overall_risk_level,
        human_review_required=human_approval_required or bool(proposed_alerts),
    )
    masked_data = MaskedDataSummary(
        masking_applied=bool(masker.masked_fields),
        masked_fields=masker.masked_fields,
    )

    return RiskPack(
        case_id=finance_pack.case_id,
        contract_id=finance_pack.contract_id,
        generated_at=datetime.now(UTC),
        overall_risk_level=overall_risk_level,
        rule_evaluations=evaluations,
        triggered_rule_ids=[item.rule_id for item in triggered],
        alerts=alert_matches,
        proposed_alerts=proposed_alerts,
        required_actions=required_actions,
        insufficient_evidence=insufficient_evidence,
        human_approval_required=human_approval_required,
        masked_data=masked_data,
        summary=summary,
        handoff_summary=(
            f"Risk level {overall_risk_level.value if overall_risk_level else 'NONE'}; "
            f"{len(triggered)} rules triggered; "
            f"{len(insufficient_evidence)} evidence gaps; "
            f"human review {'required' if summary.human_review_required else 'not required'}."
        ),
        decision_made_by_risk_agent=False,
    )


@function_tool(strict_mode=False)
def build_risk_pack(finance_pack: FinanceFeaturePack) -> str:
    """Build one masked RiskPack JSON for the supplied FinanceFeaturePack.

    The tool loads all active organizer-provided RR rules, existing alerts, and
    data classification policy from PostgreSQL, evaluates every active rule
    against the supplied contract metrics, matches existing alerts (with
    risk-type aliases),
    proposes alerts for triggered rules that have no mapping, masks restricted and
    confidential fields per 20_DATA_CLASS, and reports overall severity, required
    actions, missing evidence, a summary, and whether human approval is required,
    then returns formatted JSON. Call it once per case.
    """
    return build_risk_pack_impl(finance_pack).model_dump_json(indent=2)
