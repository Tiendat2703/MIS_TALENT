# Contract input mapping

Tài liệu này mô tả mapping giữa nội dung hiển thị bằng tiếng Việt trên FE và
payload tiếng Anh gửi tới `POST /runs` của BE.

## Quy tắc chung

- FE có thể hiển thị label, hướng dẫn và thông báo lỗi bằng tiếng Việt.
- Tên key trong payload phải giữ nguyên bằng tiếng Anh theo bảng bên dưới.
- FE không yêu cầu người dùng chọn loại nhu cầu vốn. Decision suy ra loại hình từ
  `payment_terms`, sau khi Finance đã cung cấp `requested_amount`.
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
| Số tiền đề nghị | `requested_amount` | `number > 0 \| null` | `null` | Không bắt buộc; null để Finance tính từ dòng tiền riêng của hợp đồng |
| Loại nhu cầu vốn | `funding_need_type` | `null` ở submission mới | `null` | Decision xác định từ `payment_terms` và sản phẩm ngân hàng phù hợp |
| Thời hạn tài trợ | `tenor` | `string \| null` | `null` | Không bắt buộc; Finance dùng khoảng ngày hợp đồng khi để trống |

## Phân công xử lý

- Finance giữ nguyên số tiền người dùng nhập. Nếu số tiền là null, Finance lấy đáy
  âm lớn nhất của dòng tiền tích lũy riêng của hợp đồng làm `requested_amount`.
- Decision đọc `payment_terms` và số tiền Finance trả ra, tìm sản phẩm ngân hàng
  đáp ứng ngưỡng số tiền/collateral, rồi mới đặt `funding_need_type`.
- Chỉ sau khi chọn được sản phẩm, hệ thống mới tạo yêu cầu approval cho bank
  pre-check tương ứng.

## Chuyển đổi dữ liệu trước khi gửi

| Dữ liệu người dùng nhập | Payload gửi tới BE |
| --- | --- |
| `1.200.000.000 ₫` | `1200000000` |
| `25%` | `0.25` |
| `01/08/2026` trên giao diện ngày | `"2026-08-01"` |
| Để trống số tiền/thời hạn | `null` |
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
  "requested_amount": null,
  "funding_need_type": null,
  "tenor": null
}
```

Schema xác thực cuối cùng của BE là `ContractUploadPackage` tại
`app/schema/pipeline_input.py`. File JSON của FE chỉ chứa dữ liệu mẫu; schema BE
vẫn là nguồn kiểm tra dữ liệu đáng tin cậy trước khi Finance Agent chạy.
