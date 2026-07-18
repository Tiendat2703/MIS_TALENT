# OPC — Quy trình nghiệp vụ (nguồn Mermaid để chỉnh sửa)

Dán đoạn code dưới vào **mermaid.live**, **VS Code (extension Mermaid Preview)**, hoặc **draw.io (Insert → Advanced → Mermaid)** để render và tùy chỉnh cho báo cáo.

Đây là bản **flowchart có cổng quyết định** (bổ trợ cho bản swimlane). Nếu cần đúng dạng swimlane (lane theo tác nhân) trong báo cáo, khuyến nghị vẽ lại bằng draw.io/Lucidchart để kiểm soát bố cục tốt hơn.

```mermaid
flowchart TD
    Start(["Bước 1 · Cơ hội kinh doanh<br/>CON-004 · 4,2 tỷ · 20 tỉnh"]):::start
    Start --> O

    O["Bước 2 · ORCHESTRATOR<br/>Phân loại, phân rã, định tuyến<br/>Dữ liệu: 02, 03, 04<br/>Output: kế hoạch + gói dữ liệu"]:::orch
    O --> F

    F["Bước 3 · DATA &amp; FINANCE<br/>Tổng hợp dòng tiền, tính funding gap, biên LN<br/>Dữ liệu: 04, 06, 07, 08, 09<br/>Output: Cashflow summary · Funding need · Missing-data"]:::fin
    F --> GA{"Cổng A<br/>Thiếu dữ liệu?"}:::gate
    GA -- "Có" --> REQ["Đòi chứng từ / tạm dừng<br/>(VD: tuổi nợ CR-001)"]:::gate
    REQ --> F
    GA -- "Không" --> R

    R["Bước 4 · RISK &amp; COMPLIANCE<br/>Áp risk rules, phân loại/gắn cờ dữ liệu nhạy cảm (chính sách), xác định điểm duyệt<br/>Dữ liệu: 08, 13, 14, 20<br/>Output: Risk level · Alerts · Required approvals"]:::risk
    R --> GB{"Cổng B<br/>Cảnh báo Critical? (RR-001)"}:::gate
    GB -- "Có (VD TXN-006/007)" --> HOLD["Giữ giao dịch + báo nhà sáng lập"]:::crit
    GB -- "Không" --> D

    D["Bước 5 · DECISION &amp; PARTNER<br/>Khớp sản phẩm NH, so sánh VietinBank/CoopBank/PartnerX<br/>Dữ liệu: 10, 11, 12 + output 3,4<br/>Output: Decision Card"]:::dec
    D --> GC{"Cổng C<br/>Độ tin cậy &lt; 0,65? (RR-006)"}:::gate
    GC -- "Có (bond 0,63)" --> NOREC["Không khuyến nghị / đòi bằng chứng"]:::gate
    NOREC --> D
    GC -- "Không" --> GD

    GD{"Cổng D<br/>&gt; 300tr hoặc gửi ra đối tác? (RR-005)"}:::gate
    GD -- "Cần duyệt" --> FOUND["Bước 6 · NHÀ SÁNG LẬP<br/>Phê duyệt / trả lại"]:::found
    FOUND -- "Không đồng ý" --> D
    FOUND -- "Đồng ý" --> EXEC
    GD -- "Không cần" --> EXEC

    EXEC["Bước 7 · THỰC THI (sau phê duyệt)<br/>Nộp precheck (dữ liệu đã che), sinh hồ sơ<br/>Dữ liệu: 11, 12, 21"]:::dec
    EXEC --> BANK["Bước 8 · ĐỐI TÁC NGÂN HÀNG<br/>Nhận &amp; phản hồi precheck (mô phỏng)<br/>API-002 / API-005"]:::bank
    BANK --> LOG["Bước 9 · GHI NHẬN &amp; CHỐT<br/>Audit log + so sánh before/after<br/>Dữ liệu: 25"]:::orch
    LOG --> E1(["Quyết định: NHẬN hợp đồng (có điều kiện)"]):::start
    LOG --> E2(["Quyết định: KHÔNG NHẬN hợp đồng"]):::crit

    classDef start fill:#2F7D57,stroke:#1C5E40,color:#fff;
    classDef orch fill:#123A5A,stroke:#0C2A42,color:#fff;
    classDef fin fill:#17786A,stroke:#0F5A4F,color:#fff;
    classDef risk fill:#2E6291,stroke:#1F4A70,color:#fff;
    classDef dec fill:#4A4E93,stroke:#353873,color:#fff;
    classDef found fill:#97722B,stroke:#725620,color:#fff;
    classDef bank fill:#5A6A7E,stroke:#44515F,color:#fff;
    classDef gate fill:#FBEFD6,stroke:#BE851F,color:#6E4B0E;
    classDef crit fill:#F6E7E5,stroke:#BF4A3F,color:#8A342B;
```

## Chú thích mã sheet (Team Pack)
- 02 OPC_PROFILE · 03 CUSTOMERS · 04 CONTRACTS · 06 ORDERS · 07 INVOICES
- 08 BANK_TXN · 09 CASHFLOW · 10 CREDIT_PROFILE · 11 BANK_PRODUCTS · 12 API_CATALOG
- 13 RISK_RULES · 14 ALERTS · 20 DATA_CLASS · 21 MASKING_EXAMPLES · 25 RUNTIME_LOG_SCHEMA

## Lớp Governance xuyên suốt (cross-cutting)
- **Che/token hoá dữ liệu** (CUS-005 → TOK-CUS-A91F): **thực thi tự động tại ranh giới tin cậy** (mỗi lần gọi API ngoài/LLM ngoài — Bước 7, 8). Risk & Compliance chỉ *định nghĩa chính sách* (sheet 20/21), không tự thực thi.
- **Audit log** (sheet 25): ghi nhận ở **mọi bước**.
- Đây là control **không thuộc riêng agent nào** — nên vẽ dưới dạng dải/nền bao trùm, hoặc chú thích riêng.

## 4 cổng kiểm soát (governance)
- **Cổng A** — thiếu dữ liệu → đòi chứng từ (PUB-002).
- **Cổng B** — cảnh báo Critical (RR-001) → giữ giao dịch + human-in-the-loop.
- **Cổng C** — độ tin cậy < 0,65 (RR-006) → không khuyến nghị.
- **Cổng D** — >300 triệu hoặc gửi hồ sơ ra đối tác (RR-005 / quy tắc OPC) → nhà sáng lập phê duyệt.
