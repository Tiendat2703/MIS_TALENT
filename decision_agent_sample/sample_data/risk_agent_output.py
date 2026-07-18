"""
Mock output của Risk Agent, dùng để test Decision Agent.
Trong thực tế, tool get_risk_agent_output(contract_id) sẽ query DB/API thật.
"""

RISK_AGENT_OUTPUT = {
    "CON-004": {
        "contract_id": "CON-004",
        "risk_level": "MEDIUM",
        "blocking_risk_flags": [],
        "missing_evidence": ["cashflow_buffer_confirmation"],
        "supplier_confirmation_status": "NOT_REQUIRED",
        "receivable_aging_status": "CURRENT",
        "fraud_flags": [
            {
                "alert_id": "AL-001",
                "alert_date": "2026-07-05",
                "alert_type": "Transaction anomaly",
                "related_record": ["TXN-006", "TXN-007"],
                "severity": "Critical",
                "risk_score": 90,
                "description": "Two abnormal ecommerce debits at 02:13 and 02:17",
                "recommended_action": "Hold + founder confirmation",
            }
        ],
        "compliance_notes": "Cần xác nhận thêm về giao dịch bất thường trước khi duyệt.",
    },
    "CON-007": {
        "contract_id": "CON-007",
        "risk_level": "HIGH",
        "blocking_risk_flags": ["MISSING_SIGNED_CONTRACT"],
        "missing_evidence": ["signed_contract_copy", "supplier_confirmation"],
        "supplier_confirmation_status": "PENDING",
        "receivable_aging_status": "OVERDUE_30D",
        "fraud_flags": [],
        "compliance_notes": "Hồ sơ chưa đủ điều kiện xử lý do thiếu hợp đồng ký kết.",
    },
}


def get_risk_agent_output(contract_id: str) -> dict:
    """Trả về mock risk data theo contract_id. Raise nếu không tồn tại."""
    if contract_id not in RISK_AGENT_OUTPUT:
        raise ValueError(f"No risk data found for contract_id={contract_id}")
    return RISK_AGENT_OUTPUT[contract_id]
