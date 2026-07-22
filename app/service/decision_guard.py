"""Deterministic checks around LLM-produced Decision batches."""

from __future__ import annotations

from typing import Any

from app.schema.decisionAgent import (
    ACTIVE_ONLY_RECOMMENDED_OPTIONS,
    ACTIVE_RECOMMENDED_OPTIONS,
    DecisionBatchOutput,
    DecisionStatus,
    RecommendedOption,
)
from app.schema.handoff_packs import FinanceBatchPack, RiskBatchPack, RiskPack
from app.schema.risk_db_models import CreditProfile
from app.service.credit_profile import resolve_contract_funding_need
from app.service.finance_handoff import normalize_contract_lifecycle
from app.tools.DecisionAgent.GetBankProduct import load_bank_product_catalog


def apply_finance_approval_policy(
    batch: DecisionBatchOutput,
    finance_batch: FinanceBatchPack,
) -> DecisionBatchOutput:
    """Project contract-final approval separately from Risk and bank approval."""
    finance_by_contract = {
        finance.contract_id: finance for finance in finance_batch.packs
    }
    payload = batch.model_dump(mode="json")
    for decision in payload["decisions"]:
        finance = finance_by_contract.get(decision["contract_id"])
        if finance is None:
            continue
        details = finance.finance_details or {}
        governance = details.get("governance_context") or {}
        threshold = governance.get("contract_final_action_approval_threshold")
        contract_finance = details.get("contract_finance") or {}
        economics = (
            contract_finance.get("contract_economics")
            or details.get("contract_economics")
            or {}
        )
        contract_value = economics.get("contract_value", finance.contract_value)
        required = (
            isinstance(threshold, (int, float))
            and isinstance(contract_value, (int, float))
            and contract_value > threshold
        )
        decision["contract_final_action_approval"] = (
            {
                "required": True,
                "source": "CONTRACT_VALUE_POLICY",
                "status": "NOT_REQUESTED",
                "object_ids": [finance.contract_id],
            }
            if required
            else {
                "required": False,
                "source": None,
                "status": "NOT_REQUIRED",
                "object_ids": [],
            }
        )
    return DecisionBatchOutput.model_validate(payload)


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

    catalog_by_id: dict[str, dict[str, Any]] | None = None
    for finance in finance_batch.packs:
        decision = decisions[finance.contract_id]
        details = finance.finance_details or {}
        expected_lifecycle = str(
            details.get("contract_lifecycle")
            or normalize_contract_lifecycle(details.get("contract_status"))
        )
        is_active_contract = expected_lifecycle == "ACTIVE"
        decision_lifecycle = normalize_contract_lifecycle(decision.contract_status)
        if is_active_contract:
            if (
                decision_lifecycle != "ACTIVE"
                or decision.assessment_type != "ONGOING_CONTRACT_REVIEW"
                or decision.recommended_option not in ACTIVE_RECOMMENDED_OPTIONS
            ):
                raise ValueError(
                    f"Decision for {finance.contract_id} must be an ACTIVE "
                    "ONGOING_CONTRACT_REVIEW using a management recommendation"
                )
        elif (
            decision.assessment_type == "ONGOING_CONTRACT_REVIEW"
            or decision.recommended_option in ACTIVE_ONLY_RECOMMENDED_OPTIONS
        ):
            raise ValueError(
                f"Decision for {finance.contract_id} cannot use the ACTIVE "
                f"workflow; authoritative lifecycle is {expected_lifecycle}"
            )

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
        if decision.selected_bank_product_id is not None:
            if catalog_by_id is None:
                catalog_by_id = {
                    str(product["bank_product_id"]): product
                    for product in load_bank_product_catalog()
                }
            product = catalog_by_id.get(decision.selected_bank_product_id)
            if product is None:
                raise ValueError(
                    f"Decision for {finance.contract_id} selected an unknown bank "
                    f"product id: {decision.selected_bank_product_id}"
                )
            if decision.selected_bank_product_name != product["product_name"]:
                raise ValueError(
                    f"Decision product name for {finance.contract_id} must match "
                    f"catalog id {decision.selected_bank_product_id}: "
                    f"{product['product_name']}"
                )
            if requested_amount is None:
                raise ValueError(
                    f"Decision for {finance.contract_id} selected a bank product "
                    "before Finance supplied requested_amount"
                )
            minimum_amount = float(product["minimum_amount"])
            if requested_amount < minimum_amount:
                raise ValueError(
                    f"Decision product {decision.selected_bank_product_id} requires "
                    f"minimum_amount={minimum_amount}, but {finance.contract_id} "
                    f"has requested_amount={requested_amount}"
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


def _contract_hold_policy(
    risk: RiskPack,
) -> set[str]:
    """Return contract rules that require review, never automatic rejection."""
    triggered = set(risk.triggered_rule_ids)
    return triggered.intersection({"RR-003", "RR-007"})


def _is_active_decision(decision: Any) -> bool:
    return (
        normalize_contract_lifecycle(getattr(decision, "contract_status", None))
        == "ACTIVE"
        and getattr(decision, "assessment_type", None)
        == "ONGOING_CONTRACT_REVIEW"
    )


def _has_authoritative_contract_rejection(decision: Any) -> bool:
    flow = (
        decision.get("contract_final_action_approval", {})
        if isinstance(decision, dict)
        else getattr(decision, "contract_final_action_approval", None)
    )
    status = flow.get("status") if isinstance(flow, dict) else getattr(
        flow, "status", None
    )
    return status == "REJECTED"


def _replace_unbacked_rejection(decision: dict[str, Any]) -> None:
    """Turn an AI-only rejection into a reversible human review."""
    current_option = decision.get("recommended_option")
    replacement_option = (
        RecommendedOption.NEED_MORE_DATA.value
        if current_option == RecommendedOption.REJECT_MISSING_EVIDENCE.value
        else RecommendedOption.RECOMMEND_HOLD.value
    )
    decision.update(
        accept_opportunity=None,
        recommended_option=replacement_option,
        decision_status=DecisionStatus.REVIEW.value,
        is_preliminary=True,
        is_final_decision=False,
        requires_founder_confirmation=True,
        human_confirmation_status="PENDING",
    )
    if not decision.get("required_actions"):
        decision["required_actions"] = [{
            "action": (
                "Rà soát bằng chứng và xin quyết định của người có thẩm quyền "
                "trước khi kết luận nhận hoặc từ chối hợp đồng."
            ),
            "owner": "Founder & Contract Owner",
        }]
    if not decision.get("human_confirmation_points"):
        decision["human_confirmation_points"] = [
            "Founder xác nhận hành động cuối của hợp đồng sau khi hoàn tất rà soát."
        ]


def apply_mandatory_risk_policy(
    batch: DecisionBatchOutput,
    risk_batch: RiskBatchPack,
    *,
    contract_id: str | None = None,
) -> DecisionBatchOutput:
    """Deterministically preserve mandatory risk review after continuation.

    RR-003 and a conclusively triggered RR-007 require a reversible HOLD. A
    bank precheck result may enrich the card but must not silently turn that
    review into approval. Missing evidence remains NEED_MORE_DATA and never
    becomes a rejection.
    """
    risk_by_contract = {risk.contract_id: risk for risk in risk_batch.packs}
    payload = batch.model_dump(mode="json")

    for decision in payload["decisions"]:
        current_contract_id = decision["contract_id"]
        if contract_id is not None and current_contract_id != contract_id:
            continue
        risk = risk_by_contract.get(current_contract_id)
        if risk is None:
            continue

        decision.update(
            risk_assessment_status=risk.risk_assessment_status,
            risk_level=(
                risk.overall_risk_level.value.casefold()
                if risk.overall_risk_level is not None
                else None
            ),
            review_priority=(
                risk.review_priority.value
                if risk.review_priority is not None
                else None
            ),
            portfolio_transaction_approval=(
                {
                    "required": True,
                    "source": "RR-001",
                    "status": "NOT_REQUESTED",
                    "object_ids": risk.portfolio_transaction_approval_object_ids,
                }
                if risk.portfolio_transaction_approval_required
                else {
                    "required": False,
                    "source": None,
                    "status": "NOT_REQUIRED",
                    "object_ids": [],
                }
            ),
        )
        if (
            decision.get("decision_status") == DecisionStatus.REJECT.value
            and _has_authoritative_contract_rejection(decision)
        ):
            continue
        if risk.risk_assessment_status == "INCOMPLETE":
            decision.update(
                risk_level=None,
                decision_status=DecisionStatus.REVIEW.value,
                recommended_option=RecommendedOption.NEED_MORE_DATA.value,
                accept_opportunity=None,
                requires_founder_confirmation=True,
                human_confirmation_status="PENDING",
                external_api_submission_approval_status="NOT_REQUESTED",
                bank_precheck_status="NOT_ELIGIBLE_TO_RUN",
                eligibility_score=None,
                precheck_note=None,
                is_preliminary=True,
                is_final_decision=False,
            )
            if not decision.get("required_actions"):
                decision["required_actions"] = [{
                    "action": (
                        "Bổ sung và rà soát evidence còn thiếu trong Risk Pack "
                        "trước khi đưa ra kết luận rủi ro."
                    ),
                    "owner": "Risk & Contract Owner",
                }]
            if not decision.get("human_confirmation_points"):
                decision["human_confirmation_points"] = [
                    "Xác nhận evidence bổ sung trước khi chạy lại Risk Assessment."
                ]
            # An incomplete assessment cannot become a conclusive hold or
            # rejection. Triggered facts remain visible while the recommendation
            # stays NEED_MORE_DATA for every contract lifecycle.
            continue

        required_rule_ids = _contract_hold_policy(risk)
        if not required_rule_ids:
            if (
                decision.get("decision_status") == DecisionStatus.REJECT.value
                and not _has_authoritative_contract_rejection(decision)
            ):
                _replace_unbacked_rejection(decision)
            continue

        is_active_review = (
            normalize_contract_lifecycle(decision.get("contract_status")) == "ACTIVE"
            and decision.get("assessment_type") == "ONGOING_CONTRACT_REVIEW"
        )
        decision.update(
            accept_opportunity=None,
            decision_status=DecisionStatus.REVIEW.value,
            is_preliminary=True,
            is_final_decision=False,
            requires_founder_confirmation=True,
            human_confirmation_status="PENDING",
        )
        if not is_active_review:
            decision["recommended_option"] = RecommendedOption.RECOMMEND_HOLD.value

        actions = list(decision.get("required_actions") or [])
        action_templates = {
            "RR-003": (
                "Rà soát lại giá bán, chi phí ước tính và biên hợp đồng theo RR-003.",
                "Finance & Contract Owner",
            ),
            "RR-007": (
                "Rà soát kế hoạch vận hành và mức phạt tiến độ theo RR-007.",
                "Operations & Contract Owner",
            ),
        }
        for rule_id in sorted(required_rule_ids):
            if any(
                rule_id.casefold() in str(item.get("action") or "").casefold()
                for item in actions
            ):
                continue
            action, owner = action_templates[rule_id]
            actions.append({"action": action, "owner": owner})
        decision["required_actions"] = actions
        if not decision.get("human_confirmation_points"):
            decision["human_confirmation_points"] = [
                "Người có thẩm quyền xác nhận hành động tiếp theo sau khi hoàn tất "
                f"rà soát {', '.join(sorted(required_rule_ids))}."
            ]

        cited_rule_ids = sorted(required_rule_ids)
        rationale = " ".join([
            str(decision.get("protective_condition") or ""),
            *[str(reason) for reason in decision.get("reasons") or []],
        ]).casefold()
        if all(rule_id.casefold() in rationale for rule_id in cited_rule_ids):
            continue

        policy_note = (
            (
                "Cảnh báo quản trị theo "
                f"{', '.join(cited_rule_ids)}; cần hoàn tất hành động quản trị "
                "trước bước tiếp theo, nhưng không từ chối hợp đồng đang ACTIVE."
            )
            if is_active_review
            else (
                "Chính sách rủi ro yêu cầu HOLD theo "
                f"{', '.join(cited_rule_ids)}; cần hoàn tất hành động rà soát "
                "trước khi tiếp tục hồ sơ."
            )
        )
        reasons = list(decision["reasons"])
        reasons[-1] = f"{reasons[-1]} {policy_note}"
        decision["reasons"] = reasons
        decision["protective_condition"] = (
            f"{decision['protective_condition']} {policy_note}"
        )

    return DecisionBatchOutput.model_validate(payload)


def validate_decision_risk_policy(
    batch: DecisionBatchOutput,
    risk_batch: RiskBatchPack,
) -> None:
    """Enforce evidence holds without converting risk severity into rejection."""
    decisions = {item.contract_id: item for item in batch.decisions}
    if list(decisions) != risk_batch.contract_ids:
        raise ValueError(
            "Decision contracts do not match RiskBatchPack order: "
            f"expected={risk_batch.contract_ids}, returned={list(decisions)}"
        )

    for risk in risk_batch.packs:
        decision = decisions[risk.contract_id]
        expected_risk_level = (
            risk.overall_risk_level.value.casefold()
            if risk.overall_risk_level is not None
            else None
        )
        observed_risk_level = (
            decision.risk_level.value if decision.risk_level is not None else None
        )
        expected_priority = (
            risk.review_priority.value
            if risk.review_priority is not None
            else None
        )
        observed_priority = (
            decision.review_priority.value
            if decision.review_priority is not None
            else None
        )
        if decision.risk_assessment_status != risk.risk_assessment_status:
            raise ValueError(
                f"Decision risk_assessment_status for {risk.contract_id} must equal "
                f"RiskPack {risk.risk_assessment_status}"
            )
        if observed_risk_level != expected_risk_level:
            raise ValueError(
                f"Decision risk_level for {risk.contract_id} must equal RiskPack "
                f"overall_risk_level {expected_risk_level}"
            )
        if observed_priority != expected_priority:
            raise ValueError(
                f"Decision review_priority for {risk.contract_id} must equal "
                f"RiskPack {expected_priority}"
            )
        if (
            decision.decision_status is DecisionStatus.REJECT
            and not _has_authoritative_contract_rejection(decision)
        ):
            raise ValueError(
                f"Reject decision for {risk.contract_id} requires an authoritative "
                "contract_final_action_approval status REJECTED"
            )
        if (
            decision.portfolio_transaction_approval.required
            != risk.portfolio_transaction_approval_required
            or decision.portfolio_transaction_approval.object_ids
            != risk.portfolio_transaction_approval_object_ids
        ):
            raise ValueError(
                f"Decision portfolio transaction approval for {risk.contract_id} "
                "must match the RR-001 portfolio evidence"
            )
        if (
            decision.decision_status is DecisionStatus.REJECT
            and _has_authoritative_contract_rejection(decision)
        ):
            continue
        if risk.risk_assessment_status == "INCOMPLETE":
            if decision.recommended_option is not RecommendedOption.NEED_MORE_DATA:
                raise ValueError(
                    f"Incomplete risk for {risk.contract_id} requires NEED_MORE_DATA"
                )
            continue

        required_rule_ids = _contract_hold_policy(risk)
        if not required_rule_ids:
            continue
        if _is_active_decision(decision):
            action_text = " ".join(
                action.action.casefold() for action in decision.required_actions
            )
            has_required_actions = all(
                rule_id.casefold() in action_text for rule_id in required_rule_ids
            )
            if (
                decision.recommended_option not in ACTIVE_RECOMMENDED_OPTIONS
                or decision.accept_opportunity is not None
                or decision.decision_status is not DecisionStatus.REVIEW
                or not has_required_actions
            ):
                raise ValueError(
                    f"ACTIVE decision for {risk.contract_id} must preserve a management "
                    f"option and include actions for risk rules {sorted(required_rule_ids)}"
                )
        elif (
            decision.recommended_option
            is not RecommendedOption.RECOMMEND_HOLD
            or decision.accept_opportunity is not None
            or decision.decision_status is not DecisionStatus.REVIEW
        ):
            raise ValueError(
                f"Decision for {risk.contract_id} must be held for review "
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
                f"Risk policy recommendation for {risk.contract_id} must explain "
                f"risk rules {missing_rule_ids}"
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

        if decision.external_api_submission_approval_status == "EXECUTED":
            matching = [
                item
                for item in executed
                if isinstance(item.get("result"), dict)
                and item["result"].get("eligible_score") == decision.eligibility_score
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

        pending_temporary_risk_rejection = (
            decision.recommended_option is RecommendedOption.TEMPORARY_REJECT_RISK
            and decision.decision_status is DecisionStatus.REJECT
            and decision.is_preliminary
        )
        if (
            pending
            and decision.decision_status is not DecisionStatus.REVIEW
            and not pending_temporary_risk_rejection
        ):
            raise ValueError(
                f"Decision for {contract_id} must be review while precheck is pending"
            )
        if pending and (
            decision.external_api_submission_approval_status != "PENDING"
            or decision.bank_precheck_status
            not in {"ELIGIBLE_AWAITING_APPROVAL", "PENDING"}
        ):
            raise ValueError(
                f"Decision for {contract_id} must expose pending external approval state"
            )


def apply_authoritative_precheck_state(
    batch: DecisionBatchOutput,
    approval_state: dict[str, Any],
) -> DecisionBatchOutput:
    """Project StateStore approval state into the unambiguous Decision fields."""
    payload = batch.model_dump(mode="json")
    decisions = {
        item["contract_id"]: item for item in payload.get("decisions", [])
    }
    requests_by_contract: dict[str, list[dict[str, Any]]] = {}
    for request in approval_state.get("approval_requests", []):
        contract_id = request.get("contract_id")
        if contract_id in decisions:
            requests_by_contract.setdefault(contract_id, []).append(request)

    for contract_id, decision in decisions.items():
        requests = requests_by_contract.get(contract_id, [])
        executed = next(
            (item for item in reversed(requests) if item.get("status") == "executed"),
            None,
        )
        pending = next(
            (item for item in reversed(requests) if item.get("status") == "pending"),
            None,
        )
        rejected = next(
            (item for item in reversed(requests) if item.get("status") == "rejected"),
            None,
        )
        failed = next(
            (item for item in reversed(requests) if item.get("status") == "failed"),
            None,
        )
        if executed is not None and isinstance(executed.get("result"), dict):
            result = executed["result"]
            decision.update(
                external_api_submission_approval_status="EXECUTED",
                bank_precheck_status="COMPLETED",
                eligibility_score=result.get("eligible_score"),
                precheck_note=result.get("precheck_note"),
            )
        elif pending is not None:
            decision.update(
                external_api_submission_approval_status="PENDING",
                bank_precheck_status="ELIGIBLE_AWAITING_APPROVAL",
                eligibility_score=None,
                precheck_note=None,
            )
            # Collecting a precheck does not reverse an existing preliminary
            # RR-based rejection. Every other pending card remains in review.
            if (
                decision.get("recommended_option")
                != RecommendedOption.TEMPORARY_REJECT_RISK.value
            ):
                decision["decision_status"] = DecisionStatus.REVIEW.value
        elif rejected is not None:
            decision.update(
                external_api_submission_approval_status="REJECTED",
                bank_precheck_status="NOT_ELIGIBLE_TO_RUN",
                eligibility_score=None,
                precheck_note=None,
            )
            if (
                decision.get("recommended_option")
                != RecommendedOption.TEMPORARY_REJECT_RISK.value
            ):
                decision["decision_status"] = DecisionStatus.REVIEW.value
        elif failed is not None:
            decision.update(
                external_api_submission_approval_status="APPROVED",
                bank_precheck_status="FAILED",
                eligibility_score=None,
                precheck_note=None,
            )
            if (
                decision.get("recommended_option")
                != RecommendedOption.TEMPORARY_REJECT_RISK.value
            ):
                decision["decision_status"] = DecisionStatus.REVIEW.value
    return DecisionBatchOutput.model_validate(payload)


__all__ = [
    "apply_finance_approval_policy",
    "apply_authoritative_precheck_state",
    "apply_mandatory_risk_policy",
    "validate_decision_finance_consistency",
    "validate_decision_prechecks",
    "validate_decision_risk_policy",
]
