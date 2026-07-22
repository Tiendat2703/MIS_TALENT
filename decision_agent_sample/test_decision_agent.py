"""
Script chạy thử Decision Agent logic (không cần LLM), dùng data mock
từ sample_data/ để kiểm tra pipeline Giai đoạn 1 -> 4 hoạt động đúng
trước khi ghép vào OpenAI Agents SDK.

Chạy: python test_decision_agent.py
"""

from sample_data import (
    get_bank_products,
    get_finance_agent_output,
    get_mock_contract_ids,
    get_risk_agent_output,
)


def build_credit_decision_case(contract_id: str) -> dict:
    """Giai đoạn 1: gộp finance + risk output thành 1 case chuẩn hóa."""
    finance = get_finance_agent_output(contract_id)
    risk = get_risk_agent_output(contract_id)
    return {
        "contract_id": contract_id,
        "finance": finance,
        "risk": risk,
        "funding_need": {
            "need_type": finance["funding_need_type"],
            "requested_amount": finance["requested_amount"],
            "tenor": finance["tenor"],
            "basis": f"Contract {contract_id}",
        },
    }


def match_bank_product(funding_need: dict, catalog: list[dict]) -> dict:
    """Giai đoạn 4: so khớp funding_need với bank_product_catalog."""
    for product in catalog:
        if product["need_type_supported"] != funding_need["need_type"]:
            continue

        reasons = []
        need_type_ok = True
        reasons.append(f"Need type matches {product['product_name']}.")

        amount_ok = funding_need["requested_amount"] >= product["minimum_amount"]
        reasons.append(
            "Requested amount is above minimum amount."
            if amount_ok
            else f"Requested amount below minimum ({product['minimum_amount']})."
        )

        collateral_ok = "CONTRACT" in product["collateral_basis_accepted"]
        reasons.append(
            f"Basis is {funding_need['basis']}."
            if collateral_ok
            else "Collateral basis not accepted."
        )

        if need_type_ok and amount_ok and collateral_ok:
            match_status = "MATCHED"
        elif need_type_ok and (amount_ok or collateral_ok):
            match_status = "PARTIAL"
        else:
            match_status = "NO_MATCH"

        return {
            "bank_product_id": product["bank_product_id"],
            "bank": product["bank"],
            "product_name": product["product_name"],
            "match_status": match_status,
            "match_reasons": reasons,
            "human_approval_required": True,
            "precheck_status": "PENDING_HUMAN_APPROVAL",
        }

    return {"match_status": "NO_MATCH", "match_reasons": ["No product supports this need_type."]}


def evaluate_risk_acceptability(risk: dict) -> str:
    """Giai đoạn 2: đánh giá risk verdict đơn giản."""
    if risk["blocking_risk_flags"]:
        return "BLOCKED"
    if risk["missing_evidence"] or risk["fraud_flags"]:
        return "NEEDS_CONFIRMATION"
    return "ACCEPTABLE"


def render_decision_card(case: dict, match: dict, risk_verdict: str) -> dict:
    """Giai đoạn 3: xuất Decision Card theo format cố định."""
    if risk_verdict == "BLOCKED":
        option = "NEED_MORE_DATA"
    elif risk_verdict == "NEEDS_CONFIRMATION" or match["match_status"] == "PARTIAL":
        option = "APPROVE_WITH_CONDITION"
    elif match["match_status"] == "MATCHED":
        option = "APPROVE"
    else:
        option = "NO_SUITABLE_PRODUCT"

    return {
        "contract_id": case["contract_id"],
        "option": option,
        "reasons": [
            f"Financial: expected_margin={case['finance']['expected_margin']}, "
            f"cashflow_buffer={case['finance']['cashflow_buffer']}",
            f"Risk: {risk_verdict} ({case['risk']['risk_level']})",
            f"Bank fit: {match.get('match_status')} - {match.get('product_name', 'N/A')}",
        ],
        "human_approval_points": [
            "Confirm contract is signed.",
            "Confirm missing evidence: " + ", ".join(case["risk"]["missing_evidence"] or ["none"]),
            "Approve bank precheck submission before sending data to bank.",
        ],
    }


def run_case(contract_id: str) -> None:
    print(f"\n{'=' * 50}\nCASE: {contract_id}\n{'=' * 50}")
    case = build_credit_decision_case(contract_id)
    catalog = get_bank_products()
    match = match_bank_product(case["funding_need"], catalog)
    risk_verdict = evaluate_risk_acceptability(case["risk"])
    card = render_decision_card(case, match, risk_verdict)

    print("Decision Card:")
    for key, value in card.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    for contract_id in get_mock_contract_ids():
        run_case(contract_id)
