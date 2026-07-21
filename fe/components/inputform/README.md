# Contract input mapping

Form gửi một `ContractUploadPackage` tới `POST /finance/preflight`.

## Trường hiển thị

| Nội dung | Payload key | Quy tắc |
| --- | --- | --- |
| Mã hợp đồng | `contract_id` | Read-only; FE lấy preview từ `GET /contracts/next-id`, BE cấp lại ID chính thức khi lưu |
| Mã khách hàng | `customer_id` | Bắt buộc và phải tồn tại trong dữ liệu demo |
| Ngày bắt đầu/kết thúc | `start_date`, `end_date` | Bắt buộc, định dạng `YYYY-MM-DD`; ngày kết thúc không được trước ngày bắt đầu |
| Mô tả hợp đồng | `description` | Bắt buộc; Finance Agent dùng để mapping dịch vụ nếu gross margin trống |
| Giá trị hợp đồng | `contract_value` | Bắt buộc, số VND lớn hơn 0 |
| Biên lợi nhuận gộp | `gross_margin` | FE hiển thị phần trăm, payload gửi số `0..1`; có thể để trống để nhận recommendation |
| Điều khoản thanh toán | `payment_terms` | Bắt buộc; chọn một trong bốn giá trị được schema cho phép |

`requested_amount`, `funding_need_type` và `tenor` không hiển thị trên form và
luôn được gửi là `null`. FE không gửi `status`; BE tự đặt trạng thái thành
`Pending approval`.

Form luôn hiển thị ngay cả khi `GET /contracts/next-id` thất bại. Mã dự kiến được
tải nền; khi chưa lấy được mã, FE gửi `contract_id: null` và BE vẫn cấp mã chính
thức khi lưu.

Nếu gross margin trống và description khớp catalog, preflight trả
`AWAITING_CONFIRMATION`. Nút “Áp dụng đề xuất” chỉ điền giá trị vào form; người
dùng phải submit lại. Chỉ lần submit có gross margin mới lưu contract và chạy
pipeline.

## Payment terms

- `Monthly payment`
- `Milestone payment`
- `Performance bond required`
- `Possible LC/trade finance`

## Payload mẫu

```json
{
  "contract_id": "CON-006",
  "customer_id": "CUS-005",
  "start_date": "2026-08-01",
  "end_date": "2027-02-28",
  "description": "Triển khai hệ thống bán hàng số cho doanh nghiệp",
  "contract_value": 1200000000,
  "gross_margin": null,
  "payment_terms": "Milestone payment",
  "requested_amount": null,
  "funding_need_type": null,
  "tenor": null
}
```
