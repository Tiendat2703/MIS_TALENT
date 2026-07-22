# Build Risk Pack

`BuildRiskReport.py` xây dựng một `RiskPack` cho đúng một hợp đồng từ
`FinanceFeaturePack` do Data & Finance Agent cung cấp. Module không đọc lại dữ
liệu tài chính của hợp đồng và không đưa ra quyết định chấp nhận hoặc từ chối
hợp đồng.

## Luồng xử lý

```text
FinanceFeaturePack
    -> đọc toàn bộ risk_rule từ PostgreSQL
    -> đánh giá từng rule trên các metric trong pack
    -> xác định rule bị kích hoạt và mức severity cao nhất
    -> đọc và ghép các alert hiện có
    -> mask identifier và giá trị nhạy cảm
    -> xác định có cần human approval
    -> RiskPack
    -> lưu RiskPack dạng JSON vào public.context.risk_pack
```

Risk Agent cung cấp hai function tool công khai là `build_risk_pack` và
`save_risk_pack`. Các hàm còn lại là helper nội bộ hoặc implementation thuần để
có thể kiểm thử mà không đi qua Agent SDK.

## Đầu vào

`FinanceFeaturePack` chứa thông tin định danh của case và tám metric có thể
nhận giá trị `null`:

| Field | Ý nghĩa trong quá trình đánh giá |
| --- | --- |
| `case_id` | Định danh của lần xử lý nghiệp vụ |
| `contract_id` | Hợp đồng đang được đánh giá |
| `company_id` | Công ty liên quan đến hợp đồng |
| `generated_at` | Thời điểm Data & Finance Agent tạo pack |
| `transaction_risk_score` | Điểm rủi ro giao dịch, từ 0 đến 100 |
| `projected_closing_cash` | Số dư tiền dự kiến cuối kỳ |
| `cash_reserve_minimum` | Mức dự trữ tiền tối thiểu |
| `gross_margin` | Biên lợi nhuận gộp |
| `document_sent_to_partner` | Trạng thái gửi tài liệu cho đối tác |
| `requested_amount` | Số tiền được yêu cầu |
| `confidence_score` | Độ tin cậy của dữ liệu, từ 0 đến 1 |
| `delivery_delay_days` | Số ngày giao hàng chậm |
| `source_record_ids` | Các record nguồn dùng để ghép alert |

Giá trị thiếu phải được giữ là `null`. Tool không tự đổi `null` thành `0`,
`false` hoặc một giá trị ước lượng.

## Cú pháp risk rule

`trigger_condition` trong bảng `risk_rule` phải có dạng:

```text
<metric> <operator> <target>
```

Các operator được hỗ trợ là `>`, `>=`, `<`, `<=` và `=`. Target có thể là số,
boolean hoặc tên của một metric khác trong pack.

Ví dụ:

```text
transaction_risk_score >= 80
closing_cash < cash_reserve_minimum
document_sent_to_partner = false
```

`closing_cash` là alias của `projected_closing_cash`. Các metric được hỗ trợ:

- `transaction_risk_score`
- `closing_cash`
- `projected_closing_cash`
- `cash_reserve_minimum`
- `gross_margin`
- `document_sent_to_partner`
- `requested_amount`
- `confidence_score`
- `delivery_delay_days`

## Các hàm trong module

### `_related_records(value)`

Tách chuỗi `alert.related_record` phân cách bằng dấu phẩy thành một `set[str]`.
Khoảng trắng và phần tử rỗng được loại bỏ. Kết quả được dùng để kiểm tra giao
nhau với `FinanceFeaturePack.source_record_ids`.

### `_parse_literal(value)`

Chuyển target trong điều kiện thành:

- `bool` nếu target là `true` hoặc `false`;
- `float` nếu target là một số;
- `str` trong các trường hợp còn lại.

Target dạng chuỗi được hiểu là tên metric tham chiếu trong
`FinanceFeaturePack`, không phải một string literal tùy ý.

### `_pack_value(finance_pack, metric)`

Ánh xạ tên metric trong rule sang field tương ứng của `FinanceFeaturePack` và
trả về giá trị. Hàm trả `None` nếu metric không được hỗ trợ.

### `_masked_value(metric, value)`

Chuẩn bị giá trị quan sát để đưa vào `RuleEvaluation`:

- trả `None` nếu không có giá trị;
- trả `[CONFIDENTIAL_VALUE]` cho metric tài chính nhạy cảm;
- trả chuỗi biểu diễn của giá trị cho các metric còn lại.

Các metric được mask gồm `closing_cash`, `projected_closing_cash`,
`cash_reserve_minimum`, `gross_margin` và `requested_amount`.

### `_evaluate_finance_rule(rule, finance_pack)`

Đánh giá một `RiskRule` theo scope trên một `FinanceFeaturePack` và trả về
`RuleEvaluation`. Applicability luôn được kiểm tra trước metric:

| Trạng thái | Điều kiện |
| --- | --- |
| `TRIGGERED` | Dữ liệu đầy đủ và điều kiện của rule đúng |
| `NOT_TRIGGERED` | Dữ liệu đầy đủ nhưng điều kiện của rule sai |
| `NOT_APPLICABLE` | Rule chưa áp dụng cho object/bước hiện tại |
| `INSUFFICIENT_EVIDENCE` | Rule áp dụng nhưng thiếu dữ liệu nghiệp vụ |
| `RULE_CONFIGURATION_ERROR` | Condition hoặc source mapping không hợp lệ |
| `RULE_INACTIVE` | Rule master thật cấu hình không hoạt động |

Thiếu dữ liệu không được xem là `NOT_TRIGGERED`. Tên các field còn thiếu được
ghi vào `missing_fields`.

### `_match_finance_pack_alerts(finance_pack, rules, evaluations)`

Ghép các alert hiện có với hợp đồng và những rule đã `TRIGGERED`:

1. `RELATED_RECORD` nếu `alert.related_record` khớp một phần tử trong
   `source_record_ids`.
2. `EXACT_RISK_TYPE` nếu `alert.alert_type` trùng với `risk_type` của một rule
   đã kích hoạt, không phân biệt chữ hoa và chữ thường.
3. Alert không khớp theo cả hai cách sẽ không được đưa vào `RiskPack`.

`matched_rule_ids` chỉ chứa các rule đã kích hoạt có `risk_type` khớp với
`alert_type`. Vì vậy một alert khớp record vẫn có thể có
`matched_rule_ids=[]` nếu không có risk type tương ứng. Identifier trong alert
được mask trước khi trả ra ngoài.

### `_requires_human_approval(evaluation)`

Trả `True` khi rule đang `TRIGGERED` và `required_action` chứa `approval`,
`founder` hoặc `human`. Severity cao tự nó không tạo approval.

### `build_risk_pack_impl(finance_pack)`

Đây là implementation chính:

1. Đọc toàn bộ rule bằng `get_risk_rules_impl()`; không hard-disable RR-005.
2. Gọi `_evaluate_finance_rule()` theo scope; RR-001 có CONTRACT và PORTFOLIO.
3. Giữ `overall_risk_level=null`; tính highest severity riêng theo hai scope.
4. Tạo union `triggered_rule_ids` và hai danh sách triggered theo scope.
5. Gom và loại bỏ action trùng lặp trong `required_actions`.
6. Gom dữ liệu thiếu theo dạng `<rule_id>:<field>`.
7. Ghép alert bằng `_match_finance_pack_alerts()`.
8. Xác định `human_approval_required`.
9. Trả về model `RiskPack`.

Hàm này phù hợp cho unit test vì trả trực tiếp Pydantic model và không phụ thuộc
vào cơ chế gọi tool của Agent SDK.

### `build_risk_pack(finance_pack)`

Đây là function tool thực hiện việc xây dựng Risk Pack:

```python
@function_tool
def build_risk_pack(finance_pack: FinanceFeaturePack) -> str:
    return build_risk_pack_impl(finance_pack).model_dump_json(indent=2)
```

Tool gọi implementation chính và serialize `RiskPack` thành JSON string có
indent. Risk Agent phải gọi tool đúng một lần cho mỗi `FinanceFeaturePack` hoàn
chỉnh.

### `save_risk_pack_impl(session_id, risk_pack)`

Cập nhật `risk_pack` trên một row đã tồn tại trong `public.context`:

```sql
UPDATE public.context
SET risk_pack = %s::json
WHERE session_id = %s
  AND finance_pack ->> 'case_id' = %s
  AND finance_pack ->> 'contract_id' = %s
RETURNING session_id
```

JSON và `session_id` được truyền dưới dạng query parameters, không được nối
trực tiếp vào SQL. Hàm serialize Pydantic `RiskPack` bằng `model_dump_json()` và
trả về `RiskPackSaveResult` sau khi cập nhật thành công.

Hàm chỉ cập nhật khi `case_id` và `contract_id` trong `context.finance_pack`
khớp với `RiskPack`, tránh ghi nhầm pack sang session khác. Hàm phát sinh
`LookupError` nếu không tồn tại row tương ứng hoặc identity không khớp. Tool
không tự insert row mới vì `context.finance_pack` là field bắt buộc và phải được
tạo bởi workflow phía trước.

### `save_risk_pack(session_id, risk_pack)`

Function tool thứ hai được đăng ký cho Risk & Compliance Agent:

```python
@function_tool
def save_risk_pack(
    session_id: int,
    risk_pack: RiskPack,
) -> RiskPackSaveResult:
    return save_risk_pack_impl(session_id, risk_pack)
```

Agent chỉ gọi tool này sau khi `build_risk_pack` thành công. `risk_pack` truyền
vào phải là object nguyên vẹn vừa được build; agent không được tính lại hoặc
thay đổi bất kỳ field nào.

Acknowledgement trả về gồm:

- `session_id`;
- `case_id`;
- `contract_id`;
- `saved=true`.

## Thứ tự gọi tool

```text
1. build_risk_pack(finance_pack)
2. Parse JSON trả về thành RiskPack
3. save_risk_pack(session_id, risk_pack)
4. Trả RiskPack không thay đổi làm final output
```

`session_id` là khóa chính kiểu `bigint` của một row đã tồn tại trong bảng
`context`. Giá trị này phải được workflow truyền riêng cho Risk Agent; không
được suy ra từ `case_id` hoặc `contract_id`.

## Đầu ra `RiskPack`

Kết quả bao gồm:

- `case_id`, `contract_id` và `generated_at`;
- `overall_risk_level=null` cùng highest severity riêng CONTRACT/PORTFOLIO;
- kết quả đánh giá của toàn bộ rule đang hoạt động;
- `triggered_rule_ids` cùng danh sách triggered riêng theo scope;
- các alert đã ghép và mask;
- `required_actions`;
- `insufficient_evidence`;
- `human_approval_required`;
- `decision_made_by_risk_agent=false`.

`decision_made_by_risk_agent` luôn là `false`. Risk Agent chỉ báo cáo rủi ro;
quyết định cuối cùng thuộc Decision Agent hoặc quy trình phê duyệt của con
người.

## Ví dụ gọi implementation

```python
from datetime import UTC, datetime

from app.schema.handoff_packs import FinanceFeaturePack
from app.tools.RiskAgent.BuildRiskReport import build_risk_pack_impl

finance_pack = FinanceFeaturePack(
    case_id="CASE-001",
    contract_id="CON-001",
    company_id="OPC-001",
    generated_at=datetime.now(UTC),
    transaction_risk_score=82,
    projected_closing_cash=400_000_000,
    cash_reserve_minimum=550_000_000,
    gross_margin=0.18,
    document_sent_to_partner=False,
    requested_amount=300_000_000,
    confidence_score=0.86,
    delivery_delay_days=3,
    source_record_ids=["CON-001", "TXN-001"],
)

risk_pack = build_risk_pack_impl(finance_pack)
print(risk_pack.model_dump_json(indent=2))
```

Ví dụ trên yêu cầu kết nối PostgreSQL hợp lệ vì implementation sẽ đọc
`risk_rule` và `alert` trong quá trình xử lý. Việc ghi chỉ xảy ra khi gọi riêng
`save_risk_pack` với một `session_id` hợp lệ.
