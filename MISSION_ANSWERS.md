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

## AI Log

### Mục 1 — Phân tích đề bài và thực hiện CP1 (Part 1: Localhost vs Production)
- **Hỏi AI:** Phân tích cấu trúc bài lab Day 14, hướng dẫn và hỗ trợ thực hiện CP1 (chạy kiểm thử bản `develop` và `production` trong `01-localhost-vs-production/`, tổng hợp câu trả lời vào `MISSION_ANSWERS.md`) cũng như cách đặt commit message chuẩn.
- **Nhận từ AI:** Giải thích tổng quan 7 phần của bài lab, các lưu ý riêng cho lớp K5, danh sách các anti-patterns trong `develop/app.py` đối chiếu với `production/app.py` & `production/config.py`, kịch bản kiểm thử các endpoint bằng `curl -i` và bảng so sánh chi tiết.
- **Tự sửa và tự kiểm tra:** Đã chạy thực tế cả hai server `develop/app.py` và `production/app.py` trên cổng `8000`, kiểm chứng trực tiếp mã trả về (`200 OK` khi truyền `?question=Hello`, `422` khi truyền JSON vào bản `develop`; `200 OK` trên `/health`, `/ready`, `/ask` ở bản `production`), đối chiếu từng số dòng code trong repo và kiểm tra `git status` đảm bảo không theo dõi file `.env`.

### Mục 2 — Thực hiện CP2 (Part 2: Docker Containerization)
- **Hỏi AI:** Tiếp tục thực hiện CP2 (build image `develop` và `advanced`, đo dung lượng thực tế, chạy container đơn lẻ và stack Docker Compose qua Nginx, cập nhật `MISSION_ANSWERS.md`).
- **Nhận từ AI:** Phân tích chi tiết các chỉ thị trong `02-docker/develop/Dockerfile` và `02-docker/production/Dockerfile`, cơ chế layer cache, sự khác nhau giữa `CMD` và `ENTRYPOINT`, kịch bản chạy build/test với cờ `-p k5-day14-docker` và sơ đồ kiến trúc 4 services (`nginx`, `agent`, `redis`, `qdrant`).
- **Tự sửa và tự kiểm tra:** Đã build trực tiếp cả hai image trên Docker Engine 29.6.2, lấy số đo thực tế từ `docker images my-agent` và `docker image inspect` (`1.67 GB` / `426.3 MB` so với `240 MB` / `57.4 MB`, giảm ~85.6%–86.5%), gọi `curl -i` kiểm chứng container `my-agent:develop` (cổng `8000`) và stack Docker Compose qua Nginx (cổng `80`), sau đó chạy `docker compose down -v` dọn sạch tài nguyên và kiểm tra `.env.local` đã nằm trong `.gitignore`.
