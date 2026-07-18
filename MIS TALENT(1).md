## **Risk Agent Brief**

m

## Risk Agent Workflow — Bản chỉnh đúng theo event-driven flow

### Step 1 — Nhận trigger kích hoạt Risk Agent

Risk Agent có thể được kích hoạt bởi nhiều loại trigger khác nhau.

Trigger chính trong luồng realtime là callback/webhook từ ngân hàng. Khi có giao dịch mới phát sinh, ngân hàng sẽ gọi callback URL của hệ thống OPC. Callback này đóng vai trò như tín hiệu báo rằng có giao dịch mới cần kiểm tra rủi ro.

Ví dụ callback từ ngân hàng:

{  
  "event\_type": "NEW\_TRANSACTION",  
  "transaction\_id": "TXN-NEW-001",  
  "account\_id": "TOK-ACC-7D20",  
  "event\_time": "2026-07-04T10:30:00+07:00"  
}

Trong phạm vi bài thi, nhóm giả định callback từ ngân hàng là hợp lệ, nên không cần xử lý bước xác thực callback.

Ngoài trigger realtime, Risk Agent cũng có thể được chạy theo batch/manual scan trên dữ liệu tĩnh để kiểm tra các giao dịch đã có sẵn trong dataset. Tuy nhiên, đây là một chế độ chạy khác, không phải bước bắt buộc trước callback ngân hàng.

### Step 2 — Gọi API ngân hàng để lấy chi tiết giao dịch mới

Khi nhận callback realtime, Risk Agent sẽ dùng transaction\_id để gọi API giả định của ngân hàng nhằm lấy chi tiết giao dịch và risk score.

Ví dụ API giả định:

GET /openapi/v1/transactions/{transaction\_id}/risk-score

Kết quả trả về có thể gồm:

{  
  "transaction\_id": "TXN-NEW-001",  
  "account\_id": "TOK-ACC-7D20",  
  "amount": 185000000,  
  "direction": "OUT",  
  "counterparty": "SUP-UNKNOWN",  
  "transaction\_time": "2026-07-04T10:30:00+07:00",  
  "bank\_risk\_score": 0.91,  
  "bank\_risk\_reason": \[  
    "High amount compared with normal pattern",  
    "Unknown counterparty",  
    "Unusual transaction time"  
  \]  
}

Nếu R1 bị kích hoạt ở mức nghiêm trọng, Risk Agent sẽ tạo alert tương ứng và gọi API giả định của ngân hàng để yêu cầu chặn giao dịch.

Ví dụ API giả định để chặn giao dịch:

POST /openapi/v1/transactions/{transaction\_id}/block

Payload mẫu:

{  
  "transaction\_id": "TXN-NEW-001",  
  "reason\_code": "ABNORMAL\_TRANSACTION\_RISK",  
  "risk\_score": 0.91,  
  "requested\_by": "Risk Agent"  
}

**Bước 1,2 sẽ làm song song và tách biệt với các bước còn lại** 

### Step 3 — Load dữ liệu context để evaluate risk rule

Sau khi có giao dịch mới hoặc khi chạy batch scan, Risk Agent sẽ load các dữ liệu cần thiết để đánh giá risk rule.

Các input chính gồm:

\- 08\_BANK\_TXN: dữ liệu giao dịch lịch sử / giao dịch đã có trong dataset  
\- 13\_RISK\_RULES: bộ rule dùng để kiểm tra rủi ro  
\- 14\_ALERTS: danh sách alert tương ứng với các rule  
\- 20\_DATA\_CLASS: chính sách masking dữ liệu  
\- Finance Feature Pack: output từ Finance Agent

Trong đó, 08\_BANK\_TXN không nên được hiểu là một bước trigger đứng trước callback ngân hàng. Nó là dữ liệu nền để Risk Agent so sánh, đối chiếu và phát hiện bất thường.

Ví dụ, khi kiểm tra một giao dịch mới, Risk Agent có thể dùng 08\_BANK\_TXN để biết:

\- Giao dịch này có lớn bất thường so với lịch sử không?  
\- Counterparty này đã từng xuất hiện chưa?  
\- Tài khoản này trước đây có giao dịch pending/failed/high-risk không?  
\- Pattern giao dịch hiện tại có lệch khỏi dữ liệu quá khứ không?

### Step 4 — Kiểm tra R1: giao dịch bất thường

Risk Agent kiểm tra R1 bằng cách kết hợp:

\- Giao dịch mới từ callback ngân hàng  
\- Risk score lấy từ API ngân hàng  
\- Dữ liệu lịch sử trong 08\_BANK\_TXN  
\- Rule R1 trong 13\_RISK\_RULES

Ví dụ logic:

Nếu bank\_risk\_score \>= ngưỡng rủi ro  
hoặc số tiền giao dịch lớn bất thường so với lịch sử  
hoặc counterparty chưa từng xuất hiện trong 08\_BANK\_TXN  
hoặc tài khoản có nhiều giao dịch pending/failed/high-risk  
\=\> kích hoạt R1: Abnormal Transaction Risk

Nếu R1 bị kích hoạt ở mức nghiêm trọng, Risk Agent sẽ tạo alert tương ứng và gọi API giả định của ngân hàng để yêu cầu chặn giao dịch.

Ví dụ API giả định để chặn giao dịch:

POST /openapi/v1/transactions/{transaction\_id}/block

Payload mẫu:

{  
  "transaction\_id": "TXN-NEW-001",  
  "reason\_code": "ABNORMAL\_TRANSACTION\_RISK",  
  "risk\_score": 0.91,  
  "requested\_by": "Risk Agent"  
}

Risk Agent không trực tiếp chặn giao dịch trong hệ thống ngân hàng. Agent chỉ gọi API ngân hàng để gửi yêu cầu chặn. Trạng thái chặn thành công hay không phụ thuộc vào phản hồi từ ngân hàng.

### Step 5 — Scan các rule R2 đến R7 bằng Finance Feature Pack

Sau khi xử lý R1, Risk Agent tiếp tục dùng Finance Feature Pack từ Finance Agent để scan các rule R2 đến R7.

Finance Feature Pack có thể gồm:

\- Liquidity Brief  
\- AR Insight  
\- Bank Reconciliation Insight  
\- Invoice Issuance Insight  
\- Margin Analysis  
\- Funding Need Analysis  
\- Missing Data Requests

Các rule R2 đến R7 có thể được hiểu như sau:

R2 — Liquidity Risk:  
Dòng tiền dự kiến thấp hơn mức dự trữ tiền mặt tối thiểu.

R3 — AR / Collection Risk:  
Có hóa đơn chưa thu, hóa đơn quá hạn hoặc khoản phải thu chưa chuyển thành tiền thật.

R4 — Bank Reconciliation Risk:  
Có giao dịch ngân hàng không khớp invoice, giao dịch pending, failed hoặc unmatched.

R5 — Missing Document Risk:  
Thiếu chứng từ cần thiết như supplier confirmation, acceptance record, receivable aging evidence.

R6 — Contract / Progress Risk:  
Hợp đồng hoặc order có vấn đề về tiến độ, nghiệm thu hoặc chưa đủ điều kiện ghi nhận.

R7 — Margin / Human Approval Risk:  
Biên lợi nhuận thấp, funding need lớn hoặc credit case cần human approval/review.

### Step 6 — Map triggered rule sang alert

Với mỗi risk rule bị kích hoạt, Risk Agent sẽ tra bảng 14\_ALERTS để lấy alert tương ứng.

Ví dụ:

R1\_ABNORMAL\_TRANSACTION  
\=\> ALERT\_HIGH\_RISK\_BANK\_TXN

R2\_LIQUIDITY\_GAP  
\=\> ALERT\_CASHFLOW\_STRESS

R5\_MISSING\_DOCUMENT  
\=\> ALERT\_MISSING\_REQUIRED\_DOCS

Nếu rule đã có alert mapping trong bảng 14\_ALERTS, Risk Agent lấy trực tiếp alert đó ra.

Nếu rule bị kích hoạt nhưng chưa có alert mapping rõ ràng, Risk Agent sẽ tạo proposed alert và đánh dấu là cần human review.

### Step 7 — Masking dữ liệu nhạy cảm

Trước khi output ra dashboard hoặc gửi sang Decision Agent, Risk Agent masking các dữ liệu nhạy cảm dựa trên 20\_DATA\_CLASS.

Các dữ liệu nên masking gồm:

\- account\_id  
\- transaction\_id  
\- counterparty\_account  
\- bank account number  
\- customer sensitive information  
\- raw bank transaction reference

Ví dụ:

account\_id: ACC-123456789 → TOK-ACC-7D20  
transaction\_id: TXN-20260704-0001 → TOK-TXN-A91F  
counterparty\_account: 9704\*\*\*\*\*\*\*\*1234

### Step 8 — Xuất Risk Alert Pack

Output cuối cùng của Risk Agent là Risk Alert Pack, gồm ba nhóm chính:

1\. Triggered risk rules  
2\. Detected alerts  
3\. Masked data

Risk Agent không tạo Decision Card và không ra quyết định cuối cùng. Agent chỉ phát hiện rủi ro, tạo alert, gọi API chặn giao dịch nếu R1 nghiêm trọng, và gửi kết quả cho Decision Agent hoặc dashboard.

**Schema Output**

{

  "risk\_pack\_id": "RISK-PACK-20260704-001",

  "company\_id": "OPC-001",

  "generated\_at": "2026-07-04T10:35:00+07:00",

  "triggered\_risk\_rules": \[

    {

      "rule\_id": "R1",

      "rule\_name": "Transaction Anomaly",

      "risk\_category": "BANK\_TRANSACTION",

      "severity": "Critical",

      "risk\_score": 90,

      "affected\_records": \[

        {

          "record\_type": "BANK\_TRANSACTION",

          "record\_id": "TXN-006",

          "source": "08\_BANK\_TXN",

          "evidence": {

            "transaction\_time": "02:13",

            "transaction\_type": "Ecommerce debit",

            "amount": 185000000,

            "reason": "Abnormal ecommerce debit at unusual time"

          }

        },

        {

          "record\_type": "BANK\_TRANSACTION",

          "record\_id": "TXN-007",

          "source": "08\_BANK\_TXN",

          "evidence": {

            "transaction\_time": "02:17",

            "transaction\_type": "Ecommerce debit",

            "amount": 172000000,

            "reason": "Repeated abnormal ecommerce debit within short time window"

          }

        }

      \],

      "action": {

        "action\_type": "BLOCK\_TRANSACTION",

        "api\_called": true,

        "api\_endpoint": "/openapi/v1/transactions/{transaction\_id}/block",

        "action\_status": "BLOCK\_REQUESTED"

      }

    },

    {

      "rule\_id": "R7",

      "rule\_name": "Low Margin Contract",

      "risk\_category": "CONTRACT\_MARGIN",

      "severity": "Medium",

      "risk\_score": 72,

      "affected\_records": \[

        {

          "record\_type": "CONTRACT",

          "record\_id": "CON-005",

          "source": "04\_CONTRACTS / Finance Feature Pack",

          "evidence": {

            "estimated\_margin\_rate": 0.092,

            "target\_margin\_rate": 0.15,

            "reason": "Contract margin is lower than target margin"

          }

        }

      \],

      "action": {

        "action\_type": "HUMAN\_REVIEW\_MARGIN",

        "api\_called": false,

        "api\_endpoint": null,

        "action\_status": "REVIEW\_REQUIRED"

      }

    },

    {

      "rule\_id": "R6",

      "rule\_name": "Contract Progress Risk",

      "risk\_category": "CONTRACT\_PROGRESS",

      "severity": "Medium",

      "risk\_score": 66,

      "affected\_records": \[

        {

          "record\_type": "CONTRACT",

          "record\_id": "CON-004",

          "source": "04\_CONTRACTS / Finance Feature Pack",

          "evidence": {

            "contract\_status": "In progress",

            "acceptance\_status": "Not confirmed",

            "reason": "Contract has not reached acceptance stage but financial action is being considered"

          }

        }

      \],

      "action": {

        "action\_type": "PROPOSE\_NEW\_ALERT",

        "api\_called": false,

        "api\_endpoint": null,

        "action\_status": "HUMAN\_REVIEW\_REQUIRED"

      }

    }

  \],

  "detected\_alerts": \[

    {

      "alert\_id": "AL-001",

      "alert\_date": "2026-06-17",

      "alert\_type": "Transaction anomaly",

      "related\_record": \[

        "TXN-006",

        "TXN-007"

      \],

      "severity": "Critical",

      "risk\_score": 90,

      "description": "Two abnormal ecommerce debits at 02:13 and 02:17",

      "recommended\_action": "Hold and request founder confirmation",

      "mapped\_rule\_id": "R1",

      "alert\_source": "14\_ALERTS"

    },

    {

      "alert\_id": "AL-002",

      "alert\_date": "2026-06-18",

      "alert\_type": "Low margin contract",

      "related\_record": \[

        "CON-005"

      \],

      "severity": "Medium",

      "risk\_score": 72,

      "description": "Contract margin is lower than target margin",

      "recommended\_action": "Review contract margin before approval",

      "mapped\_rule\_id": "R7",

      "alert\_source": "14\_ALERTS"

    }

  \],

  "proposed\_alerts": \[

    {

      "proposed\_alert\_id": "PAL-001",

      "proposed\_date": "2026-07-04",

      "alert\_type": "Contract progress risk",

      "related\_record": \[

        "CON-004"

      \],

      "severity": "Medium",

      "risk\_score": 66,

      "description": "Contract has not reached acceptance stage but financial action is being considered",

      "recommended\_action": "Review contract progress and acceptance evidence before further processing",

      "proposed\_for\_rule\_id": "R6",

      "reason\_for\_proposal": "Risk rule R6 was triggered but no exact alert mapping was found in 14\_ALERTS",

      "alert\_source": "AGENT\_PROPOSED",

      "requires\_human\_review": true

    }

  \],

  "masked\_data": {

    "masking\_applied": true,

    "masking\_policy\_source": "20\_DATA\_CLASS",

    "masked\_fields": \[

      {

        "field\_name": "account\_id",

        "record\_type": "BANK\_ACCOUNT",

        "source\_record\_id": "ACC-001",

        "masked\_value": "TOK-ACC-7D20"

      },

      {

        "field\_name": "transaction\_id",

        "record\_type": "BANK\_TRANSACTION",

        "source\_record\_id": "TXN-006",

        "masked\_value": "TOK-TXN-006"

      },

      {

        "field\_name": "transaction\_id",

        "record\_type": "BANK\_TRANSACTION",

        "source\_record\_id": "TXN-007",

        "masked\_value": "TOK-TXN-007"

      }

    \]

  },

  "summary": {

    "total\_rules\_triggered": 3,

    "triggered\_rule\_ids": \[

      "R1",

      "R7",

      "R6"

    \],

    "total\_alerts\_detected": 2,

    "total\_proposed\_alerts": 1,

    "unmapped\_rule\_ids": \[

      "R6"

    \],

    "highest\_severity": "Critical",

    "human\_review\_required": true,

    "decision\_made\_by\_risk\_agent": false

  }

}

