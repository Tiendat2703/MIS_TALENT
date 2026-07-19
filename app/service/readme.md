# Transaction Anomaly Monitor

`transaction_anomaly_monitor.py` là service polling độc lập với contract Risk
Agent. Service không đăng ký `@function_tool`, không cần `case_id`, `contract_id`
hoặc `session_id`, và không tạo bảng state/checkpoint.

```text
bank_txn -> TransactionAnomalyMonitor -> alert

FinanceFeaturePack -> build_risk_pack -> đọc alert -> save_risk_pack
```

## Chạy service

Trong virtual environment của dự án:

```powershell
# Quét liên tục mỗi 2 giây
python -m app.service.transaction_anomaly_monitor

# Thay đổi chu kỳ polling
python -m app.service.transaction_anomaly_monitor --poll-seconds 5

# Quét đúng một lần rồi đóng database pool
python -m app.service.transaction_anomaly_monitor --once
```

Nhấn `Ctrl+C` để yêu cầu shutdown. Service hoàn thành database query hiện tại,
không bắt đầu vòng quét mới, đóng pool và in thông báo shutdown.

## Luồng một vòng quét

1. `load_transaction_anomaly_rules()` đọc các rule transaction anomaly từ
   `risk_rule`. Ngưỡng và operator nằm trong `trigger_condition`, không nằm trong
   code service.
2. `find_existing_transaction_alerts()` lập index alert deterministic và tách
   các transaction ID trong `related_record` của alert legacy.
3. `fetch_bank_transactions()` đọc toàn bộ `bank_txn` cho prototype.
4. `evaluate_transaction_rule()` đánh giá từng transaction/rule và trả
   `TRIGGERED`, `NOT_TRIGGERED` hoặc `INSUFFICIENT_EVIDENCE`.
5. `build_transaction_alert()` tạo payload cho kết quả `TRIGGERED`.
6. `upsert_transaction_alert()` ghi alert bằng `INSERT ... ON CONFLICT`.
7. `scan_transaction_anomalies_once()` trả `TransactionMonitorReport` đã loại
   dữ liệu nhạy cảm.
8. `run_transaction_monitor()` điều khiển polling, backoff và shutdown.

Điều kiện transaction hiện hỗ trợ metric `transaction_risk_score` cùng các
operator `>`, `>=`, `<`, `<=`, `=`. Severity, risk type và recommended action
luôn lấy từ row `risk_rule`.

## Idempotency và alert legacy

Alert ID được tạo cố định từ cặp transaction/rule:

```python
digest = sha256(f"{txn_id}:{rule_id}".encode()).hexdigest()[:12]
alert_id = f"AL-TXN-{digest}"
```

Vì `alert_id` là primary key và câu lệnh ghi dùng `ON CONFLICT`, polling lặp,
restart service hoặc hai process chạy đồng thời không tạo thêm row cho cùng một
cặp transaction/rule.

Các alert legacy có thể chứa nhiều ID, ví dụ `TXN-006, TXN-007`. Nếu transaction
đã xuất hiện trong alert legacy có cùng `alert_type` với `risk_type` của rule,
service tính là `existing` và không sinh alert deterministic mới. Alert
deterministic đã tồn tại nhưng score/metadata thay đổi sẽ được update.

Service không sửa `txn_status`, không hold/block transaction và không tự resolve
alert khi transaction trở lại normal.

## Log an toàn

Mỗi vòng chỉ có một summary:

```text
[TXN MONITOR] rules=1 scanned=12 triggered=1 created=1 updated=0 existing=2 insufficient=0 errors=0
```

Khi insert alert mới:

```text
[ANOMALY] txn=TOK-TXN-XXXXXXXX rule=RR-001 severity=CRITICAL
```

Raw transaction ID chỉ được dùng trong database payload. Report/log không chứa
raw transaction, amount, account, counterparty hoặc password.

## Test

```powershell
python -m pytest tests/test_transaction_anomaly_monitor.py -q
```

Để demo an toàn, chạy `--once` trước để xác nhận rule RR-001 và hai transaction
legacy được nhận đúng, sau đó chạy polling liên tục và inject lần lượt một
transaction score `20` và một transaction score `90`.
