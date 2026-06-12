# CityFlow Assets & Data Processing Pipeline

Kho lưu trữ này lưu trữ các asset bản đồ thô, đồ thị di chuyển đường bộ (routing graph) và tệp mô tả `assets_manifest.json` của game **CityFlow / City Bus Connect**. Đồng thời, đây cũng là nơi quản lý toàn bộ quy trình tiền xử lý dữ liệu địa lý cho các thành phố.

---

## 🛠 Quy trình Tiền xử lý & Xuất bản Dữ liệu (Workflow)

```mermaid
graph TD
    A[1. Tải dữ liệu OSM thô<br>download_stops.py] -->|raw_hcmc_bus_stops.json| B[2. Nén & làm sạch trạm<br>compress_stops.py]
    B -->|hcmc/hcmc_bus_stops.json| C[3. Tính toán trước đường đi OSRM<br>generate_routes.py]
    B -->|hcmc/hcmc_bus_stops.json| D[4. Biên dịch JSON sang Hive<br>compile_assets_to_hive.py]
    C -->|hcmc/hcmc_routes_graph.json| D
    D -->|hcmc/hcmc_bus_stops.hive| E[5. Đưa ra thư mục gốc để Publish]
    E --> F[6. Xuất bản Release lên GitHub<br>publish.py]
```

### Bước 1: Tải dữ liệu thô tự động (Download Raw OSM Data)
Chạy script để tự động tải danh sách trạm xe buýt từ Overpass API về thư mục của thành phố tương ứng:
```bash
python download_stops.py --city hcmc
```
- **Xử lý lỗi HTTP 429 (Rate Limit)**: Script tự động truy cập trang trạng thái `/status` để xem khi nào có slot trống để đợi, tự động xoay tua truy vấn (rotate) qua 3 máy chủ Overpass API gương công cộng khác nhau, và áp dụng Exponential Backoff để thử lại an toàn.
- **Tùy biến**: Bạn có thể tùy biến địa danh OSM bằng tham số `--area-name` (Ví dụ: `python download_stops.py --city hcmc --area-name "Tỉnh Bình Dương"`).
*Đầu ra:* file thô lưu tại `<city>/raw_<city>_bus_stops.json`.

### Bước 2: Nén và làm sạch danh sách trạm (Clean & Compress)
Chạy script để lọc bỏ các tag không cần thiết và giảm kích thước file:
```bash
python compress_stops.py --city hcmc
```
*Đầu ra:* file sạch `<city>/<city>_bus_stops.json`.

### Bước 3: Tính toán trước các tuyến đường xe chạy (Precalculate Routing Graph)
Script này sẽ truy vấn OSRM (động cơ tìm đường lái xe) để dựng đường đi snapping theo bản đồ đường bộ giữa tất cả cặp trạm có cự ly chim bay $\le$ 4km (tương đương $\le$ 6.6km đường bộ).
```bash
python generate_routes.py --city hcmc
```
- **Tối ưu**: Script hỗ trợ cơ chế tải song song (16 luồng) và tự động khôi phục tiến trình cũ (resume cache) nếu bị gián đoạn.
- **OSRM Server**: Script tự động ưu tiên truy vấn OSRM cục bộ chạy ở `http://localhost:5000` (rất nhanh, khuyên dùng) trước khi fallback sang public API.

### Bước 4: Biên dịch JSON sang cơ sở dữ liệu nhị phân Hive (Compile to Hive)
Để game chạy mượt 60 FPS, chúng ta đóng gói các file JSON cồng kềnh sang định dạng nhị phân Hive `.hive`:
```bash
python compile_assets_to_hive.py hcmc
```
*(Quy trình chạy hoàn toàn bằng Python 3, không cần cài đặt thêm Dart SDK)*
*Đầu ra:* `<city>/<city>_bus_stops.hive` và `<city>/<city>_routes_graph.hive`.

### Bước 5: Xuất bản lên GitHub (Publish Release)
Chạy script tự động hóa để cập nhật manifest và đẩy asset lên release của GitHub:
```bash
./publish.py
```
*Quy trình tự động của `publish.py`:*
1. Tự động quét các file tài nguyên `{city_id}_map.pmtiles`, `{city_id}_routes_graph.hive`, và `{city_id}_bus_stops.hive` trực tiếp từ các thư mục thành phố tương ứng (ví dụ: `hcmc/`).
2. Tính toán mã băm SHA256 và kích thước file.
3. Nếu file có sự thay đổi, tự động tăng phiên bản (ví dụ `1.0.0` $\rightarrow$ `1.0.1`) trong `assets_manifest.json` và cập nhật đường dẫn tải về.
4. Nếu file không thay đổi, giữ nguyên URL của Release trước đó và phiên bản cũ (tiết kiệm thời gian và băng thông).
5. Tạo GitHub Release với thẻ tag (ví dụ `v1.0.2`), tự động đẩy các file có thay đổi lên thông qua GitHub CLI (`gh`).
6. Commit và push `assets_manifest.json` đã cập nhật lên nhánh `main`.

---

## 📋 Yêu cầu hệ thống (Prerequisites)

- **Python 3**: các thư viện đi kèm sẵn (`urllib`, `json`, `concurrent.futures`, `argparse`, `zlib`, `struct`).
- **GitHub CLI (`gh`)**: cài đặt trên thiết bị và đã đăng nhập bằng lệnh `gh auth login` để có quyền đẩy release lên GitHub.
