# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Đọc `01-localhost-vs-production/develop/app.py` và đối chiếu với bản đã khắc phục ở `01-localhost-vs-production/production/`:

1. **Hardcode secrets trực tiếp trong mã nguồn (`develop/app.py` dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` nằm cứng trong file code. Nếu push lên GitHub public, bot quét secret sẽ thu thập được ngay lập tức và chiếm quyền truy cập DB / làm phát sinh chi phí API.
   - **Cách sửa ở bản `production`:** `production/config.py` (dòng 27, 32) đọc toàn bộ khóa nhạy cảm qua `os.getenv("OPENAI_API_KEY", "")` và `os.getenv("AGENT_API_KEY", "")`, kèm hàm `validate()` (dòng 37–46) bắt buộc phải có `AGENT_API_KEY` khi `ENVIRONMENT == "production"`.

2. **Hardcode cấu hình và bật cứng chế độ debug (`develop/app.py` dòng 21–22):**
   - `DEBUG = True`, `MAX_TOKENS = 500` được gán cố định, không có lớp quản lý cấu hình tập trung nên muốn thay đổi tham số giữa `dev` / `staging` / `production` phải sửa trực tiếp mã nguồn.
   - **Cách sửa ở bản `production`:** `production/config.py` (dòng 15–35) gom toàn bộ cấu hình vào `@dataclass class Settings` đọc từ biến môi trường theo nguyên lý 12-Factor App (`DEBUG` mặc định là `false`).

3. **Dùng `print()` thay cho structured logging và in lộ cả secret ra log (`develop/app.py` dòng 33–38):**
   - Dòng 34 `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ trực tiếp API key ra stdout/log hệ thống; ngoài ra log dạng chuỗi tự do thiếu timestamp, mức độ nghiêm trọng (`level`) và rất khó parse/truy vấn trên các hệ thống tập trung (Loki, Datadog, Cloud Logging).
   - **Cách sửa ở bản `production`:** `production/app.py` (dòng 28–32, 111–122) dùng module `logging` xuất chuỗi JSON có cấu trúc (`event`, `question_length`, `client_ip`, `response_length`) và tuyệt đối không ghi secret vào log.

4. **Thiếu Health Check và Readiness Probe (`develop/app.py` dòng 42–43):**
   - Không có endpoint kiểm tra tình trạng sống/sẵn sàng nên Docker/Kubernetes/Railway/Render không biết khi nào process bị treo để tự restart, cũng không biết lúc nào app mới khởi động xong để bắt đầu điều phối traffic vào.
   - **Cách sửa ở bản `production`:** `production/app.py` bổ sung `GET /health` (liveness probe, dòng 135–149) và `GET /ready` (readiness probe trả `503` khi `is_ready == False`, dòng 152–161).

5. **Cấu hình mạng và chạy server kiểu cục bộ (`develop/app.py` dòng 50–53):**
   - `host="localhost"` chỉ lắng nghe loopback bên trong máy/container nên khi đóng gói Docker sẽ không nhận được kết nối từ bên ngoài; `port=8000` gắn cứng thay vì đọc biến môi trường `PORT` do nền tảng cloud cấp; `reload=True` theo dõi file liên tục gây tốn tài nguyên và mất ổn định trên production.
   - **Cách sửa ở bản `production`:** `production/app.py` (dòng 194–199) kết hợp `config.py` (dòng 17–19) bind `host="0.0.0.0"`, lấy `port` từ biến `PORT`, và chỉ bật `reload` khi `DEBUG=true`.

6. **Không xử lý Graceful Shutdown và quản lý vòng đời ứng dụng:**
   - Bản `develop` tắt đột ngột khi nhận tín hiệu dừng container (`SIGTERM`), làm đứt ngang các request đang xử lý dở.
   - **Cách sửa ở bản `production`:** `production/app.py` sử dụng `lifespan` context manager (dòng 39–67) để cập nhật cờ `is_ready` khi khởi động/đóng ứng dụng và đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189) để hoàn tất các request đang chạy trước khi thoát.

7. **Thiếu kiểm soát CORS và xác thực dữ liệu đầu vào chuẩn JSON (`develop/app.py` dòng 30–31):**
   - Endpoint `POST /ask` nhận `question: str` qua query string thay vì JSON body chuẩn và không cấu hình `CORSMiddleware`.
   - **Cách sửa ở bản `production`:** `production/app.py` cấu hình `CORSMiddleware` giới hạn theo `ALLOWED_ORIGINS` (dòng 77–82) và nhận JSON body có kiểm tra trường `question` (dòng 102–108).

---

### Exercise 1.2: Running develop version

Chạy bản `01-localhost-vs-production/develop/app.py` trên cổng `8000` và kiểm thử bằng `curl -i`:

- **Gọi đúng qua query string (`POST /ask?question=Hello`):**

```http
$ curl -i -X POST "http://localhost:8000/ask?question=Hello"
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:22:11 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

- **Nếu gửi JSON body (không có query param `question`) sẽ bị trả `422`:**

```http
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 422 Unprocessable Content
date: Wed, 25 Nov 2026 10:22:11 GMT
server: uvicorn
content-length: 94
content-type: application/json

{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}
```

- **Quan sát trên log terminal của `develop`:** Server chạy được nhưng in thẳng API key ra console (`[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this`), chứng tỏ bản này chưa sẵn sàng cho môi trường production.

---

### Exercise 1.3: Comparison table

Kiểm thử bản `01-localhost-vs-production/production/app.py` sau khi tạo `.env` từ `.env.example`:

```http
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:22:12 GMT
server: uvicorn
content-length: 129
content-type: application/json

{"status":"ok","uptime_seconds":0.9,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T10:22:13.674190+00:00"}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:22:12 GMT
server: uvicorn
content-length: 14
content-type: application/json

{"ready":true}

$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:22:12 GMT
server: uvicorn
content-length: 136
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}
```

Bảng đối chiếu giữa bản `Develop` (Basic) và `Production` (Advanced):

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| **Config & Secrets** | Hardcode trực tiếp trong `app.py` (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`) | Đọc tập trung từ biến môi trường qua `config.py` (`os.getenv`) kèm hàm `validate()` fail-fast | Ngăn lộ khóa bí mật trong lịch sử Git; cho phép dùng cùng một bản build cho nhiều môi trường (dev/staging/prod) mà không phải sửa code (12-Factor Config). |
| **Health Check** | Không có (`/health`, `/ready` đều không tồn tại) | Có `GET /health` (liveness) và `GET /ready` (readiness trả `503` khi chưa sẵn sàng) | Nền tảng vận hành biết khi nào process bị treo để tự khởi động lại (`/health`) và Load Balancer chỉ điều hướng người dùng vào instance đã nạp xong tài nguyên (`/ready`). |
| **Logging** | Dùng `print()` tự do, thậm chí in cả `OPENAI_API_KEY` ra màn hình | Dùng module `logging` xuất chuỗi JSON có cấu trúc, ẩn thông tin nhạy cảm | Log JSON dễ thu thập, đánh chỉ mục, lọc và cảnh báo tự động trên hệ thống giám sát tập trung mà không làm rò rỉ dữ liệu mật. |
| **Shutdown** | Tắt đột ngột ngay khi dừng tiến trình | Quản lý vòng đời qua `lifespan` + bắt tín hiệu `SIGTERM` (Graceful shutdown) | Đảm bảo khi deploy bản mới hoặc scale down, container ngừng nhận request mới nhưng vẫn xử lý trọn vẹn các request đang dở, tránh gây lỗi `502`/`504` cho người dùng. |
| **Host, Port & Reload** | `host="localhost"`, `port=8000` cố định, `reload=True` luôn bật | `host="0.0.0.0"`, `port` đọc từ biến `PORT`, `reload` chỉ bật khi `DEBUG=true` | Cho phép container nhận kết nối từ bên ngoài mạng nội bộ Docker/Cloud, tương thích với cổng động do Railway/Render cấp và giữ hiệu năng ổn định. |
| **CORS & Input Validation** | Không cấu hình CORS; nhận tham số qua query string | Có `CORSMiddleware` theo `ALLOWED_ORIGINS`; nhận JSON body và trả `422` rõ ràng khi thiếu dữ liệu | Kiểm soát chặt domain frontend nào được phép gọi API từ trình duyệt và chuẩn hóa giao tiếp REST API. |

---

## AI Log

### Mục 1 — Phân tích đề bài và thực hiện CP1 (Part 1: Localhost vs Production)
- **Hỏi AI:** Phân tích cấu trúc bài lab Day 14, hướng dẫn và hỗ trợ thực hiện CP1 (chạy kiểm thử bản `develop` và `production` trong `01-localhost-vs-production/`, tổng hợp câu trả lời vào `MISSION_ANSWERS.md`) cũng như cách đặt commit message chuẩn.
- **Nhận từ AI:** Giải thích tổng quan 7 phần của bài lab, các lưu ý riêng cho lớp K5, danh sách các anti-patterns trong `develop/app.py` đối chiếu với `production/app.py` & `production/config.py`, kịch bản kiểm thử các endpoint bằng `curl -i` và bảng so sánh chi tiết.
- **Tự sửa và tự kiểm tra:** Đã chạy thực tế cả hai server `develop/app.py` và `production/app.py` trên cổng `8000`, kiểm chứng trực tiếp mã trả về (`200 OK` khi truyền `?question=Hello`, `422` khi truyền JSON vào bản `develop`; `200 OK` trên `/health`, `/ready`, `/ask` ở bản `production`), đối chiếu từng số dòng code trong repo và kiểm tra `git status` đảm bảo không theo dõi file `.env`.
