"""Deterministically reconcile human-gated bank precheck requests.

The LLM may explain a missing document correctly but still skip the precheck
tool. Approval availability must not depend on that nondeterministic choice:
when Decision has an authoritative positive amount, the application registers
the exact supported tool arguments in StateStore. This grants no bank access;
the external API remains blocked until a human approves that exact request.
"""

from __future__ import annotations

from typing import Any

from app.Agent.bus import event_bus
from app.Agent.state_store import register_approval_request
from app.schema.decisionAgent import DecisionBatchOutput, RecommendedOption
from app.schema.handoff_packs import FinanceBatchPack
from app.schema.risk_db_models import CreditProfile
from app.service.credit_profile import resolve_contract_funding_need


_NON_ACTIONABLE_OPTIONS = {
    RecommendedOption.TEMPORARY_REJECT_RISK,
    RecommendedOption.REJECT_MISSING_EVIDENCE,
    RecommendedOption.NO_SUITABLE_PRODUCT,
}


def build_precheck_approval_specs(
    decisions: DecisionBatchOutput,
    finance_batch: FinanceBatchPack,
    credit_profiles: dict[str, CreditProfile],
) -> list[dict[str, Any]]:
    """Build exact StateStore requests for actionable contract funding needs."""
    decisions_by_contract = {
        decision.contract_id: decision for decision in decisions.decisions
    }
    specs: list[dict[str, Any]] = []

    for finance in finance_batch.packs:
        decision = decisions_by_contract.get(finance.contract_id)
        if decision is None or decision.recommended_option in _NON_ACTIONABLE_OPTIONS:
            continue

        funding_need = resolve_contract_funding_need(
            finance,
            credit_profiles.get(finance.contract_id),
        )
        if funding_need is None:
            continue
        amount = funding_need.get("requested_amount")
        if not isinstance(amount, (int, float)) or amount <= 0:
            continue
        # The Decision guard separately enforces that capital_need equals this
        # authoritative amount. Avoid creating a request for an inconsistent card.
        if decision.capital_need != amount:
            continue

        need_type = funding_need.get("need_type")
        if need_type == "PERFORMANCE_BOND":
            tool_name = "precheck_performance_bond"
            arguments = {
                "contract_id": finance.contract_id,
                "amount": float(amount),
            }
        elif need_type == "TRADE_FINANCE":
            tool_name = "precheck_trade_finance"
            arguments = {
                "contract_id": finance.contract_id,
                # An empty list is still the real supplied evidence set. The bank
                # precheck, not approval registration, evaluates its completeness.
                "supplier_docs": list(finance.supplier_docs),
                "amount": float(amount),
            }
        elif need_type == "WORKING_CAPITAL":
            tool_name = "precheck_micro_credit"
            arguments = {
                "contract_id": finance.contract_id,
                "amount": float(amount),
                "receivable_list": list(finance.receivable_list),
            }
        else:
            # No real bank precheck tool exists for this need type.
            continue

        specs.append(
            {
                "contract_id": finance.contract_id,
                "tool": tool_name,
                "arguments": arguments,
            }
        )
    return specs


async def ensure_precheck_approval_requests(
    run_id: int,
    decisions: DecisionBatchOutput,
    finance_batch: FinanceBatchPack,
    credit_profiles: dict[str, CreditProfile],
) -> list[dict[str, Any]]:
    """Idempotently register every exact actionable precheck request."""
    ensured: list[dict[str, Any]] = []
    for spec in build_precheck_approval_specs(
        decisions,
        finance_batch,
        credit_profiles,
    ):
        request = await register_approval_request(
            run_id,
            spec["contract_id"],
            spec["tool"],
            spec["arguments"],
        )
        if request.pop("_newly_registered", False):
            await event_bus.emit(
                run_id,
                {
                    "type": "approval_requested",
                    "agent": "Decision_Agent",
                    "task": (
                        f"Chờ phê duyệt {spec['tool']} cho "
                        f"{spec['contract_id']}"
                    ),
                    "status": "review",
                    "data": {
                        "approval_id": request["approval_id"],
                        "contract_id": spec["contract_id"],
                        "tool": spec["tool"],
                        "arguments": spec["arguments"],
                        "approval_state": request["status"],
                        "registered_by": "application_reconciliation",
                    },
                },
            )
        ensured.append(request)
    return ensured


__all__ = [
    "build_precheck_approval_specs",
    "ensure_precheck_approval_requests",
]
