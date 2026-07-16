"""Evaluate organizer-provided RR rules against organizer-provided DB data."""

from __future__ import annotations

import operator
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from agents import function_tool

from app.schema.risk_db_models import RiskEvaluationReport, RiskRule
from app.schema.handoff_packs import RiskFinding, RuleEvaluation
from app.tools.RiskAgent.GetBankTransactions import get_bank_transactions_impl
from app.tools.RiskAgent.GetFinancialRiskData import (
    get_cashflows_impl,
    get_contracts_impl,
    get_credit_profiles_impl,
)
from app.tools.RiskAgent.GetRiskControls import get_risk_rules_impl
from app.tools.RiskAgent._masking import mask_evaluation

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
_METRIC_ALIASES = {"closing_cash": "projected_closing_cash"}


def _human_approval_required(rule: RiskRule) -> bool:
    text = f"{rule.required_action} {rule.risk_type}".lower()
    return "approval" in text or "founder" in text or "human" in text


def _parse_literal(value: str) -> Decimal | bool | str:
    normalized = value.strip()
    if normalized.lower() in {"true", "false"}:
        return normalized.lower() == "true"
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return normalized


def _source_records(metric: str) -> tuple[str, str, list[tuple[str, dict[str, Any]]]] | None:
    if metric == "transaction_risk_score":
        return (
            "bank_txn",
            "txn_id",
            [(row.txn_id, row.model_dump()) for row in get_bank_transactions_impl()],
        )
    if metric == "closing_cash":
        return (
            "cashflow",
            "month",
            [(row.month, row.model_dump()) for row in get_cashflows_impl()],
        )
    if metric == "gross_margin":
        return (
            "contract",
            "contract_id",
            [(row.contract_id, row.model_dump()) for row in get_contracts_impl()],
        )
    if metric == "requested_amount":
        return (
            "credit_profile",
            "credit_case_id",
            [
                (row.credit_case_id, row.model_dump())
                for row in get_credit_profiles_impl()
            ],
        )
    return None


def _evaluate_rule(rule: RiskRule) -> RuleEvaluation:
    match = _CONDITION.match(rule.trigger_condition)
    if not match:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            status="INSUFFICIENT_EVIDENCE",
            missing_fields=["parseable_trigger_condition"],
            message="The DB trigger_condition cannot be parsed safely.",
        )

    metric = match.group("metric").lower()
    comparison_operator = match.group("operator")
    target_text = match.group("target")
    source = _source_records(metric)
    if source is None:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            status="INSUFFICIENT_EVIDENCE",
            missing_fields=[metric],
            message=f"No organizer-provided DB column supplies {metric}.",
        )

    table_name, _, records = source
    if not records:
        return RuleEvaluation(
            rule_id=rule.rule_id,
            status="INSUFFICIENT_EVIDENCE",
            missing_fields=[table_name],
            message=f"The organizer-provided {table_name} table has no rows.",
        )

    observed_field = _METRIC_ALIASES.get(metric, metric)
    literal_target = _parse_literal(target_text)
    findings: list[RiskFinding] = []
    missing_fields: set[str] = set()
    for record_id, row in records:
        observed = row.get(observed_field)
        target = row.get(target_text) if isinstance(literal_target, str) else literal_target
        if observed is None:
            missing_fields.add(observed_field)
            continue
        if target is None:
            missing_fields.add(target_text)
            continue
        try:
            triggered = _OPERATORS[comparison_operator](observed, target)
        except TypeError:
            missing_fields.add(f"comparable_{metric}")
            continue
        if triggered:
            findings.append(
                RiskFinding(
                    rule_id=rule.rule_id,
                    risk_type=rule.risk_type,
                    severity=rule.severity,
                    trigger_condition=rule.trigger_condition,
                    required_action=rule.required_action,
                    owner_agent=rule.owner_agent,
                    source_table=table_name,
                    record_id=record_id,
                    observed_metric=metric,
                    observed_value=str(observed),
                    comparison_operator=comparison_operator,
                    comparison_value=str(target),
                    human_approval_required=_human_approval_required(rule),
                )
            )

    if findings:
        status = "TRIGGERED"
        message = f"{len(findings)} DB record(s) satisfy {rule.trigger_condition}."
    elif missing_fields:
        status = "INSUFFICIENT_EVIDENCE"
        message = "Required DB values are missing; the rule was not assumed false."
    else:
        status = "NOT_TRIGGERED"
        message = f"No DB record satisfies {rule.trigger_condition}."
    return RuleEvaluation(
        rule_id=rule.rule_id,
        status=status,
        findings=findings,
        missing_fields=sorted(missing_fields),
        message=message,
    )


def evaluate_risks_impl() -> RiskEvaluationReport:
    evaluations = [_evaluate_rule(rule) for rule in get_risk_rules_impl()]
    triggered_rule_ids = [
        evaluation.rule_id
        for evaluation in evaluations
        if evaluation.status == "TRIGGERED"
    ]
    return RiskEvaluationReport(
        evaluated_at=datetime.now(UTC),
        evaluations=evaluations,
        triggered_rule_ids=triggered_rule_ids,
        human_approval_required=any(
            finding.human_approval_required
            for evaluation in evaluations
            for finding in evaluation.findings
        ),
        source_tables=[
            "risk_rule",
            "bank_txn",
            "cashflow",
            "contract",
            "credit_profile",
        ],
    )


@function_tool
def evaluate_risks() -> RiskEvaluationReport:
    """Evaluate every RR rule using only fields present in the organizer DB."""
    return mask_evaluation(evaluate_risks_impl())


if __name__ == "__main__":
    print(mask_evaluation(evaluate_risks_impl()).model_dump_json(indent=2))
