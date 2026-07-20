"""Deterministic checks around LLM-produced Decision batches."""

from __future__ import annotations

from typing import Any

from app.schema.decisionAgent import DecisionBatchOutput, DecisionStatus
from app.schema.handoff_packs import FinanceBatchPack


def validate_decision_finance_consistency(
    batch: DecisionBatchOutput,
    finance_batch: FinanceBatchPack,
) -> None:
    """Keep contract capital need separate from portfolio liquidity metrics."""
    decisions = {item.contract_id: item for item in batch.decisions}
    expected_ids = finance_batch.contract_ids
    if list(decisions) != expected_ids:
        raise ValueError(
            "Decision contracts do not match FinanceBatchPack order: "
            f"expected={expected_ids}, returned={list(decisions)}"
        )

    for finance in finance_batch.packs:
        decision = decisions[finance.contract_id]
        if finance.requested_amount is None:
            if decision.capital_need is not None:
                raise ValueError(
                    f"Decision for {finance.contract_id} invented contract capital_need="
                    f"{decision.capital_need}; Finance requested_amount is missing"
                )
            continue
        if decision.capital_need != finance.requested_amount:
            raise ValueError(
                f"Decision capital_need for {finance.contract_id} must equal the "
                f"contract requested_amount {finance.requested_amount}, got "
                f"{decision.capital_need}"
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
]
