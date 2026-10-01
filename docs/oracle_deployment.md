# Triển khai trên Oracle Cloud Infrastructure

Ứng dụng Flask và ViSoBERT chạy trên Oracle Compute VM bằng Docker Compose, Python 3.13.5 và PyTorch CPU. Không sử dụng Render hoặc GitHub Pages để phục vụ backend Python. Cấu hình không đặt trần RAM cho container; tổng bộ nhớ vẫn bị giới hạn bởi VM.

## 1. Tạo tài khoản và VM

1. Đăng ký Oracle Cloud, chọn home region và tạo compartment cho dự án.
2. Tạo Compute instance dùng Ubuntu 24.04 LTS, shape `VM.Standard.A1.Flex` (ARM64), cấu hình khởi đầu 2 OCPU/12 GB RAM và boot volume 50 GB. Không chọn E2.1.Micro 1 GB cho mô hình cục bộ.
3. Kiểm tra nhãn Always Free và dự toán chi phí ngay trong Console trước khi tạo. [Tài liệu Oracle hiện tại](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) ghi tổng hạn mức A1 2 OCPU/12 GB; không mặc định 4 OCPU/24 GB miễn phí. Nếu hết capacity, thử availability domain khác trong home region hoặc chờ cấp lại tài nguyên.
4. Tạo public subnet có route tới Internet Gateway, gán public IPv4 và lưu private key SSH trên máy cá nhân. Cho phép TCP 22 từ IP của bạn trong NSG/security list; bước thử nghiệm không cần mở 8000 ra Internet.

## 2. Cài môi trường trên VM

Từ PowerShell trên máy cá nhân:

```powershell
ssh -i C:\duong-dan\oracle.key ubuntu@IP_CUA_VM
```

Trên Ubuntu, cài Git và Docker Engine cùng Compose plugin theo [hướng dẫn chính thức cho Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Xác minh:

```bash
sudo apt-get update
sudo apt-get install -y git
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
git clone --branch develop https://github.com/DungPhanHoangg05/A-Multi-Agent-Large-Language-Model-Approach-to-Price-Driven-Stock-Trading-in-the-Vietnamese-Stock-Ma.git quantagent-vn
cd quantagent-vn
cp deploy/oracle/.env.example .env
chmod 600 .env
nano .env
```

Điền `GROQ_API_KEY`; `HF_TOKEN` là tùy chọn. Nhánh remote được clone phải đã chứa các file triển khai mới; nếu thay đổi chỉ tồn tại trên máy cá nhân, cần đẩy commit đã kiểm thử trước khi clone. Không sao chép private key SSH hoặc `.env` vào image.

```bash
sudo docker compose build
sudo docker compose run --rm --no-deps web python -c "import torch, talib, vnstock; print('Các thư viện đã nạp thành công')"
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=100 web
curl --fail http://127.0.0.1:8000/
```

Image dùng kiến trúc của VM; bước cài gói và smoke test trên chính A1 xác minh khả năng tương thích ARM64. Lần phân tích sentiment đầu tiên tải ViSoBERT, cần Internet và có thể lâu hơn các lần sau. Healthcheck chỉ xác minh HTTP, chưa xác minh Groq, dữ liệu thị trường hoặc mô hình sentiment.

## 3. Truy cập khi chưa có tên miền

Mở terminal PowerShell riêng trên máy cá nhân:

```powershell
ssh -i C:\duong-dan\oracle.key -N -L 8000:127.0.0.1:8000 ubuntu@IP_CUA_VM
```

Giữ phiên SSH hoạt động rồi mở `http://127.0.0.1:8000` trong trình duyệt. Cổng ứng dụng chỉ bind loopback của VM.

## 4. Công bố HTTPS khi đã có tên miền

Trỏ DNS A của tên miền tới public IPv4 của VM. Mở TCP 80/443 trong OCI NSG/security list và firewall hệ điều hành đang sử dụng; giữ nguyên SSH, không xóa hoặc flush bộ luật firewall OCI. Không mở TCP 8000.

Tạo hash mật khẩu bằng lệnh tương tác, không truyền mật khẩu trong dòng lệnh:

```bash
sudo docker run --rm -it caddy:2-alpine caddy hash-password
nano .env
```

Điền `APP_DOMAIN` (ví dụ `stocks.example.com`, không kèm `https://`), `APP_USERNAME` và `APP_PASSWORD_HASH`. Bao hash trong dấu nháy đơn để Compose giữ nguyên các ký tự `$`. Reverse proxy yêu cầu mật khẩu vì các API hiện tại cho phép đổi cấu hình và API key. Caddy tự cấp chứng chỉ khi DNS và cổng 80/443 hoạt động.

```bash
sudo docker compose -f compose.yaml -f deploy/oracle/compose.public.yaml up -d --build
sudo docker compose -f compose.yaml -f deploy/oracle/compose.public.yaml logs --tail=100 proxy
```

Truy cập `https://TEN_MIEN_CUA_BAN` và đăng nhập bằng thông tin vừa đặt.

## 5. Bộ nhớ, dữ liệu và cập nhật

- Gunicorn bắt buộc giữ một worker: trạng thái phân tích/backtest nằm trong bộ nhớ tiến trình. Nhiều worker khiến truy vấn trạng thái không tìm thấy tác vụ và tạo thêm bản sao mô hình. Không bật preload, tự recycle worker hoặc nhiều replica khi tác vụ đang chạy.
- Cache Hugging Face, kết quả backtest và `outputs/` dùng named volumes, tồn tại khi thay container. Không chạy `docker compose down -v` nếu cần giữ dữ liệu. Cache `sentiment_cache_*.json` tại gốc ứng dụng chưa được gắn volume: sao lưu ra VM bằng `docker compose cp web:/app/sentiment_cache_FPT.json ./sentiment_cache_FPT.json` và khôi phục theo chiều ngược lại nếu cần giữ cache qua lần thay container; thực hiện cho từng mã đã sử dụng.
- Tác vụ web đang chạy và trạng thái polling không tồn tại qua lần restart. Chờ tác vụ hoàn tất trước khi cập nhật; runner nghiên cứu dùng checkpoint trong `outputs/` có thể phục hồi theo cơ chế hiện có.
- Kiểm tra `free -h`, `sudo docker stats --no-stream` và `sudo docker inspect --format '{{.State.OOMKilled}}' "$(sudo docker compose ps -q web)"`. Nếu VM vẫn thiếu RAM, giảm số tác vụ đồng thời hoặc tăng RAM trong hạn mức tài khoản. Không có bảo đảm hết OOM chỉ bằng đổi nhà cung cấp.
- Oracle có thể thu hồi VM Always Free ít sử dụng theo chính sách của họ; giữ bản sao kết quả ngoài VM.

Cập nhật khi các tác vụ đã hoàn tất:

```bash
git pull --ff-only origin develop
sudo docker compose up -d --build
```

Nếu đang dùng HTTPS, thay lệnh cuối bằng lệnh Compose có hai file ở mục 4. Bản triển khai chỉ được xem là xác minh hoàn chỉnh sau khi build trên VM, HTTP/HTTPS hoạt động và một lượt phân tích/backtest thực tế chạy thành công.
