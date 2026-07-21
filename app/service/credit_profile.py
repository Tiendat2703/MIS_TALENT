"""Resolve contract funding from the authoritative ``credit_profile`` table.

The current database does not have a dedicated ``contract_id`` column on
``credit_profile``. A profile is therefore contract-scoped only when its
``collateral_or_basis`` contains an exact ``CON-...`` identifier. Profiles
without that identifier remain company/portfolio evidence and must not be
guessed onto a contract.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.database.repository import query_db
from app.schema.risk_db_models import CreditProfile


_CONTRACT_ID_PATTERN = re.compile(
    r"(?<![A-Z0-9-])(CON-[A-Z0-9]+(?:-[A-Z0-9]+)*)(?![A-Z0-9-])",
    re.IGNORECASE,
)


def normalize_credit_request_type(request_type: str | None) -> str | None:
    """Map the organizer's credit request labels to Decision need types."""
    normalized = str(request_type or "").casefold()
    if "performance bond" in normalized or "bảo lãnh thực hiện" in normalized:
        return "PERFORMANCE_BOND"
    if any(
        value in normalized
        for value in (
            "trade finance",
            "tài trợ thương mại",
            "letter of credit",
            "l/c",
        )
    ):
        return "TRADE_FINANCE"
    if "receivable" in normalized or "khoản phải thu" in normalized:
        return "RECEIVABLE_FINANCING"
    if "working capital" in normalized or "vốn lưu động" in normalized:
        return "WORKING_CAPITAL"
    return None


def referenced_contract_ids(profile: CreditProfile) -> set[str]:
    """Return only explicit contract identifiers from the profile basis."""
    basis = str(profile.collateral_or_basis or "")
    return {match.upper() for match in _CONTRACT_ID_PATTERN.findall(basis)}


def map_credit_profiles_to_contracts(
    profiles: Sequence[CreditProfile],
    contract_ids: Sequence[str],
) -> dict[str, CreditProfile]:
    """Map one unambiguous credit profile to each requested contract.

    Multiple credit cases for one contract cannot be represented safely by the
    current one-funding-need Decision Card, so fail instead of choosing one
    silently.
    """
    requested = {contract_id.upper(): contract_id for contract_id in contract_ids}
    matches: dict[str, list[CreditProfile]] = {}
    for profile in profiles:
        for normalized_id in referenced_contract_ids(profile):
            contract_id = requested.get(normalized_id)
            if contract_id is not None:
                matches.setdefault(contract_id, []).append(profile)

    ambiguous = {
        contract_id: [profile.credit_case_id for profile in items]
        for contract_id, items in matches.items()
        if len(items) > 1
    }
    if ambiguous:
        raise ValueError(
            "Multiple credit_profile rows reference one contract; the funding "
            f"request is ambiguous: {ambiguous}"
        )
    return {contract_id: items[0] for contract_id, items in matches.items()}


def load_contract_credit_profiles(
    contract_ids: Sequence[str],
) -> dict[str, CreditProfile]:
    """Read real credit profiles and return exact contract-scoped matches."""
    rows = query_db(
        """
        SELECT credit_case_id, company_id, request_type, requested_amount,
               tenor, collateral_or_basis, eligibility_score, precheck_note,
               approval_status
        FROM public.credit_profile
        ORDER BY credit_case_id
        """
    )
    if not isinstance(rows, list):
        raise RuntimeError("Expected credit_profile query to return a list of rows")
    profiles = [CreditProfile.model_validate(row) for row in rows]
    return map_credit_profiles_to_contracts(profiles, contract_ids)


def _field(finance: Mapping[str, Any] | Any, name: str) -> Any:
    if isinstance(finance, Mapping):
        return finance.get(name)
    return getattr(finance, name)


def resolve_contract_funding_need(
    finance: Mapping[str, Any] | Any,
    credit_profile: CreditProfile | None,
) -> dict[str, Any] | None:
    """Apply the funding-source priority used by Decision.

    A profile with a missing amount does not fall through to the contract amount;
    that would conceal incomplete credit data and violate the requested priority.
    """
    if credit_profile is not None:
        need_type = normalize_credit_request_type(credit_profile.request_type)
        if need_type is None:
            need_type = _field(finance, "funding_need_type")
        amount = (
            float(credit_profile.requested_amount)
            if credit_profile.requested_amount is not None
            else None
        )
        return {
            "need_type": need_type,
            "requested_amount": amount,
            "tenor": credit_profile.tenor or _field(finance, "tenor"),
            "basis": "credit_profile.requested_amount",
            "scope": "contract",
            "source": "credit_profile",
            "credit_case_id": credit_profile.credit_case_id,
            "amount_status": "PROVIDED" if amount is not None else "MISSING",
        }

    need_type = _field(finance, "funding_need_type")
    raw_amount = _field(finance, "requested_amount")
    amount = float(raw_amount) if raw_amount is not None else None
    if need_type is None and amount is None:
        return None
    details = _field(finance, "finance_details") or {}
    funding_details = details.get("funding_need") or {}
    amount_source = funding_details.get("requested_amount_source")
    source_metadata = {
        "contract_cashflow_peak_deficit": {
            "basis": "finance.contract_cashflow_peak_deficit",
            "source": "finance_inference",
            "status": "INFERRED",
        },
        "performance_bond_percentage": {
            "basis": "finance.performance_bond_percentage",
            "source": "finance_inference",
            "status": "CALCULATED",
        },
        "performance_bond_explicit_amount": {
            "basis": "contract.payment_terms.performance_bond_amount",
            "source": "contract_term",
            "status": "EXTRACTED",
        },
        "performance_bond_full_contract_fallback": {
            "basis": "finance.performance_bond_full_contract_fallback",
            "source": "finance_inference",
            "status": "ESTIMATED",
        },
        "payment_terms_percentage": {
            "basis": "finance.payment_terms_percentage",
            "source": "finance_inference",
            "status": "CALCULATED",
        },
        "payment_terms_explicit_amount": {
            "basis": "contract.payment_terms.financing_amount",
            "source": "contract_term",
            "status": "EXTRACTED",
        },
        "payment_terms_full_contract_fallback": {
            "basis": "finance.payment_terms_full_contract_fallback",
            "source": "finance_inference",
            "status": "ESTIMATED",
        },
    }.get(amount_source)
    return {
        "need_type": need_type,
        "requested_amount": amount,
        "tenor": _field(finance, "tenor"),
        "payment_terms": details.get("payment_terms"),
        "basis": (
            source_metadata["basis"]
            if source_metadata is not None
            else "contract.funding_need.requested_amount"
        ),
        "scope": "contract",
        "source": (
            source_metadata["source"]
            if source_metadata is not None
            else "contract_funding_need"
        ),
        "credit_case_id": None,
        "amount_status": (
            source_metadata["status"]
            if source_metadata is not None and amount is not None
            else "PROVIDED" if amount is not None else "MISSING"
        ),
    }


def credit_profile_payload(profile: CreditProfile | None) -> dict[str, Any] | None:
    """Serialize profile evidence with numeric values kept numeric for the agent."""
    if profile is None:
        return None
    return {
        "credit_case_id": profile.credit_case_id,
        "company_id": profile.company_id,
        "request_type": profile.request_type,
        "requested_amount": (
            float(profile.requested_amount)
            if profile.requested_amount is not None
            else None
        ),
        "tenor": profile.tenor,
        "collateral_or_basis": profile.collateral_or_basis,
        "eligibility_score": (
            float(profile.eligibility_score)
            if profile.eligibility_score is not None
            else None
        ),
        "precheck_note": profile.precheck_note,
        "approval_status": profile.approval_status,
        "source_table": "credit_profile",
        "reference_only": True,
    }


__all__ = [
    "credit_profile_payload",
    "load_contract_credit_profiles",
    "map_credit_profiles_to_contracts",
    "normalize_credit_request_type",
    "referenced_contract_ids",
    "resolve_contract_funding_need",
]
