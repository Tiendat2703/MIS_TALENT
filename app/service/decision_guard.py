"""Deterministic checks around LLM-produced Decision batches."""

from __future__ import annotations

from typing import Any

from app.schema.decisionAgent import (
    DecisionBatchOutput,
    DecisionStatus,
    RecommendedOption,
)
from app.schema.handoff_packs import FinanceBatchPack, RiskBatchPack, RiskPack
from app.schema.risk_db_models import CreditProfile
from app.service.credit_profile import resolve_contract_funding_need


def validate_decision_finance_consistency(
    batch: DecisionBatchOutput,
    finance_batch: FinanceBatchPack,
    credit_profiles: dict[str, CreditProfile],
) -> None:
    """Validate capital need against Credit Profile -> contract fallback rules."""
    decisions = {item.contract_id: item for item in batch.decisions}
    expected_ids = finance_batch.contract_ids
    if list(decisions) != expected_ids:
        raise ValueError(
            "Decision contracts do not match FinanceBatchPack order: "
            f"expected={expected_ids}, returned={list(decisions)}"
        )

    for finance in finance_batch.packs:
        decision = decisions[finance.contract_id]
        funding_need = resolve_contract_funding_need(
            finance,
            credit_profiles.get(finance.contract_id),
        )
        requested_amount = (
            funding_need.get("requested_amount") if funding_need is not None else None
        )
        funding_source = (
            funding_need.get("basis") if funding_need is not None else "no funding need"
        )
        if requested_amount is None:
            if decision.capital_need is not None:
                raise ValueError(
                    f"Decision for {finance.contract_id} invented contract capital_need="
                    f"{decision.capital_need}; authoritative requested_amount is "
                    f"missing ({funding_source})"
                )
            continue
        if decision.capital_need != requested_amount:
            raise ValueError(
                f"Decision capital_need for {finance.contract_id} must equal the "
                f"authoritative requested_amount {requested_amount} from "
                f"{funding_source}, got "
                f"{decision.capital_need}"
            )


def _temporary_rejection_policy(
    risk: RiskPack,
) -> tuple[set[str], set[str]]:
    """Return mandatory rule ids and large-amount companion risk ids."""
    triggered = set(risk.triggered_rule_ids)
    required_rule_ids: set[str] = set()
    large_amount_companions: set[str] = set()

    if "RR-003" in triggered:
        required_rule_ids.add("RR-003")

    if "RR-005" in triggered:
        large_amount_companions = triggered - {"RR-005"}
        if large_amount_companions:
            required_rule_ids.add("RR-005")

    return required_rule_ids, large_amount_companions


def validate_decision_risk_policy(
    batch: DecisionBatchOutput,
    risk_batch: RiskBatchPack,
) -> None:
    """Enforce temporary rejection for margin or large-risk combinations."""
    decisions = {item.contract_id: item for item in batch.decisions}
    if list(decisions) != risk_batch.contract_ids:
        raise ValueError(
            "Decision contracts do not match RiskBatchPack order: "
            f"expected={risk_batch.contract_ids}, returned={list(decisions)}"
        )

    for risk in risk_batch.packs:
        required_rule_ids, large_amount_companions = _temporary_rejection_policy(
            risk
        )
        if not required_rule_ids:
            continue

        decision = decisions[risk.contract_id]
        if (
            decision.recommended_option
            is not RecommendedOption.TEMPORARY_REJECT_RISK
            or decision.accept_opportunity
            or decision.decision_status is not DecisionStatus.REJECT
        ):
            raise ValueError(
                f"Decision for {risk.contract_id} must be temporarily rejected "
                f"because risk rules {sorted(required_rule_ids)} require it"
            )

        rationale = " ".join(
            [decision.protective_condition, *decision.reasons]
        ).casefold()
        missing_rule_ids = [
            rule_id
            for rule_id in sorted(required_rule_ids)
            if rule_id.casefold() not in rationale
        ]
        if missing_rule_ids:
            raise ValueError(
                f"Temporary rejection for {risk.contract_id} must explain "
                f"risk rules {missing_rule_ids}"
            )
        if (
            "RR-005" in required_rule_ids
            and not any(
                rule_id.casefold() in rationale
                for rule_id in large_amount_companions
            )
        ):
            raise ValueError(
                f"Large-amount temporary rejection for {risk.contract_id} must "
                "identify at least one companion triggered risk rule"
            )


def validate_decision_prechecks(
    batch: DecisionBatchOutput,
    approval_state: dict[str, Any],
) -> None:
    """Ensure score/note/status are exact consequences of StateStore records."""
    decisions = {item.contract_id: item for item in batch.decisions}
    requests_by_contract: dict[str, list[dict[str, Any]]] = {}
    for request in approval_state.get("approval_requests", []):
        contract_id = request.get("contract_id")
        if contract_id not in decisions:
            raise ValueError(
                f"Approval request refers to unknown contract {contract_id}"
            )
        requests_by_contract.setdefault(contract_id, []).append(request)

    for contract_id, decision in decisions.items():
        requests = requests_by_contract.get(contract_id, [])
        executed = [item for item in requests if item.get("status") == "executed"]
        pending = [item for item in requests if item.get("status") == "pending"]

        if decision.approval_status:
            matching = [
                item
                for item in executed
                if isinstance(item.get("result"), dict)
                and item["result"].get("eligible_score") == decision.eligible_score
                and item["result"].get("precheck_note") == decision.precheck_note
            ]
            if not matching:
                raise ValueError(
                    f"Decision precheck fields for {contract_id} do not match "
                    "an executed StateStore result"
                )
        elif executed:
            raise ValueError(
                f"Decision for {contract_id} ignored an executed precheck result"
            )

        if pending and decision.decision_status is not DecisionStatus.REVIEW:
            raise ValueError(
                f"Decision for {contract_id} must be review while precheck is pending"
            )


__all__ = [
    "validate_decision_finance_consistency",
    "validate_decision_prechecks",
    "validate_decision_risk_policy",
]
