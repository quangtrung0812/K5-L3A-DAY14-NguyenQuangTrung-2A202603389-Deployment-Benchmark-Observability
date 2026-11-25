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

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

Đọc `02-docker/develop/Dockerfile`:

1. **Base image là gì?**
   - `python:3.11` — image Python đầy đủ dựa trên Debian (bao gồm cả trình biên dịch C/C++, công cụ build và nhiều gói hệ thống mặc định nên kích thước rất lớn).
2. **Working directory là gì?**
   - `/app` (được đặt bởi `WORKDIR /app`). Mọi chỉ thị `COPY`, `RUN`, `CMD` phía sau đều chạy tương đối trong thư mục `/app` của container.
3. **Tại sao `COPY requirements.txt` trước khi copy mã nguồn (`app.py`, `utils/`)?**
   - Để tận dụng cơ chế **Docker Layer Cache**. Docker lưu cache theo từng layer tuần tự từ trên xuống và sẽ vô hiệu hóa (invalidate) mọi layer phía sau ngay khi một layer thay đổi. Vì mã nguồn (`app.py`) được chỉnh sửa rất thường xuyên trong khi `requirements.txt` hiếm khi thay đổi, việc tách `COPY .../requirements.txt .` và `RUN pip install --no-cache-dir -r requirements.txt` lên trước giúp Docker tái sử dụng nguyên vẹn layer cài đặt thư viện (`CACHED`) mỗi khi chỉ sửa code, rút ngắn thời gian build từ hàng chục giây xuống dưới 1 giây.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - **`CMD`:** Khai báo lệnh (hoặc bộ tham số) **mặc định** khi container khởi chạy; toàn bộ `CMD` sẽ **bị ghi đè** nếu người dùng truyền lệnh khác ở cuối `docker run <image> <command>` (ví dụ `docker run -it my-agent:develop sh`).
   - **`ENTRYPOINT`:** Cố định chương trình thực thi chính của container (biến container hoạt động như một file binary độc lập); mọi tham số truyền thêm ở cuối `docker run <image> <args>` sẽ được **nối vào sau `ENTRYPOINT`** thay vì thay thế nó (trừ khi ghi đè tường minh bằng cờ `--entrypoint`).

---

### Exercise 2.2: Build và run container cơ bản (`my-agent:develop`)

Build image từ thư mục gốc của repo và chạy thử container trên cổng `8000`:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name cp2-dev -p 8000:8000 my-agent:develop
```

Kết quả kiểm thử thực tế (lưu ý bản `develop` nhận `question` qua query string):

```http
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:45:14 GMT
server: uvicorn
content-length: 53
content-type: application/json

{"status":"ok","uptime_seconds":0.8,"container":true}

$ curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 10:45:14 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build & Image size comparison

Phân tích `02-docker/production/Dockerfile`:

- **Stage 1 (`builder` — `FROM python:3.11-slim AS builder`):** Cài đặt các công cụ biên dịch hệ thống (`gcc`, `libpq-dev`) qua `apt-get` và cài toàn bộ Python dependencies vào thư mục `/root/.local` (`pip install --no-cache-dir --user -r requirements.txt`). Toàn bộ stage này chỉ phục vụ việc build và **không nằm trong image cuối cùng**.
- **Stage 2 (`runtime` — `FROM python:3.11-slim AS runtime`):** Bắt đầu lại từ một image `python:3.11-slim` sạch, tạo non-root user `appuser`, chỉ copy kết quả thư viện đã cài đặt từ Stage 1 (`COPY --from=builder /root/.local /home/appuser/.local`) cùng code cần chạy (`main.py`, `utils/mock_llm.py`), khai báo `HEALTHCHECK` và khởi chạy `uvicorn` dưới quyền `appuser`.
- **Tại sao image nhỏ hơn (và an toàn hơn)?**
  1. Đổi base image từ `python:3.11` đầy đủ sang biến thể tối giản `python:3.11-slim`.
  2. Nhờ **multi-stage build**, toàn bộ trình biên dịch `gcc`, thư viện header `libpq-dev` và các tệp trung gian lúc build bị bỏ lại ở Stage 1; Stage 2 chỉ giữ lại Python runtime và các package cần thiết để chạy ứng dụng — vừa giảm mạnh dung lượng lưu trữ/băng thông kéo image, vừa thu hẹp bề mặt tấn công (attack surface) kết hợp non-root user.

Kết quả đo thực tế trên máy bằng `docker images my-agent` và `docker image inspect` (Docker Engine 29.6.2):

```text
$ docker images my-agent
IMAGE               ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:advanced   8b58b30b8400        240MB         57.4MB        
my-agent:develop    47b4316bdc68       1.67GB          426MB

$ docker image inspect my-agent:develop my-agent:advanced --format "{{.RepoTags}} size_bytes={{.Size}}"
[my-agent:develop] size_bytes=426320301
[my-agent:advanced] size_bytes=57409243
```

- **Develop (`my-agent:develop`):** `1.67 GB` (~`1670 MB` Disk Usage) / `426.3 MB` (Content Size)
- **Production (`my-agent:advanced`):** `240 MB` (Disk Usage) / `57.4 MB` (Content Size)
- **Difference (Mức giảm dung lượng):** Giảm **85.6%** theo Disk Usage (`1670 MB → 240 MB`) và giảm **86.5%** theo Content Size (`426.3 MB → 57.4 MB`).

---

### Exercise 2.4: Docker Compose stack & Architecture diagram

#### 1. Sơ đồ kiến trúc và cơ chế giao tiếp (`02-docker/production/docker-compose.yml` & `nginx/nginx.conf`)

```text
                        Host Machine
                             │
                HTTP :80 / HTTPS :443
                             ▼
┌────────────────────────────┼───────────────────────────────────┐
│  Docker Bridge Network: internal                               │
│                            ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  nginx (nginx:alpine)                                    │  │
│  │  - Reverse proxy, rate limit (10r/s, burst=20)           │  │
│  │  - Security headers (X-Frame-Options, nosniff, XSS)      │  │
│  └─────────────────────────┬────────────────────────────────┘  │
│                            │ proxy_pass http://agent:8000      │
│                            ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  agent (FastAPI — multi-stage target: runtime, :8000)    │  │
│  │  - Không expose port trực tiếp ra ngoài host             │  │
│  │  - depends_on: redis (healthy) & qdrant (healthy)        │  │
│  └───────────┬───────────────────────────────┬──────────────┘  │
│              │ REDIS_URL=                    │ QDRANT_URL=     │
│              │ redis://redis:6379/0          │ http://qdrant:6333
│              ▼                               ▼                 │
│  ┌───────────────────────┐       ┌──────────────────────────┐  │
│  │  redis (redis:7-alpine)│       │ qdrant (qdrant:v1.9.0)   │  │
│  │  Port 6379/tcp        │       │ Port 6333-6334/tcp       │  │
│  │  Volume: redis_data   │       │ Volume: qdrant_data      │  │
│  └───────────────────────┘       └──────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

- **Các services được khởi động:** 4 services gồm `nginx`, `agent`, `redis` và `qdrant` nằm chung trong mạng bridge cô lập `internal`.
- **Cách các services giao tiếp:**
  - Chỉ duy nhất **`nginx`** mở cổng `80`/`443` ra máy host làm cổng vào (entrypoint), sau đó chuyển tiếp (`proxy_pass`) lưu lượng tới `http://agent:8000` qua tên DNS nội bộ của Docker Compose.
  - **`agent`** không mở cổng trực tiếp ra ngoài host (tăng bảo mật), chỉ khởi chạy sau khi healthcheck của cả `redis` (`redis-cli ping`) và `qdrant` (kiểm tra TCP `6333`) đều báo `healthy`, rồi kết nối nội bộ qua `redis://redis:6379/0` và `http://qdrant:6333`.

#### 2. Kết quả chạy và kiểm thử thực tế qua Nginx

Tạo file `.env.local` trong `02-docker/production/`, khởi chạy stack với tên project riêng `-p k5-day14-docker` và kiểm thử qua cổng `80`:

```text
$ docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml ps
NAME                       IMAGE                   COMMAND                  SERVICE   CREATED          STATUS                           PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   "uvicorn main:app --…"   agent     13 seconds ago   Up 1 second (health: starting)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            "/docker-entrypoint.…"   nginx     13 seconds ago   Up 1 second                      0.0.0.0:80->80/tcp, [::]:80->80/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    "./entrypoint.sh"        qdrant    13 seconds ago   Up 12 seconds (healthy)          6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          "docker-entrypoint.s…"   redis     13 seconds ago   Up 12 seconds (healthy)          6379/tcp
```

```http
$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 10:46:06 GMT
Content-Type: application/json
Content-Length: 95
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.5,"version":"2.0.0","timestamp":"2026-11-25T10:46:06.284622"}

$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
Date: Wed, 25 Nov 2026 10:46:06 GMT
Content-Type: application/json
Content-Length: 95
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

*(Sau khi kiểm thử xong đã chạy `docker compose -p k5-day14-docker -f 02-docker/production/docker-compose.yml down -v` để giải phóng cổng 80/443.)*

---

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop/`)

1. **API key được kiểm tra ở đâu?**
   - Trong dependency `verify_api_key(api_key: str = Security(api_key_header))` tại `04-api-gateway/develop/app.py` (dòng 39–54), trích xuất header `X-API-Key` thông qua `APIKeyHeader(name="X-API-Key", auto_error=False)` và được gắn trực tiếp vào `POST /ask` bằng `_key: str = Depends(verify_api_key)` (dòng 70). Các route `/` và `/health` được để public cho nền tảng vận hành kiểm tra.
2. **Điều gì xảy ra nếu thiếu hoặc sai key?**
   - **Thiếu header `X-API-Key`:** Trả về **`401 Unauthorized`** (`Missing API key. Include header: X-API-Key: <your-key>`).
   - **Sai giá trị `X-API-Key`:** Trả về **`403 Forbidden`** (`Invalid API key.`). *(Lưu ý: trong hợp đồng chấm tự động của Part 6, cả hai trường hợp thiếu hoặc sai key đều quy ước trả về `401`.)*
3. **Làm sao rotate (xoay vòng) API key an toàn?**
   - Cập nhật khóa mới trên trình quản lý biến môi trường của nền tảng cloud (`AGENT_API_KEY`) thay vì sửa code, sau đó khởi động lại dịch vụ và cấp khóa mới cho client.
   - Để xoay vòng **không gián đoạn (zero-downtime)**: hỗ trợ danh sách nhiều khóa hợp lệ cùng lúc trong thời gian chuyển giao (ví dụ `AGENT_API_KEYS=new_key,old_key` hoặc lưu hash khóa kèm hạn sử dụng trong Redis/DB), đợi tất cả client chuyển sang `new_key` rồi mới xóa `old_key`.

**Kết quả kiểm thử thực tế với `AGENT_API_KEY=secret-key-123`:**

```http
# 1) Không gửi X-API-Key → 401 Unauthorized
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 14:38:34 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# 2) Gửi sai X-API-Key → 403 Forbidden
$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: wrong-key" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 14:38:34 GMT
server: uvicorn
content-length: 29
content-type: application/json

{"detail":"Invalid API key."}

# 3) Gửi đúng X-API-Key → 200 OK
$ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: secret-key-123" -H "Content-Type: application/json" -d '{"question": "Hello"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:38:34 GMT
server: uvicorn
content-length: 145
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

### Exercise 4.2: JWT authentication (`04-api-gateway/production/`)

- **Luồng xác thực JWT (Stateless Auth) trong `auth.py` & `app.py`:**
  1. Client gửi `username` / `password` đến `POST /auth/token` (`app.py` dòng 105–118).
  2. `authenticate_user()` đối chiếu thông tin đăng nhập; nếu đúng thì `create_token()` đóng gói payload gồm `sub` (tên người dùng), `role` (`user` hoặc `admin`), `iat` (thời điểm tạo) và `exp` (hết hạn sau 60 phút), rồi ký bằng `HS256` với `SECRET_KEY`.
  3. Khi gọi `POST /ask`, client gửi kèm `Authorization: Bearer <token>`. Dependency `verify_token()` xác minh chữ ký số và thời hạn ngay trên RAM mà không phải truy vấn database: thiếu header → `401 Unauthorized`, token hết hạn → `401`, chữ ký không hợp lệ → `403`.

**Kết quả kiểm thử thực tế (đã che token):**

```http
# 1) Gọi /ask không đính kèm Bearer token → 401 Unauthorized
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Explain JWT"}'
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 14:38:36 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

# 2) Đăng nhập lấy JWT với tài khoản student / demo123 → 200 OK
$ curl -i -X POST http://localhost:8000/auth/token -H "Content-Type: application/json" -d '{"username": "student", "password": "demo123"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:38:36 GMT
server: uvicorn
content-length: 307
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"access_token":"<REDACTED_TOKEN>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer <REDACTED_PREFIX>..."}
```

---

### Exercise 4.3: Rate limiting (`04-api-gateway/production/rate_limiter.py`)

1. **Thuật toán được sử dụng:** **Sliding Window (Log/Counter)** với cấu trúc `deque` lưu danh sách các mốc `timestamp` của từng request theo mỗi `user_id` trong cửa sổ trượt `60` giây; mỗi lần kiểm tra sẽ loại bỏ các timestamp cũ hơn `now - 60` ở đầu hàng đợi (`popleft()`) rồi đếm số phần tử còn lại.
2. **Giới hạn (Limit):**
   - Role `user` (`rate_limiter_user` — tài khoản `student`): **`10` requests / phút** (`window_seconds=60`).
   - Role `admin` (`rate_limiter_admin` — tài khoản `teacher`): **`100` requests / phút**.
3. **Cách nâng / bypass giới hạn cho `admin`:**
   - Dựa vào trường `role` trích xuất từ JWT payload (`app.py` dòng 141): `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user` để áp hạn mức riêng cho `admin` (`100 req/phút`), hoặc chỉ gọi `rate_limiter_user.check(username)` khi `role != "admin"` nếu muốn miễn giới hạn hoàn toàn.

**Kết quả vòng lặp 20 requests liên tiếp bằng token của `student` (giới hạn 10 req/phút):**

```http
# Request 1 (hợp lệ) → 200 OK
$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <REDACTED_TOKEN>" -H "Content-Type: application/json" -d '{"question": "Test 1"}'
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:38:36 GMT
server: uvicorn
content-length: 187
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 1","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

# Request 11 (chạm trần 10 req/60s) → 429 Too Many Requests
$ curl -i -X POST http://localhost:8000/ask -H "Authorization: Bearer <REDACTED_TOKEN>" -H "Content-Type: application/json" -d '{"question": "Test 11"}'
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 14:38:37 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795617577
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Tóm tắt diễn biến 20 lượt gọi trong vòng lặp:
- **Request 01 → 10:** Đều trả về `HTTP/1.1 200 OK`, trường `requests_remaining` giảm dần từ `9` về `0`.
- **Request 11 → 20:** Toàn bộ bị chặn với `HTTP/1.1 429 Too Many Requests` kèm header `Retry-After: 59`.

---

### Exercise 4.4: Cost guard implementation & Tại sao cần cả Rate Limit lẫn Cost Guard

1. **Cách hoạt động và triển khai Cost Guard:**
   - **Trong `04-api-gateway/production/cost_guard.py`:** `CostGuard` theo dõi lượng `input_tokens` và `output_tokens` tiêu thụ trong ngày, quy đổi sang USD theo đơn giá (`\$0.00015 / 1K input tokens`, `\$0.0006 / 1K output tokens`). Trước mỗi lần gọi LLM, `check_budget(user_id)` kiểm tra trần ngân sách toàn hệ thống (`\$10/ngày` → vượt trả `503`) và trần từng user (`\$1/ngày` → vượt trả **`402 Payment Required`**, đạt `80%` thì ghi log cảnh báo); sau khi LLM trả lời, `record_usage()` cộng dồn chi phí thực tế.
   - **Triển khai chuẩn Production với Redis (stateless cho nhiều worker/instance):**
     - Đặt key theo kỳ hạn, ví dụ theo ngày `cost:daily:{YYYY-MM-DD}` hoặc theo tháng cho từng user `budget:{user_id}:{YYYY-MM}`.
     - Trước khi gọi LLM: đọc `current = float(r.get(key) or 0)`; nếu `current + estimated_cost > BUDGET_LIMIT` (hoặc `current >= BUDGET_LIMIT`) thì chặn ngay bằng `HTTPException(status_code=402)`.
     - Sau khi gọi LLM: dùng lệnh nguyên tử `r.incrbyfloat(key, actual_cost)` để cộng tiền và đặt `r.expire(key, ttl_seconds)` (ví dụ `172800` giây cho ngân sách ngày hoặc `32 * 86400` giây cho ngân sách tháng) để dữ liệu tự động hết hạn sang kỳ mới mà không mất trạng thái khi restart/scale container.
2. **Vì sao cần CẢ Rate Limit LẪN Cost Guard?**
   - **Rate Limit bảo vệ tốc độ và tải hệ thống (ngắn hạn — theo giây/phút):** Ngăn spam/DDoS làm nghẽn worker hoặc chạm trần RPM của nhà cung cấp LLM, nhưng không kiểm soát được tổng tiền (một user gọi đều đặn 9 request/phút suốt 24 giờ vẫn tạo ra gần 13,000 lượt gọi LLM, hoặc gửi các prompt rất dài tốn nhiều token).
   - **Cost Guard bảo vệ ngân sách tài chính (dài hạn — theo số token & USD ngày/tháng):** Đảm bảo tổng chi phí API không bao giờ vượt trần tiền cho phép, nhưng nếu thiếu Rate Limit thì kẻ tấn công có thể bắn hàng trăm request đồng thời trong 1 giây gây quá tải hệ thống hoặc lọt qua bước kiểm tra ngân sách trước khi chi phí kịp cộng dồn. Hai cơ chế bổ trợ trực tiếp cho nhau.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks — Phân biệt Liveness (`/health`) và Readiness (`/ready`)

Đọc và kiểm thử `05-scaling-reliability/develop/app.py` & `production/app.py`:

| Tiêu chí | `GET /health` (Liveness Probe) | `GET /ready` (Readiness Probe) |
|---|---|---|
| **Câu hỏi trả lời** | Tiến trình (process) của container còn sống và phản hồi được không? | Instance này đã sẵn sàng nhận traffic thực tế từ người dùng chưa? |
| **Điều kiện trả mã lỗi** | Chỉ fail / timeout khi event loop bị treo, deadlock hoặc crash tiến trình. **Không được trả 500/503 chỉ vì mất kết nối tạm thời tới Redis/DB.** | Trả **`503 Service Unavailable`** khi đang khởi động (`_is_ready == False`), đang graceful shutdown, hoặc mất kết nối tới dependency bắt buộc như Redis (`_redis.ping()` lỗi). |
| **Hành động của Platform / LB** | Docker / Kubernetes / Railway sẽ **kill và restart lại container** nếu fail liên tiếp. | Load Balancer (Nginx / K8s Service) **tạm ngắt điều phối request mới** vào instance này nhưng **không giết container**, chờ đến khi dependency hồi phục. |

*(Nếu gộp kiểm tra Redis vào `/health` và trả 503 khi Redis chập chờn, orchestrator sẽ restart hàng loạt tất cả các container agent dù bản thân agent không bị hỏng — gây hiệu ứng dây chuyền cascading failure.)*

**Kết quả kiểm thử trên `05-scaling-reliability/develop/app.py`:**

```http
$ curl -i http://localhost:8000/health
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:52:48 GMT
server: uvicorn
content-length: 197
content-type: application/json

{"status":"degraded","uptime_seconds":0.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T14:52:48.995117+00:00","checks":{"memory":{"status":"degraded","used_percent":98.6}}}

$ curl -i http://localhost:8000/ready
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 14:52:48 GMT
server: uvicorn
content-length: 37
content-type: application/json

{"ready":true,"in_flight_requests":1}
```

---

### Exercise 5.2: Graceful shutdown (`SIGTERM`)

- **Cơ chế hoạt động trong `05-scaling-reliability/develop/app.py`:**
  1. Middleware `track_requests` tăng biến đếm `_in_flight_requests` khi nhận request và giảm trong khối `finally` khi xử lý xong.
  2. Khi nền tảng gửi tín hiệu `SIGTERM` (ví dụ lệnh `docker stop`), `uvicorn` kích hoạt phần sau `yield` của `lifespan(app)` (với `timeout_graceful_shutdown=30`).
  3. Cờ `_is_ready` lập tức chuyển về `False` để `/ready` trả `503` (Load Balancer ngưng đẩy request mới vào), đồng thời vòng lặp chờ `_in_flight_requests == 0` (tối đa 30 giây) để hoàn tất trọn vẹn các request đang chạy rồi mới thoát tiến trình với mã `0`.
- **Quan sát thực tế khi dừng 1 instance trong Docker (`docker stop k5-day14-scaling-agent-2`):**
  ```text
  agent-2  | INFO:     Shutting down
  agent-2  | INFO:     Waiting for application shutdown.
  agent-2  | INFO:app:Instance instance-49bfa6 shutting down
  agent-2  | INFO:     Application shutdown complete.
  agent-2  | INFO:     Finished server process [1]
  ```

---

### Exercise 5.3: Stateless design — Vì sao lưu state trong RAM bị hỏng khi scale?

- **Vấn đề của Stateful (in-memory dict `conversation_history = {}`):** Mỗi container/worker chạy trong không gian bộ nhớ RAM hoàn toàn tách biệt. Khi mở rộng lên 3 instance đứng sau Load Balancer (round-robin):
  - Lượt 1 của User A rơi vào `Instance 1` → lịch sử chỉ nằm trong RAM của `Instance 1`.
  - Lượt 2 của User A được Nginx chuyển sang `Instance 2` → RAM của `Instance 2` trống rỗng, agent mất sạch ngữ cảnh hội thoại (hoặc báo `404 Session not found`). Ngoài ra nếu `Instance 1` restart/scale-down, toàn bộ dữ liệu trong RAM mất vĩnh viễn.
- **Giải pháp Stateless (`05-scaling-reliability/production/app.py`):** Không giữ bất kỳ trạng thái phiên nào trong RAM của tiến trình Python; mọi thao tác đọc/ghi lịch sử (`save_session`, `load_session`, `append_to_history`) đều lưu vào **Redis** dùng chung với khóa `session:{session_id}` và `TTL = 3600s` (`_redis.setex`). Nhờ đó bất kỳ instance nào nhận request đều đọc được đúng lịch sử hội thoại mới nhất.

---

### Exercise 5.4 & 5.5: Load balancing với Nginx (`--scale agent=3`) & Kiểm thử `test_stateless.py`

Tạo file `.env.local` trong `05-scaling-reliability/production/`, khởi chạy stack với `-p k5-day14-scaling` mở cổng `8080`:

```text
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
$ docker compose -p k5-day14-scaling ps
NAME                       IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 14 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 14 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 14 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     28 seconds ago   Up 13 seconds             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     33 seconds ago   Up 25 seconds (healthy)   6379/tcp
```

Kiểm tra header `X-Served-By` từ Nginx thấy rõ lưu lượng được điều phối sang các IP container khác nhau (`172.20.0.5:8000` và `172.20.0.4:8000`):

```http
$ curl -i http://localhost:8080/health
HTTP/1.1 200 OK
Server: nginx/1.31.10
Date: Wed, 25 Nov 2026 14:56:35 GMT
Content-Type: application/json
Content-Length: 110
Connection: keep-alive
X-Served-By: 172.20.0.5:8000

{"status":"ok","instance_id":"instance-cae5aa","uptime_seconds":12.3,"storage":"redis","redis_connected":true}

$ curl -i http://localhost:8080/ready
HTTP/1.1 200 OK
Server: nginx/1.31.10
Date: Wed, 25 Nov 2026 14:56:35 GMT
Content-Type: application/json
Content-Length: 43
Connection: keep-alive
X-Served-By: 172.20.0.4:8000

{"ready":true,"instance":"instance-49bfa6"}
```

**Kết quả chạy `python test_stateless.py`:**

```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 261a2400-b946-47df-9a84-ff7bd4020c58

Request 1: [instance-cae5aa]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-8b37fa]
  Q: Why do we need containers?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 3: [instance-49bfa6]
  Q: What is Kubernetes?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 4: [instance-cae5aa]
  Q: How does load balancing work?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 5: [instance-8b37fa]
  Q: What is Redis used for?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-49bfa6', 'instance-cae5aa', 'instance-8b37fa'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Kubernetes?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: How does load balancing work?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Redis used for?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...

✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:**
1. **Phân tải Round-Robin qua Nginx:** 5 câu hỏi liên tiếp trong cùng phiên `261a2400-b946-47df-9a84-ff7bd4020c58` được Nginx chia đều lần lượt qua cả **3 container khác nhau** (`instance-cae5aa` → `instance-8b37fa` → `instance-49bfa6` → `instance-cae5aa` → `instance-8b37fa`).
2. **Bảo toàn trạng thái hội thoại nhờ Redis:** Khi gọi `GET /chat/261a2400-.../history` (rơi vào `agent-2`), hệ thống trả về đầy đủ **10 messages** (5 cặp `user` + `assistant`) theo đúng thứ tự thời gian vì cả 3 instance đều đọc/ghi chung khóa `session:261a2400-...` trên Redis.
3. **Chịu lỗi (Failover):** Khi thử dừng `k5-day14-scaling-agent-2`, Nginx tự động chuyển tiếp các request tiếp theo sang 2 instance còn sống (`instance-cae5aa`, `instance-8b37fa`) và trả `200 OK` không gián đoạn nhờ cấu hình `proxy_next_upstream error timeout http_503` trong `nginx.conf`.

*(Sau khi kiểm thử xong đã chạy `docker compose -p k5-day14-scaling down -v` để giải phóng cổng `8080` và bộ nhớ.)*

---

## Part 6: Final Project — Production-Ready AI Agent (`06-lab-complete/`)

### Tóm tắt các hạng mục đã hoàn thiện
- **`app/config.py` & `.env.example`:** Đọc tập trung toàn bộ cấu hình từ biến môi trường (`PORT`, `ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD` / `MONTHLY_BUDGET_USD`, `LOG_LEVEL`), không hardcode secret.
- **`app/auth.py`:** Xác thực header `X-API-Key` bằng `APIKeyHeader(auto_error=False)` và `secrets.compare_digest` — cả thiếu và sai khóa đều trả `401 Unauthorized`.
- **`app/redis_client.py`:** Khởi tạo connection pool `redis.from_url(..., socket_connect_timeout=1.5)` dạng lazy (không chặn startup khi chưa có Redis) và hàm `redis_healthy()` kiểm tra `ping()` cho `/ready`.
- **`app/rate_limiter.py`:** Thuật toán Sliding Window 60 giây trên Redis Sorted Set (`ZREMRANGEBYSCORE` → `ZCARD` → `ZADD` + `EXPIRE`), vượt ngưỡng trả `429 Too Many Requests` kèm header `Retry-After` và bảo toàn trạng thái qua các lần restart/nhiều worker.
- **`app/cost_guard.py`:** Cộng dồn chi phí token theo ngày vào Redis bằng `INCRBYFLOAT` (`cost:daily:YYYY-MM-DD`), chặn trước khi gọi LLM với mã `402 Payment Required` nếu chạm trần `DAILY_BUDGET_USD`.
- **`app/main.py`:** Định dạng toàn bộ log ứng dụng bằng `JsonFormatter`, tách biệt Liveness (`GET /health` luôn trả `200`) và Readiness (`GET /ready` trả `503` khi mất Redis hoặc đang tắt), xử lý lỗi không lộ stack trace, và quản lý Graceful Shutdown qua `lifespan`.
- **`Dockerfile`, `.dockerignore`, `docker-compose.yml`, `railway.toml`, `render.yaml`:** Multi-stage build với `python:3.11-slim` + `/opt/venv` (~`63 MB`), chạy dưới non-root `appuser`, có `HEALTHCHECK`, `uvicorn` chạy làm PID 1 (`exec uvicorn ... --port ${PORT:-8000} --workers 2`) tắt êm trong `0.9s` khi `docker stop`.

### Output kiểm tra `python check_production_ready.py` (Bản đầy đủ — POSIX + Docker)

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

### Mục 1 — Phân tích đề bài và thực hiện CP1 (Part 1: Localhost vs Production)
- **Hỏi AI:** Phân tích cấu trúc bài lab Day 14, hướng dẫn và hỗ trợ thực hiện CP1 (chạy kiểm thử bản `develop` và `production` trong `01-localhost-vs-production/`, tổng hợp câu trả lời vào `MISSION_ANSWERS.md`) cũng như cách đặt commit message chuẩn.
- **Nhận từ AI:** Giải thích tổng quan 7 phần của bài lab, các lưu ý riêng cho lớp K5, danh sách các anti-patterns trong `develop/app.py` đối chiếu với `production/app.py` & `production/config.py`, kịch bản kiểm thử các endpoint bằng `curl -i` và bảng so sánh chi tiết.
- **Tự sửa và tự kiểm tra:** Đã chạy thực tế cả hai server `develop/app.py` và `production/app.py` trên cổng `8000`, kiểm chứng trực tiếp mã trả về (`200 OK` khi truyền `?question=Hello`, `422` khi truyền JSON vào bản `develop`; `200 OK` trên `/health`, `/ready`, `/ask` ở bản `production`), đối chiếu từng số dòng code trong repo và kiểm tra `git status` đảm bảo không theo dõi file `.env`.

### Mục 2 — Thực hiện CP2 (Part 2: Docker Containerization)
- **Hỏi AI:** Tiếp tục thực hiện CP2 (build image `develop` và `advanced`, đo dung lượng thực tế, chạy container đơn lẻ và stack Docker Compose qua Nginx, cập nhật `MISSION_ANSWERS.md`).
- **Nhận từ AI:** Phân tích chi tiết các chỉ thị trong `02-docker/develop/Dockerfile` và `02-docker/production/Dockerfile`, cơ chế layer cache, sự khác nhau giữa `CMD` và `ENTRYPOINT`, kịch bản chạy build/test với cờ `-p k5-day14-docker` và sơ đồ kiến trúc 4 services (`nginx`, `agent`, `redis`, `qdrant`).
- **Tự sửa và tự kiểm tra:** Đã build trực tiếp cả hai image trên Docker Engine 29.6.2, lấy số đo thực tế từ `docker images my-agent` và `docker image inspect` (`1.67 GB` / `426.3 MB` so với `240 MB` / `57.4 MB`, giảm ~85.6%–86.5%), gọi `curl -i` kiểm chứng container `my-agent:develop` (cổng `8000`) và stack Docker Compose qua Nginx (cổng `80`), sau đó chạy `docker compose down -v` dọn sạch tài nguyên và kiểm tra `.env.local` đã nằm trong `.gitignore`.

### Mục 3 — Thực hiện CP3 (Part 4: API Security)
- **Hỏi AI:** Tiếp tục thực hiện CP3 (kiểm thử API Key ở bản `develop`, lấy JWT token và chạy vòng lặp 20 request kiểm thử Rate Limit ở bản `production`, phân tích Cost Guard và cập nhật `MISSION_ANSWERS.md`).
- **Nhận từ AI:** Giải thích cơ chế `verify_api_key`, luồng ký/xác thực JWT (`HS256`), thuật toán Sliding Window trong `rate_limiter.py`, cách thiết kế Cost Guard bằng Redis và kịch bản kiểm thử các mã trạng thái `401`, `403`, `200`, `429`.
- **Tự sửa và tự kiểm tra:** Đã chạy trực tiếp cả hai server `04-api-gateway/develop/app.py` (với `AGENT_API_KEY=secret-key-123`) và `04-api-gateway/production/app.py`, đăng nhập `POST /auth/token` bằng tài khoản `student` / `demo123`, chạy vòng lặp 20 request xác nhận 10 request đầu trả `200 OK` và từ request thứ 11 trả `429 Too Many Requests`, đồng thời kiểm tra toàn bộ chuỗi JWT đã được che thành `<REDACTED_TOKEN>` trước khi lưu vào `MISSION_ANSWERS.md`.

### Mục 4 — Thực hiện CP4 (Part 5: Scaling & Reliability)
- **Hỏi AI:** Tiếp tục thực hiện CP4 (kiểm thử `/health`, `/ready`, graceful shutdown ở bản `develop`, bật Docker Compose stack `--scale agent=3` với project `-p k5-day14-scaling`, chạy `test_stateless.py` và cập nhật `MISSION_ANSWERS.md`).
- **Nhận từ AI:** Phân biệt chi tiết Liveness (`/health`) và Readiness (`/ready`), giải thích cơ chế `lifespan` + `SIGTERM`, lý do lưu state trong RAM gây lỗi khi scale ngang, cùng kịch bản chạy và dọn dẹp stack `k5-day14-scaling`.
- **Tự sửa và tự kiểm tra:** Đã khởi chạy thực tế 3 container `agent` + `redis` + `nginx` trên cổng `8080`, chạy `python test_stateless.py` xác nhận cả 3 instance (`instance-cae5aa`, `instance-8b37fa`, `instance-49bfa6`) cùng xử lý một session mà vẫn giữ nguyên đủ 10 messages trong Redis, thử dừng 1 instance kiểm chứng graceful shutdown & failover của Nginx, sau đó chạy `docker compose -p k5-day14-scaling down -v` và kiểm tra `.env.local` không bị Git theo dõi.

### Mục 5 — Thực hiện CP5 (Part 6: Final Project — `06-lab-complete/`)
- **Hỏi AI:** Hỗ trợ hoàn thiện toàn bộ các chỗ `TODO` trong `06-lab-complete/` (`app/config.py`, `app/auth.py`, `app/redis_client.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) theo đúng hợp đồng 12 tiêu chí của Part 6.
- **Nhận từ AI:** Triển khai code đọc cấu hình 12-Factor, xác thực `X-API-Key` trả `401`, kết nối Redis lazy kèm `redis_healthy()`, rate limiter cửa sổ trượt bằng Redis Sorted Set (`429` + `Retry-After`), cost guard bằng `INCRBYFLOAT` (`402`), `JsonFormatter`, `lifespan` graceful shutdown, và multi-stage `Dockerfile` chạy non-root user với `exec uvicorn` ở PID 1.
- **Tự sửa và tự kiểm tra:** Đã đối chiếu từng module, xác nhận `check_production_ready.py` hoàn toàn không bị chỉnh sửa (`git diff` trống), và chạy bản chấm đầy đủ `python check_production_ready.py` trong môi trường Linux POSIX kết nối Docker Engine 29.6.2 đạt **`PASS 12/12` (`43/43 checks passed`)** với image size `63 MB` và thời gian `docker stop` `0.9s` (exit code `0`).
