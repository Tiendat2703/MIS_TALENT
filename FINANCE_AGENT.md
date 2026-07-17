# Finance Agent — Tài liệu triển khai (backend)

Tài liệu này mô tả: (1) các bước hiện tại của Finance Agent, (2) đã làm gì trong
code, (3) tiếp theo cần làm gì. Dùng cho vòng bán kết MIS Talent 2026.

---

## 1. Tổng quan & kiến trúc

Finance Agent trả lời các câu hỏi tài chính của OPC: có thiếu tiền không, thiếu
bao nhiêu, tháng nào, tiền nào đã thật sự về, margin có ổn không, dữ liệu nào còn
thiếu. Output là **Finance Feature Pack** gửi cho Risk Agent (và Decision Agent
đọc lại). Finance Agent **không** quyết định nhận/từ chối hợp đồng và **không**
chọn sản phẩm ngân hàng — đó là việc của Decision Agent.

Kiến trúc **code cầm lái + LLM tổng hợp** (kiểu B):

- Code chạy tuần tự các bước tính toán (deterministic), mỗi bước bắn event lên
  `event_bus` để FE hiển thị tiến trình realtime.
- Gom toàn bộ số đã tính thành `FINANCE_FACTS`, gọi LLM **một lần** để sinh phần
  diễn giải (mức sẵn sàng, mức áp lực, tóm tắt bàn giao). **LLM không tạo/sửa con
  số nào** — số liệu luôn khớp tuyệt đối với dữ liệu.
- Code ráp số + diễn giải thành Finance Feature Pack.

Lý do chọn kiểu B thay vì để LLM tự gọi từng tool: các bước tài chính là toán cố
định, luôn phải chạy hết, không có gì để LLM "quyết định gọi hay không". Để code
tính giúp nhanh, chắc số, ổn định khi demo; LLM lo phần diễn giải là chỗ nó thật
sự thêm giá trị.

---

## 2. Các bước hiện tại của agent

Bản báo cáo thiết kế có 8 bước; sau khi rà logic với dữ liệu thật, đã gộp và vá
thành **6 bước tính + 1 bước tổng hợp**. Các chỗ sửa quan trọng được ghi rõ.

| Bước | Việc | Bảng dùng | Code/LLM |
|---|---|---|---|
| 1 | Load & validate | tất cả | Code |
| 2 | Reconcile invoice ↔ bank txn | 07, 08 | Code |
| 3 | Liquidity & funding need | 09, 02 | Code |
| 4 | Phân loại invoice | 07 | Code |
| 5 | Margin | 06, 04, 02, 05 | Code |
| 6 | Missing data request | kết quả B1,2,4 | Code |
| 7 | Tổng hợp & handoff | — | LLM (có fallback) |

**Bước 1 — Load & validate.** Kiểm tra toàn vẹn tham chiếu, field bắt buộc, số
bất thường. Điểm đã vá: **không coi mọi counterparty của bank_txn là khách hàng**
— SUP-/TAX/FOUNDER là bên ngoài hợp lệ, UNK- là tín hiệu rủi ro chứ không phải
lỗi dữ liệu.

**Bước 2 — Reconcile.** Khớp invoice với giao dịch ngân hàng để tách tiền đã thu
với công nợ. Điểm đã vá (nghiêm trọng nhất): INV-001 và INV-003 cùng khách
CUS-001, cùng 45M — nếu chỉ so số tiền + khách sẽ khớp nhầm cả hai vào TXN-004.
Cách đúng: bắt buộc **invoice_id nằm trong description** và **một txn chỉ khớp
một invoice**. Ngoài ra loại góp vốn founder (TXN-010) và giao dịch không Normal
khỏi confirmed cash.

**Bước 3 — Liquidity & funding need.** Đã gộp bước tính projected closing cash cũ
vào đây: **chỉ đọc** `projected_closing_cash` (không tính lại, vì data không tái
tạo được và vốn là forecast cho sẵn). `reserve_gap = max(0, cash_reserve_minimum
− projected_closing_cash)`, `funding_need` = gap lớn nhất. Thêm
`net_operating_flow = expected_cash_in − expected_cash_out` để lộ tháng nào tự
thân âm dòng tiền. Bật cờ `requires_human_approval` khi funding_need > 300M
(ngưỡng governance).

**Bước 4 — Phân loại invoice.** paid / open / overdue / not-issued. Điểm đã vá:
**overdue không phải một status** mà tự suy ra = Open và due_date đã qua ngày tham
chiếu.

**Bước 5 — Margin.** `margin = order_revenue − estimated_cost`, gộp theo hợp đồng
và danh mục, so target. Báo cả **full-book** (mọi order) lẫn **committed-only**
(Delivered + In progress) để phân biệt cái đã chốt với kế hoạch.

**Bước 6 — Missing data request.** Điểm đã vá: **không dò bảng chứng từ (vì không
tồn tại)** mà bám điều kiện thật: invoice Open không có tiền về, invoice
Not-issued mà order chưa Delivered, credit khách không gắn invoice, counterparty
chưa định danh, lỗi validate.

**Bước 7 — Tổng hợp & handoff.** LLM nhận toàn bộ số đã tính, trả về
`FinanceSynthesis` (readiness, pressure level, data confidence, diễn giải margin,
attention points cho Risk, tóm tắt handoff). Có **fallback rule-based** khi chưa
có `agents`/API để luồng vẫn chạy đủ.

---

## 3. Đã làm gì trong code

Toàn bộ nằm trong package `app` (song song Decision Agent), dùng chung `config`,
`hooks`, `bus`, `repository`.

| File | Vai trò |
|---|---|
| [app/Agent/financeAgent.py](app/Agent/financeAgent.py) | Orchestrator: chạy 7 bước, bắn event, gọi LLM tổng hợp, ráp Feature Pack, có `__main__` chạy thử |
| [app/schema/financeAgent.py](app/schema/financeAgent.py) | Dataclass: các phần Feature Pack + `FinanceSynthesis` (output_type của LLM) |
| [app/skills/financeAgent.md](app/skills/financeAgent.md) | Prompt cho LLM tổng hợp |
| [app/tools/FinanceAgent/finance_data.py](app/tools/FinanceAgent/finance_data.py) | Truy cập dữ liệu: DB thật hoặc mock |
| [app/tools/FinanceAgent/mock_data.py](app/tools/FinanceAgent/mock_data.py) | Bản sao trung thực dữ liệu Team Pack |
| [app/tools/FinanceAgent/validate_data.py](app/tools/FinanceAgent/validate_data.py) | Bước 1 |
| [app/tools/FinanceAgent/reconcile.py](app/tools/FinanceAgent/reconcile.py) | Bước 2 |
| [app/tools/FinanceAgent/liquidity.py](app/tools/FinanceAgent/liquidity.py) | Bước 3 |
| [app/tools/FinanceAgent/invoices.py](app/tools/FinanceAgent/invoices.py) | Bước 4 |
| [app/tools/FinanceAgent/margin.py](app/tools/FinanceAgent/margin.py) | Bước 5 |
| [app/tools/FinanceAgent/missing_data.py](app/tools/FinanceAgent/missing_data.py) | Bước 6 |
| [app/tools/FinanceAgent/util.py](app/tools/FinanceAgent/util.py) | parse ngày, ép số, format tiền |

### Cách chạy

```bash
# Chạy end-to-end với mock + fallback (không cần DB, không cần API):
FINANCE_SKIP_LLM=true FINANCE_USE_MOCK=true python -m app.Agent.financeAgent

# Chạy với LLM thật (cần openai-agents + OPENAI_API_KEY trong app/.env):
FINANCE_USE_MOCK=true python -m app.Agent.financeAgent
```

Biến môi trường:
- `FINANCE_USE_MOCK` (mặc định `true`): dùng mock; đặt `false` để đọc Supabase.
- `FINANCE_SKIP_LLM` (mặc định `false`): `true` để bỏ qua LLM, dùng fallback.
- `FINANCE_REFERENCE_DATE` (vd `2026-07-17`): ngày tham chiếu tính overdue.

### Kết quả đã kiểm chứng (mock, ngày 2026-07-17)

- Funding need **710,000,000**, **6/6 tháng dưới ngưỡng dự trữ** (06/07/08 âm tiền mặt).
- `requires_human_approval = true` (710M > ngưỡng 300M).
- Reconcile: confirmed cash **45M** (INV-001 ↔ TXN-004); INV-003 dù cùng 45M cùng
  CUS-001 vẫn không bị khớp nhầm; góp vốn founder 300M tách riêng.
- Invoice: paid 45M, overdue **325M** (INV-002 + INV-003), open 310M, not-issued **2.76B**.
- Margin: portfolio **27.62%** so target 28% (committed-only 31.52%); dưới target: CON-004 (24%), CON-002 (26.34%).
- Missing data: **9 mục** bám điều kiện thật.
- Event realtime: 16 event (run_started → 7 bước → run_finished) bắn lên `event_bus`.

### Kết nối FE

FE `subscribe(run_id)` vào `event_bus` để nhận stream event từng bước, và
`get_snapshot(run_id)` để lấy trạng thái + kết quả cuối. Payload event gồm
`type`, `step`, `task`, `status`, `summary`.

---

## 4. Tiếp theo cần làm

**Kết nối DB (ưu tiên 1).** Đang dùng mock. Cần chạy script dump schema Supabase
để lấy đúng tên bảng và cột, rồi cập nhật `TABLES` trong
[finance_data.py](app/tools/FinanceAgent/finance_data.py) và đặt
`FINANCE_USE_MOCK=false`. Lưu ý `order` là từ khóa SQL nên đã để trong ngoặc kép.

**Bật LLM thật.** Cần `openai-agents` và `OPENAI_API_KEY` trong `app/.env`. Luồng
LLM đã wire theo đúng pattern Decision Agent (Agent + Runner + output_type +
hooks), nạp trễ nên chỉ cần khi thật sự gọi.

**Nối pipeline.** Finance Feature Pack là input cho Validate → Risk; Decision đọc
lại Finance Feature Pack + Risk Pack. Cần thống nhất khóa dữ liệu khi ghép.

**Giai đoạn 2 (khai thác sâu hơn dữ liệu).** Các nâng cấp đã bàn, chưa làm:
- Cân AR theo `payment_reliability` (03_CUSTOMERS) để ra khoản thu thực tế kỳ vọng.
- Dựng projection bottom-up từ invoice/AR rồi so với forecast của OPC (chênh lệch là insight); lúc đó công thức tính closing cash mới quay lại có ý nghĩa.
- Dùng `order.status`/`delivery_note` sâu hơn cho điều kiện phát hành invoice và rủi ro giao hàng.
- Đối chiếu `contract.gross_margin` cho sẵn với margin tính từ order như tín hiệu chất lượng dữ liệu.
- Chuyển phần `business_impact` của từng mục missing data sang cho LLM viết (hiện đang là mức mặc định do code đặt).

**Ghi chú quyết định thiết kế:**
- Bước 3 đã gộp (chỉ đọc projected_closing_cash, không tính lại).
- Margin báo cả full-book lẫn committed-only.
- need_type (loại vốn) là việc của Decision Agent, Finance chỉ đưa số tiền + cơ sở.
- Không có bảng chứng từ/evidence trong data; missing data bám điều kiện thật.
