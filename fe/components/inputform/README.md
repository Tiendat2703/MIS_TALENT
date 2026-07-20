# Contract input mapping

Tài liệu này mô tả mapping giữa nội dung hiển thị bằng tiếng Việt trên FE và
payload tiếng Anh gửi tới `POST /runs` của BE.

## Quy tắc chung

- FE có thể hiển thị label, hướng dẫn và thông báo lỗi bằng tiếng Việt.
- Tên key trong payload phải giữ nguyên bằng tiếng Anh theo bảng bên dưới.
- Không dịch các giá trị enum như `PERFORMANCE_BOND` hoặc
  `RECEIVABLE_FINANCING` trước khi gửi tới BE.
- Hợp đồng mới luôn có `status: "Pending approval"`. Trường này không hiển thị
  trong form và BE tiếp tục cưỡng chế lại giá trị này.

## Mapping trường dữ liệu

| Nội dung trên FE | Payload key | Kiểu dữ liệu BE | Ví dụ payload | Ghi chú |
| --- | --- | --- | --- | --- |
| Mã hợp đồng | `contract_id` | `string` | `"CON-UPLOAD-001"` | Bắt buộc, không được rỗng |
| Mã khách hàng | `customer_id` | `string` | `"CUS-005"` | Bắt buộc, không được rỗng |
| Ngày bắt đầu | `start_date` | `date` dạng `YYYY-MM-DD` | `"2026-08-01"` | Bắt buộc |
| Ngày kết thúc | `end_date` | `date` dạng `YYYY-MM-DD` | `"2027-02-28"` | Không được trước ngày bắt đầu |
| Trạng thái | `status` | `"Pending approval"` | `"Pending approval"` | Không hiển thị/không cho người dùng sửa |
| Mô tả hợp đồng | `description` | `string` | `"Triển khai hệ thống..."` | Nội dung có thể viết bằng tiếng Việt |
| Giá trị hợp đồng | `contract_value` | `number > 0` | `1200000000` | Đơn vị VND, không gửi chuỗi đã định dạng |
| Biên lợi nhuận gộp | `gross_margin` | `number` từ `0` đến `1` | `0.25` | FE hiển thị `25%`, payload gửi `0.25` |
| Điều khoản thanh toán | `payment_terms` | `string` | `"30% advance..."` | Bắt buộc, không được rỗng |
| Số tiền đề nghị | `requested_amount` | `number > 0` | `300000000` | Đơn vị VND, không vượt giá trị hợp đồng |
| Loại nhu cầu vốn | `funding_need_type` | `enum` | `"PERFORMANCE_BOND"` | Xem bảng enum bên dưới |
| Thời hạn tài trợ | `tenor` | `string` | `"7 months"` | Hiện BE nhận chuỗi |

## Mapping loại nhu cầu vốn

| Nội dung trên FE | Giá trị gửi tới BE |
| --- | --- |
| Bảo lãnh thực hiện | `PERFORMANCE_BOND` |
| Tài trợ thương mại | `TRADE_FINANCE` |
| Vốn lưu động | `WORKING_CAPITAL` |
| Tài trợ khoản phải thu | `RECEIVABLE_FINANCING` |

## Chuyển đổi dữ liệu trước khi gửi

| Dữ liệu người dùng nhập | Payload gửi tới BE |
| --- | --- |
| `1.200.000.000 ₫` | `1200000000` |
| `25%` | `0.25` |
| `01/08/2026` trên giao diện ngày | `"2026-08-01"` |
| Không có trường trạng thái trên form | `"status": "Pending approval"` |

Form thực hiện mapping tập trung trong hàm `buildContractPayload()` tại
[`form.tsx`](./form.tsx). Dữ liệu mẫu nằm tại
[`contract-payload.json`](./contract-payload.json).

Để kiểm tra kết nối mà không chạy pipeline, FE gửi payload tới
`POST /contracts/validate`. Endpoint này chỉ validate và trả lại JSON đã nhận;
không ghi database và không khởi chạy agent.

## Payload hoàn chỉnh

```json
{
  "contract_id": "CON-UPLOAD-001",
  "customer_id": "CUS-005",
  "start_date": "2026-08-01",
  "end_date": "2027-02-28",
  "status": "Pending approval",
  "description": "Triển khai hệ thống quản lý chuỗi cung ứng cho 12 kho nông sản",
  "contract_value": 1200000000,
  "gross_margin": 0.25,
  "payment_terms": "Performance bond required; 30% advance, 50% delivery, 20% acceptance",
  "requested_amount": 300000000,
  "funding_need_type": "PERFORMANCE_BOND",
  "tenor": "7 months"
}
```

Schema xác thực cuối cùng của BE là `ContractUploadPackage` tại
`app/schema/pipeline_input.py`. File JSON của FE chỉ chứa dữ liệu mẫu; schema BE
vẫn là nguồn kiểm tra dữ liệu đáng tin cậy trước khi Finance Agent chạy.
