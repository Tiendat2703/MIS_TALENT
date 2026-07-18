"""Mock dữ liệu Team Pack (MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx).

Đây là bản sao trung thực của các sheet tài chính, dùng khi CHƯA kết nối được
Supabase. Khi DB sẵn sàng, đặt biến môi trường FINANCE_USE_MOCK=false thì
finance_data.py sẽ đọc DB thật thay vì mock này.

Ngày để dạng chuỗi ISO 'YYYY-MM-DD'; số tiền VND để dạng int.
"""

from __future__ import annotations

# 04_CONTRACTS
CONTRACTS = [
    {"contract_id": "CON-001", "customer_id": "CUS-001", "start_date": "2026-04-20", "end_date": "2026-10-20", "status": "Active", "description": "Recurring operations support", "contract_value": 720000000, "gross_margin": 0.30, "payment_terms": "Monthly payment"},
    {"contract_id": "CON-002", "customer_id": "CUS-002", "start_date": "2026-05-05", "end_date": "2026-09-30", "status": "Active", "description": "ERP-light order flow setup", "contract_value": 980000000, "gross_margin": 0.26, "payment_terms": "Milestone payment"},
    {"contract_id": "CON-003", "customer_id": "CUS-004", "start_date": "2026-05-16", "end_date": "2026-11-30", "status": "Active", "description": "Customer service automation", "contract_value": 1250000000, "gross_margin": 0.31, "payment_terms": "Milestone payment"},
    {"contract_id": "CON-004", "customer_id": "CUS-005", "start_date": "2026-06-01", "end_date": "2027-03-31", "status": "Pending expansion", "description": "20-province cooperative network rollout", "contract_value": 4200000000, "gross_margin": 0.24, "payment_terms": "Performance bond required"},
    {"contract_id": "CON-005", "customer_id": "CUS-008", "start_date": "2026-06-08", "end_date": "2026-12-31", "status": "Negotiation", "description": "Trade documentation and reporting workflow", "contract_value": 1850000000, "gross_margin": 0.29, "payment_terms": "Possible LC/trade finance"},
]

# 06_ORDERS
ORDERS = [
    {"order_id": "ORD-001", "contract_id": "CON-001", "customer_id": "CUS-001", "order_date": "2026-05-02", "due_date": "2026-05-22", "status": "Delivered", "service_id": "SVC-002", "order_revenue": 45000000, "estimated_cost": 14000000, "delivery_note": "Normal"},
    {"order_id": "ORD-002", "contract_id": "CON-001", "customer_id": "CUS-001", "order_date": "2026-06-02", "due_date": "2026-06-25", "status": "In progress", "service_id": "SVC-002", "order_revenue": 45000000, "estimated_cost": 14500000, "delivery_note": "Normal"},
    {"order_id": "ORD-003", "contract_id": "CON-002", "customer_id": "CUS-002", "order_date": "2026-05-10", "due_date": "2026-06-10", "status": "Delivered", "service_id": "SVC-001", "order_revenue": 280000000, "estimated_cost": 205000000, "delivery_note": "Margin pressure"},
    {"order_id": "ORD-004", "contract_id": "CON-003", "customer_id": "CUS-004", "order_date": "2026-05-21", "due_date": "2026-07-02", "status": "At risk", "service_id": "SVC-003", "order_revenue": 310000000, "estimated_cost": 198000000, "delivery_note": "Resource bottleneck"},
    {"order_id": "ORD-005", "contract_id": "CON-004", "customer_id": "CUS-005", "order_date": "2026-06-18", "due_date": "2026-08-30", "status": "Pending approval", "service_id": "SVC-004", "order_revenue": 1600000000, "estimated_cost": 1216000000, "delivery_note": "Requires performance bond"},
    {"order_id": "ORD-006", "contract_id": "CON-004", "customer_id": "CUS-005", "order_date": "2026-09-01", "due_date": "2026-11-15", "status": "Planned", "service_id": "SVC-004", "order_revenue": 1500000000, "estimated_cost": 1140000000, "delivery_note": "Requires working capital"},
    {"order_id": "ORD-007", "contract_id": "CON-005", "customer_id": "CUS-008", "order_date": "2026-07-01", "due_date": "2026-09-15", "status": "Planned", "service_id": "SVC-005", "order_revenue": 800000000, "estimated_cost": 568000000, "delivery_note": "May require LC support"},
    {"order_id": "ORD-008", "contract_id": "CON-003", "customer_id": "CUS-004", "order_date": "2026-07-05", "due_date": "2026-08-15", "status": "Planned", "service_id": "SVC-003", "order_revenue": 420000000, "estimated_cost": 276000000, "delivery_note": "Needs extra contractor"},
    {"order_id": "ORD-009", "contract_id": "CON-002", "customer_id": "CUS-002", "order_date": "2026-06-20", "due_date": "2026-07-30", "status": "In progress", "service_id": "SVC-001", "order_revenue": 360000000, "estimated_cost": 266400000, "delivery_note": "Payment after UAT"},
    {"order_id": "ORD-010", "contract_id": "CON-001", "customer_id": "CUS-001", "order_date": "2026-07-02", "due_date": "2026-07-25", "status": "Planned", "service_id": "SVC-002", "order_revenue": 45000000, "estimated_cost": 14500000, "delivery_note": "Normal"},
]

# 07_INVOICES
INVOICES = [
    {"invoice_id": "INV-001", "order_id": "ORD-001", "customer_id": "CUS-001", "issue_date": "2026-05-22", "due_date": "2026-06-06", "status": "Paid", "invoice_amount": 45000000, "paid_date": "2026-06-03"},
    {"invoice_id": "INV-002", "order_id": "ORD-003", "customer_id": "CUS-002", "issue_date": "2026-06-10", "due_date": "2026-07-10", "status": "Open", "invoice_amount": 280000000, "paid_date": None},
    {"invoice_id": "INV-003", "order_id": "ORD-002", "customer_id": "CUS-001", "issue_date": "2026-06-25", "due_date": "2026-07-10", "status": "Open", "invoice_amount": 45000000, "paid_date": None},
    {"invoice_id": "INV-004", "order_id": "ORD-004", "customer_id": "CUS-004", "issue_date": "2026-07-02", "due_date": "2026-08-01", "status": "Open", "invoice_amount": 310000000, "paid_date": None},
    {"invoice_id": "INV-005", "order_id": "ORD-005", "customer_id": "CUS-005", "issue_date": "2026-08-30", "due_date": "2026-09-29", "status": "Not issued", "invoice_amount": 1600000000, "paid_date": None},
    {"invoice_id": "INV-006", "order_id": "ORD-007", "customer_id": "CUS-008", "issue_date": "2026-09-15", "due_date": "2026-10-15", "status": "Not issued", "invoice_amount": 800000000, "paid_date": None},
    {"invoice_id": "INV-007", "order_id": "ORD-009", "customer_id": "CUS-002", "issue_date": "2026-07-30", "due_date": "2026-08-29", "status": "Not issued", "invoice_amount": 360000000, "paid_date": None},
]

# 08_BANK_TXN
BANK_TXN = [
    {"txn_id": "TXN-001", "txn_date": "2026-05-04", "bank": "VietinBank", "account_id": "OPC_MAIN", "direction": "Credit", "description": "CUS-006 monthly service", "amount": 52000000, "counterparty_id": "CUS-006", "txn_status": "Normal", "transaction_risk_score": 12},
    {"txn_id": "TXN-002", "txn_date": "2026-05-08", "bank": "CoopBank", "account_id": "OPC_LOCAL", "direction": "Credit", "description": "CUS-003 setup deposit", "amount": 36000000, "counterparty_id": "CUS-003", "txn_status": "Normal", "transaction_risk_score": 16},
    {"txn_id": "TXN-003", "txn_date": "2026-05-22", "bank": "VietinBank", "account_id": "OPC_MAIN", "direction": "Debit", "description": "Cloud infrastructure", "amount": -74000000, "counterparty_id": "SUP-002", "txn_status": "Normal", "transaction_risk_score": 25},
    {"txn_id": "TXN-004", "txn_date": "2026-06-03", "bank": "CoopBank", "account_id": "OPC_LOCAL", "direction": "Credit", "description": "INV-001 payment", "amount": 45000000, "counterparty_id": "CUS-001", "txn_status": "Normal", "transaction_risk_score": 10},
    {"txn_id": "TXN-005", "txn_date": "2026-06-05", "bank": "VietinBank", "account_id": "OPC_MAIN", "direction": "Debit", "description": "Contractor payment batch", "amount": -185000000, "counterparty_id": "SUP-003", "txn_status": "Normal", "transaction_risk_score": 40},
    {"txn_id": "TXN-006", "txn_date": "2026-06-11", "bank": "VietinBank", "account_id": "OPC_MAIN", "direction": "Debit", "description": "Unknown ecommerce charge at 02:13", "amount": -86000000, "counterparty_id": "UNK-ECOM", "txn_status": "Suspicious", "transaction_risk_score": 88},
    {"txn_id": "TXN-007", "txn_date": "2026-06-11", "bank": "VietinBank", "account_id": "OPC_MAIN", "direction": "Debit", "description": "Unknown ecommerce charge retry at 02:17", "amount": -92000000, "counterparty_id": "UNK-ECOM", "txn_status": "Suspicious", "transaction_risk_score": 91},
    {"txn_id": "TXN-008", "txn_date": "2026-06-12", "bank": "CoopBank", "account_id": "OPC_LOCAL", "direction": "Debit", "description": "Local field survey advance", "amount": -28000000, "counterparty_id": "SUP-004", "txn_status": "Normal", "transaction_risk_score": 34},
    {"txn_id": "TXN-009", "txn_date": "2026-06-15", "bank": "VietinBank", "account_id": "OPC_MAIN", "direction": "Debit", "description": "Tax provisional payment", "amount": -68000000, "counterparty_id": "TAX", "txn_status": "Normal", "transaction_risk_score": 22},
    {"txn_id": "TXN-010", "txn_date": "2026-06-16", "bank": "VietinBank", "account_id": "OPC_MAIN", "direction": "Credit", "description": "Founder capital injection", "amount": 300000000, "counterparty_id": "FOUNDER", "txn_status": "Normal", "transaction_risk_score": 5},
]

# 09_CASHFLOW
CASHFLOW = [
    {"month": "2026-06", "expected_cash_in": 428000000, "expected_cash_out": 610000000, "direct_cost": 420000000, "opex": 122000000, "cash_reserve_minimum": 550000000, "projected_closing_cash": -160000000, "management_note": "Short-term pressure"},
    {"month": "2026-07", "expected_cash_in": 390000000, "expected_cash_out": 1030000000, "direct_cost": 710000000, "opex": 180000000, "cash_reserve_minimum": 550000000, "projected_closing_cash": -130000000, "management_note": "Needs credit line"},
    {"month": "2026-08", "expected_cash_in": 260000000, "expected_cash_out": 720000000, "direct_cost": 530000000, "opex": 165000000, "cash_reserve_minimum": 550000000, "projected_closing_cash": -155000000, "management_note": "Wait for milestone payment"},
    {"month": "2026-09", "expected_cash_in": 1600000000, "expected_cash_out": 880000000, "direct_cost": 630000000, "opex": 190000000, "cash_reserve_minimum": 550000000, "projected_closing_cash": 350000000, "management_note": "Recovery if invoice paid"},
    {"month": "2026-10", "expected_cash_in": 800000000, "expected_cash_out": 640000000, "direct_cost": 490000000, "opex": 160000000, "cash_reserve_minimum": 550000000, "projected_closing_cash": 150000000, "management_note": "Trade workflow collection"},
    {"month": "2026-11", "expected_cash_in": 1500000000, "expected_cash_out": 1200000000, "direct_cost": 880000000, "opex": 220000000, "cash_reserve_minimum": 550000000, "projected_closing_cash": 300000000, "management_note": "Second expansion phase"},
]

# 03_CUSTOMERS
CUSTOMERS = [
    {"customer_id": "CUS-001", "customer_name": "Hợp tác xã Nông sản An Phú", "customer_type": "Cooperative", "province": "Lâm Đồng", "industry": "Agriculture", "strategic_value": "Medium", "revenue_model": "Recurring", "payment_reliability": 0.78, "banking_fit_hint": "Team analysis required"},
    {"customer_id": "CUS-002", "customer_name": "Công ty May Sao Việt", "customer_type": "SME", "province": "Nam Định", "industry": "Manufacturing", "strategic_value": "High", "revenue_model": "Project", "payment_reliability": 0.64, "banking_fit_hint": "Team analysis required"},
    {"customer_id": "CUS-003", "customer_name": "Cửa hàng Minh Tâm", "customer_type": "Household", "province": "Đà Nẵng", "industry": "Retail", "strategic_value": "Low", "revenue_model": "Recurring", "payment_reliability": 0.42, "banking_fit_hint": "Team analysis required"},
    {"customer_id": "CUS-004", "customer_name": "Công ty Logistics Bắc Nam", "customer_type": "SME", "province": "TP. Hồ Chí Minh", "industry": "Logistics", "strategic_value": "High", "revenue_model": "Project", "payment_reliability": 0.71, "banking_fit_hint": "Team analysis required"},
    {"customer_id": "CUS-005", "customer_name": "Liên hiệp HTX Xanh", "customer_type": "Cooperative", "province": "Cần Thơ", "industry": "Agriculture", "strategic_value": "High", "revenue_model": "Project", "payment_reliability": 0.83, "banking_fit_hint": "Team analysis required"},
    {"customer_id": "CUS-006", "customer_name": "Công ty Dược An Khang", "customer_type": "SME", "province": "Hà Nội", "industry": "Healthcare", "strategic_value": "Medium", "revenue_model": "Recurring", "payment_reliability": 0.58, "banking_fit_hint": "Team analysis required"},
    {"customer_id": "CUS-007", "customer_name": "Hộ kinh doanh Phúc Lợi", "customer_type": "Household", "province": "Nghệ An", "industry": "Retail", "strategic_value": "Medium", "revenue_model": "Recurring", "payment_reliability": 0.36, "banking_fit_hint": "Team analysis required"},
    {"customer_id": "CUS-008", "customer_name": "Công ty Xuất khẩu Mekong", "customer_type": "SME", "province": "Cần Thơ", "industry": "Trade", "strategic_value": "High", "revenue_model": "Project", "payment_reliability": 0.74, "banking_fit_hint": "Team analysis required"},
]

# 05_PRODUCTS (services)
SERVICES = [
    {"service_id": "SVC-001", "service_name": "Digital Sales Setup", "pricing_model": "Initial setup", "list_price": 120000000, "target_margin": 0.32, "target_segment": "SME/Household"},
    {"service_id": "SVC-002", "service_name": "OrderOps Automation", "pricing_model": "Monthly subscription", "list_price": 45000000, "target_margin": 0.35, "target_segment": "SME/Cooperative"},
    {"service_id": "SVC-003", "service_name": "Customer Care Agent Pack", "pricing_model": "Monthly subscription", "list_price": 52000000, "target_margin": 0.38, "target_segment": "SME"},
    {"service_id": "SVC-004", "service_name": "Cooperative Network Rollout", "pricing_model": "Project", "list_price": 4200000000, "target_margin": 0.24, "target_segment": "Cooperative"},
    {"service_id": "SVC-005", "service_name": "Trade Document Workflow", "pricing_model": "Project", "list_price": 1850000000, "target_margin": 0.29, "target_segment": "Trade SME"},
]

# 02_OPC_PROFILE (các trường tài chính quan trọng)
PROFILE = {
    "company_id": "OPC-001",
    "company_name": "OPC Digital Operations Co.",
    "cash_reserve_minimum": 550000000,
    "target_gross_margin": 0.28,
    "late_delivery_penalty_rate": 0.015,
    "governance_rule": "Mọi quyết định tài chính trên 300 triệu VND hoặc gửi hồ sơ ra đối tác phải có human approval.",
}
