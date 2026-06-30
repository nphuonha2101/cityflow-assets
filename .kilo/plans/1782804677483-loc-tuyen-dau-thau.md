# Plan: Lọc danh sách 105 tuyến đầu thầu HCMC

## Mục tiêu
Từ dữ liệu tuyến xe buýt HCMC trên OpenStreetMap (Overpass API), lọc ra và hiển thị danh sách các tuyến đầu thầu theo 105 mã số tuyến người dùng cung cấp.

## Các bước thực hiện

### Bước 1: Chạy `download_bid_routes.py` với `--max-routes` đủ lớn
- Lệnh: `python download_bid_routes.py --city hcmc --max-routes 200`
- Mục đích: Tải tất cả bus route relations trong bounding box HCMC từ Overpass API, xử lý thành bid route templates, lưu vào `hcmc/hcmc_bid_routes.json`
- Lý do `--max-routes 200`: Đảm bảo đủ số lượng route (105+) để filter, vì mặc định chỉ 50
- Rủi ro: Overpass API có thể rate-limit (script đã xử lý auto-retry + backoff)

### Bước 2: Viết script filter `filter_winning_routes.py`
- Input: `hcmc/hcmc_bid_routes.json`
- Logic:
  - Đọc danh sách 105 route codes từ biến hardcode (các số người dùng cung cấp)
  - Duyệt từng route template, kiểm tra nếu `routeNumber` (so sánh dạng string) nằm trong danh sách
  - In ra terminal danh sách các route template đã lọc (JSON hoặc dạng bảng)
- Output: hiển thị trên terminal số lượng + danh sách các tuyến tìm được

### Bước 3: Kiểm tra kết quả
- Xác nhận số lượng tuyến tìm được so với 105 (có thể thiếu nếu Overpass không có dữ liệu cho một số route)
- Thông báo các route code không tìm thấy trong dữ liệu (nếu có)

## Rủi ro & Phương án dự phòng
| Rủi ro | Phương án |
|--------|-----------|
| Overpass API không trả về đủ route | Thử lại sau, hoặc kiểm tra OSM trực tiếp |
| Một số route code không tồn tại trong OSM (`ref` tag thiếu) | Báo cáo danh sách route code không tìm thấy |
| Script mất > 2 phút do Overpass chậm | Timeout 120s đã được cấu hình trong script |

## File sinh ra
- `hcmc/hcmc_bid_routes.json` (toàn bộ bid routes, ~200 routes)
- `hcmc/filtered_bid_routes.json` (tùy chọn, nếu muốn save kết quả filter)
