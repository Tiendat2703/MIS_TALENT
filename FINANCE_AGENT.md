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

Kiến trúc **agentic — LLM tự gọi tool** (giống Decision Agent), nhưng số liệu vẫn
chính xác tuyệt đối:

- LLM (Runner) tự gọi 6 `@function_tool` để lấy chỉ số. Mỗi lần gọi tool, hooks
  bắn event `tool_started`/`tool_finished` lên `event_bus` để FE thấy từng bước.
- **Chạy song song**: bật `parallel_tool_calls`, tool là `async` (offload qua
  `asyncio.to_thread`); 5 tool độc lập được gọi cùng một lượt và chạy đồng thời,
  `missing_data` gọi sau. Dữ liệu preload một lần để tránh nạp trùng.
- Mỗi tool tự nạp dữ liệu, gọi hàm tính thuần, rồi **lưu kết quả có cấu trúc vào
  run context (store)** — số KHÔNG đi qua LLM — và trả về cho LLM một dict gọn để
  đọc và diễn giải.
- Sau khi chạy, code **ráp Finance Feature Pack từ store** (số chính xác) cộng với
  `FinanceSynthesis` do LLM sinh (diễn giải, mức sẵn sàng, tóm tắt bàn giao).
- **Fallback tất định**: nếu LLM/agents không khả dụng (thiếu API key, lỗi mạng)
  hoặc `FINANCE_SKIP_LLM=true`, code tự chạy 6 bước và dùng diễn giải rule-based —
  luồng vẫn đủ end-to-end.

Vì sao giữ được số chính xác dù LLM cầm lái: LLM chỉ quyết định gọi tool và diễn
giải; toàn bộ con số do tool tính và cất vào context, code mới là bên ráp pack. LLM
không bao giờ tự sinh hay sửa số.

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

**Bước 7 — Tổng hợp & handoff.** Sau khi LLM đã gọi đủ 6 tool và có toàn bộ số, LLM
trả về `FinanceSynthesis` (readiness, pressure level, data confidence, diễn giải
margin, attention points cho Risk, tóm tắt handoff). Có **fallback rule-based** khi
LLM/`agents`/API không khả dụng để luồng vẫn chạy đủ.

---

## 3. Đã làm gì trong code

Toàn bộ nằm trong package `app` (song song Decision Agent), dùng chung `config`,
`hooks`, `bus`, `repository`.

| File | Vai trò |
|---|---|
| [app/Agent/financeAgent.py](app/Agent/financeAgent.py) | Orchestrator agentic: tạo Agent, chạy Runner (LLM gọi tool), ráp Feature Pack từ context, có fallback tất định + `__main__` |
| [app/tools/FinanceAgent/tools.py](app/tools/FinanceAgent/tools.py) | 6 `@function_tool` để LLM gọi + `FinanceRunContext` (store kết quả) |
| [app/schema/financeAgent.py](app/schema/financeAgent.py) | Dataclass: các phần Feature Pack + `FinanceSynthesis` (output_type của LLM) |
| [app/skills/financeAgent.md](app/skills/financeAgent.md) | Prompt: hướng dẫn LLM gọi đủ 6 tool rồi tổng hợp |
| [app/tools/FinanceAgent/finance_data.py](app/tools/FinanceAgent/finance_data.py) | Truy cập dữ liệu trực tiếp từ Supabase; lỗi DB sẽ dừng pipeline |
| [app/tools/FinanceAgent/validate_data.py](app/tools/FinanceAgent/validate_data.py) | Hàm tính bước 1 (validate) |
| [app/tools/FinanceAgent/reconcile.py](app/tools/FinanceAgent/reconcile.py) | Hàm tính bước 2 (reconcile) |
| [app/tools/FinanceAgent/liquidity.py](app/tools/FinanceAgent/liquidity.py) | Hàm tính bước 3 (liquidity) |
| [app/tools/FinanceAgent/invoices.py](app/tools/FinanceAgent/invoices.py) | Hàm tính bước 4 (phân loại invoice) |
| [app/tools/FinanceAgent/margin.py](app/tools/FinanceAgent/margin.py) | Hàm tính bước 5 (margin) |
| [app/tools/FinanceAgent/missing_data.py](app/tools/FinanceAgent/missing_data.py) | Hàm tính bước 6 (missing data) |
| [app/tools/FinanceAgent/data_request.py](app/tools/FinanceAgent/data_request.py) | Dựng form yêu cầu bổ sung từ dữ liệu thiếu + áp submission người dùng |
| [app/tools/FinanceAgent/util.py](app/tools/FinanceAgent/util.py) | parse ngày, ép số, format tiền |
| [app/tools/FinanceAgent/dump_schema.py](app/tools/FinanceAgent/dump_schema.py) | In tên bảng/cột Supabase để cập nhật `TABLES` |

### Cách chạy

```bash
# Chạy tính toán tất định trên dữ liệu Supabase thật, không gọi LLM:
FINANCE_SKIP_LLM=true python -m app.Agent.financeAgent

# Chạy với LLM và dữ liệu Supabase thật:
python -m app.Agent.financeAgent
```

Biến môi trường:
- `FINANCE_SKIP_LLM` (mặc định `false`): `true` để bỏ qua LLM nhưng vẫn tính từ
  dữ liệu Supabase thật.
- `FINANCE_REFERENCE_DATE` (vd `2026-07-17`): ngày tham chiếu tính overdue.

`FINANCE_USE_MOCK` và `FINANCE_SCENARIO` không còn được hỗ trợ. Nếu
`FINANCE_SCENARIO` được cấu hình, pipeline chủ động báo lỗi thay vì áp dữ liệu mô
phỏng.

### Kết quả tham chiếu lịch sử (không dùng làm dữ liệu runtime)

- Funding need **710,000,000**, **6/6 tháng dưới ngưỡng dự trữ** (06/07/08 âm tiền mặt).
- `requires_human_approval = true` (710M > ngưỡng 300M).
- Reconcile: confirmed cash **45M** (INV-001 ↔ TXN-004); INV-003 dù cùng 45M cùng
  CUS-001 vẫn không bị khớp nhầm; góp vốn founder 300M tách riêng.
- Invoice: paid 45M, overdue **325M** (INV-002 + INV-003), open 310M, not-issued **2.76B**.
- Margin: portfolio **27.62%** so target 28% (committed-only 31.52%); dưới target: CON-004 (24%), CON-002 (26.34%).
- Missing data: **9 mục** bám điều kiện thật.
- **Nhánh agentic (LLM thật, model gpt-5.5)**: LLM gọi **5 tool độc lập song song
  trong một lượt** (cùng mốc thời gian trên event bus) rồi `missing_data`, ra đúng
  các số trên và trả về `FinanceSynthesis` chuẩn. Event: `run_started` →
  `agent_started` → 5× `tool_started` (cùng lúc) → 5× `tool_finished` →
  `tool_started/finished` cho `missing_data` → `agent_finished` → `run_finished`.
- **Nhánh fallback tất định** (`FINANCE_SKIP_LLM=true`): ra cùng số, event dạng
  `finance_step` cho từng bước.

### Kết nối FE

FE `subscribe(run_id)` vào `event_bus` để nhận stream event từng bước, và
`get_snapshot(run_id)` để lấy trạng thái + kết quả cuối. Ở nhánh agentic, mỗi bước
là một cặp `tool_started`/`tool_finished` (có `tool_name`); ở nhánh fallback là
event `finance_step` (có `step`, `task`, `status`, `summary`).

### Xử lý dữ liệu thiếu — form yêu cầu bổ sung

Đọc dữ liệu thực tế từ Supabase và xử lý ca dữ liệu còn
thiếu bằng cách hỏi lại người dùng qua form, **tuyệt đối không bịa số**.

Luồng:
1. Dữ liệu đầu vào từ Supabase có trường bắt buộc đang thiếu (`null`).
2. Bước validate phát hiện đúng trường thiếu. Các bước tính **bỏ qua** phần thiếu
   thay vì coi là 0 (`liquidity.months_missing_data`, `margin.orders_missing_data`).
3. Code dựng `data_request_form` gồm đúng các trường thật đang thiếu (mỗi field ứng
   với một bản ghi + cột), pack trả về `status = AWAITING_INPUT` và bắn event
   `data_request_required` kèm form cho FE render.
4. Người dùng điền form, FE gửi lại `submission = {field_id: value}`. Gọi lại
   `run_finance_agent(..., submission=...)`: agent áp giá trị người dùng, chạy tiếp.
   Trường nào người dùng không điền vẫn được báo còn thiếu — agent không tự suy ra.

`field_id` có dạng `table|record|column` (vd `orders|ORD-004|estimated_cost`) để FE
gửi lại chính xác.

---

## 4. Tiếp theo cần làm

**Kết nối DB.** Runtime hiện đọc trực tiếp Supabase qua `finance_data.py`; không có
fallback sang dataset cục bộ.

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
