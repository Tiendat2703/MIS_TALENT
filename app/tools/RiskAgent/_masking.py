"""Deterministic masking for data returned to the OpenAI agent."""

from __future__ import annotations

import hashlib
import re

from app.schema.risk_db_models import (
    BankTransaction,
    CompanyProfile,
    ContractRecord,
    CreditProfile,
    MaskingExample,
    OrderRecord,
    RiskEvaluationReport,
)
from app.schema.handoff_packs import RiskAlert

_IDENTIFIER = re.compile(r"\b(?:TXN|CON|CR|ORD|CUS|ACC|OPC)[-_][A-Z0-9]+\b", re.I)
_CONFIDENTIAL_METRICS = {
    "closing_cash",
    "gross_margin",
    "projected_closing_cash",
    "requested_amount",
}


def tokenize_identifier(value: str) -> str:
    prefix = value.split("-", 1)[0].split("_", 1)[0].upper()
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8].upper()
    return f"TOK-{prefix}-{digest}"


def mask_text_identifiers(value: str | None) -> str | None:
    if value is None:
        return None
    return _IDENTIFIER.sub(lambda match: tokenize_identifier(match.group(0)), value)


def mask_evaluation(report: RiskEvaluationReport) -> RiskEvaluationReport:
    safe = report.model_copy(deep=True)
    for evaluation in safe.evaluations:
        for finding in evaluation.findings:
            finding.record_id = tokenize_identifier(finding.record_id)
            if finding.observed_metric in _CONFIDENTIAL_METRICS:
                finding.observed_value = "[CONFIDENTIAL_VALUE]"
    return safe


def mask_alert(alert: RiskAlert) -> RiskAlert:
    safe = alert.model_copy(deep=True)
    safe.related_record = mask_text_identifiers(safe.related_record)
    return safe


def mask_bank_transaction(transaction: BankTransaction) -> BankTransaction:
    safe = transaction.model_copy(deep=True)
    safe.txn_id = tokenize_identifier(safe.txn_id)
    if safe.account_id:
        safe.account_id = tokenize_identifier(safe.account_id)
    if safe.counterparty_id:
        safe.counterparty_id = tokenize_identifier(safe.counterparty_id)
    return safe


def mask_company_profile(company: CompanyProfile) -> CompanyProfile:
    safe = company.model_copy(deep=True)
    safe.company_id = tokenize_identifier(safe.company_id)
    if safe.company_name:
        safe.company_name = "[MASKED_ORGANIZATION]"
    if safe.founder:
        safe.founder = "[MASKED_PERSON]"
    return safe


def mask_contract(contract: ContractRecord) -> ContractRecord:
    safe = contract.model_copy(deep=True)
    safe.contract_id = tokenize_identifier(safe.contract_id)
    if safe.customer_id:
        safe.customer_id = tokenize_identifier(safe.customer_id)
    return safe


def mask_credit_profile(profile: CreditProfile) -> CreditProfile:
    safe = profile.model_copy(deep=True)
    safe.credit_case_id = tokenize_identifier(safe.credit_case_id)
    if safe.company_id:
        safe.company_id = tokenize_identifier(safe.company_id)
    safe.collateral_or_basis = mask_text_identifiers(safe.collateral_or_basis)
    safe.precheck_note = mask_text_identifiers(safe.precheck_note)
    return safe


def mask_order(order: OrderRecord) -> OrderRecord:
    safe = order.model_copy(deep=True)
    safe.order_id = tokenize_identifier(safe.order_id)
    if safe.contract_id:
        safe.contract_id = tokenize_identifier(safe.contract_id)
    if safe.customer_id:
        safe.customer_id = tokenize_identifier(safe.customer_id)
    if safe.service_id:
        safe.service_id = tokenize_identifier(safe.service_id)
    return safe


def mask_example(example: MaskingExample) -> MaskingExample:
    safe = example.model_copy(deep=True)
    if safe.raw_example is not None:
        safe.raw_example = "[REDACTED]"
    return safe
