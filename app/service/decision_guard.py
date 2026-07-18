"""Deterministic checks around LLM-produced Decision batches."""

from __future__ import annotations

from typing import Any

from app.schema.decisionAgent import DecisionBatchOutput, DecisionStatus


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


__all__ = ["validate_decision_prechecks"]
