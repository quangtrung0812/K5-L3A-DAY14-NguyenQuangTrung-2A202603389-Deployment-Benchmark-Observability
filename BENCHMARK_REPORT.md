# Benchmark & Observability Report — Day 14

> Báo cáo kết quả đo kiểm hiệu năng, đánh giá chất lượng và giám sát vận hành thực tế của AI Agent.
> Toàn bộ con số được trích xuất trực tiếp từ các tệp JSON trong `reports/`, CSV trong `benchmark-results/` và ảnh chụp trong `screenshots/`.

**Họ tên:** Nguyễn Quang Trung — 2A202603389
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 x86_64, Python 3.14 / Python 3.11-slim, Docker Engine 29.6.2 (WSL2 backend)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ `500` ms | Đảm bảo 95% người dùng nhận được câu trả lời trong dưới 0.5 giây (phù hợp với pipeline RAG gồm ~20 ms retrieval + ~180 ms LLM call ở trạng thái bình thường), giữ trải nghiệm hội thoại tức thời trong khi vẫn cho phép phần nhỏ tail latency rơi vào p99. |
| Error rate `/ask` | ≤ `2.0` % | Cho phép 2.0% error budget để hấp thụ các lỗi mạng/upstream `503` thoáng qua từ nhà cung cấp LLM (~1% mặc định), đồng thời đặt ngưỡng cảnh báo `AgentHighErrorRate > 5%` kéo dài `1m` nhằm tránh báo động giả (alert fatigue). |
| Accuracy trên golden dataset | ≥ `85` % (không regression) | Đảm bảo chất lượng câu trả lời RAG đạt mức tin cậy cao trước khi đưa lên production và bắt buộc `regressions == 0` so với bản baseline liền trước trong CI/CD để không làm hỏng các câu từng trả lời đúng. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2 — `300` requests/mức, `MOCK_SLOW_RATE=0.03`)

*(Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json`)*

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
| 1 | `4.12` | `202.6` | `234.6` | `1709.8` | `1.33%` (`4/300`) | ✅ PASS |
| 10 | `36.09` | `201.6` | `234.5` | `1682.5` | `0.33%` (`1/300`) | ✅ PASS |
| 50 | `91.45` | `228.4` | `759.7` | `1724.0` | `0.67%` (`2/300`) | ❌ FAIL (`p95 > 500 ms`) |
| 100 | `53.2` | `427.4` | `3786.6` | `4184.9` | `0.67%` (`2/300`) | ❌ FAIL (`p95 > 500 ms`) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

RPS **chỉ tăng gần tuyến tính ở vùng tải thấp** (`c=1 → c=10`: tăng từ `4.12` lên `36.09 req/s`, gấp ~`8.76x` trong khi `p95` giữ nguyên ở ~`234.5 ms`), sau đó **tăng chậm dần rồi bão hòa và suy giảm ngược** khi quá tải (`c=50` đạt đỉnh `91.45 req/s` nhưng `p95` vọt lên `759.7 ms`; đến `c=100` thì RPS tụt xuống còn `53.2 req/s` và `p95` tăng vọt lên `3786.6 ms`). Nguyên nhân là ứng dụng đang chạy trên **1 tiến trình Python/uvicorn duy nhất**: khi đẩy 50–100 kết nối đồng thời dồn dập, chi phí chuyển ngữ cảnh trên event loop, tranh chấp socket HTTP, serialize JSON và tạo metric tăng mạnh (theo định luật Little / Amdahl), làm thời gian chờ trong hàng đợi (queueing delay) phình to và kéo tụt thông lượng thực tế.

### 2.2 Tail latency (`concurrency = 20`, `300` requests)

*(Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`)*

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| 0 | `206.4` | `236.8` | `250.7` |
| 0.03 (mặc định) | `266.1` | `255.9` | `1729.4` |
| 0.1 | `363.4` | `1705.6` | `1728.9` |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **Chỉ số nhạy nhất:** **`p99`** (khi tỷ lệ chậm nhỏ cỡ `3%`: `p99` nhảy vọt gấp **6.9 lần** từ `250.7 ms` lên `1729.4 ms` trong khi `p95` gần như chưa đổi ở `255.9 ms` và `avg` chỉ nhích nhẹ lên `266.1 ms`) và tiếp đến là **`p95`** khi tỷ lệ chậm vượt quá 5% (ở `MOCK_SLOW_RATE=0.1`, tức 10% request chậm, `p95` nhảy vọt từ `255.9 ms` lên **`1705.6 ms`**).
- **Vì sao SLO không bao giờ nên đặt theo `average`:** Ngay cả khi **10% người dùng phải chờ ~1.7 giây**, giá trị trung bình cộng `avg` vẫn chỉ là **`363.4 ms`** (nhìn bề ngoài vẫn thấp hơn hẳn ngưỡng `500 ms`!). Trung bình cộng bị kéo về phía đa số các request nhanh nên **che giấu hoàn toàn tail latency**; đặt SLO theo percentile (`p95`/`p99`) mới phản ánh trung thực trải nghiệm của nhóm người dùng chịu độ trễ xấu nhất.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

*(Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`)*

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---:|---:|---:|
| Accuracy | `4.3%` (`1/23`) | `91.3%` (`21/23`) | `100.0%` (`23/23`) |
| Avg tokens / câu | `57.2` | `109.0` | `113.7` |
| Tổng cost (USD) | `$0.000406` | `$0.000760` (`0.00076`) | `$0.000790` (`0.00079`) |
| Cost / câu đúng (USD) | `$0.00040575` | `$0.00003619` | `$0.00003436` |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS (`--min-accuracy 1.0`, `0` regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm mục kiến thức với từ khóa kích hoạt `["jwt", "xác thực"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`, giải thích rõ sự khác biệt giữa API key cố định và JWT là **token** có **chữ ký** số kèm thời điểm **hết hạn**. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm mục kiến thức với từ khóa kích hoạt `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `utils/mock_llm.py`, nêu rõ Kubernetes HPA scale số pod dựa trên **CPU**, **memory** hoặc **custom metrics** (như RPS, độ dài hàng đợi). |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Latency & Chi phí thô trên mỗi câu:** Agent `v2` có thêm bước truy xuất ngữ cảnh RAG (`search_knowledge_base` ~`20 ms`) và ghép tài liệu vào prompt nên lượng token trung bình mỗi câu tăng gần gấp đôi (`57.2 → 113.7 tokens`), làm tổng chi phí 23 câu tăng từ `$0.000406` lên `$0.000790` (+94.6%) và latency tăng nhẹ ~`20–30 ms`.
- **Hiệu quả kinh tế thực chất (`Cost / câu đúng`):** Agent `v1` tuy rẻ trên từng request nhưng trả lời sai tới `22/23` câu (`4.3%`), khiến chi phí để có **1 câu trả lời đúng** lên tới **`$0.00040575`**. Ngược lại, `v2` (sau khi sửa KB) đạt `100.0%` (`23/23`), kéo `Cost / câu đúng` xuống chỉ còn **`$0.00003436` — rẻ hơn gấp ~11.8 lần trên mỗi câu trả lời hữu ích** so với `v1`. Đánh đổi thêm ~20 ms và ~56 tokens/câu cho RAG là hoàn toàn xứng đáng.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception` / `error.type = upstream_unavailable`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với cả **4/4** alert đang **firing**: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.22` | `AgentHighErrorRate` | **`97.3 s`** (`pending` lúc `32.8 s` + `for: 1m`) | **Error rate** (đỏ > 20%) & **Requests/s theo status code** (`503` tăng vọt) |
| B | `MOCK_SLOW_RATE=0.35` | `AgentHighLatencyP95` | **`153.4 s`** (`pending` lúc `32.8 s` + `for: 2m`) | **Latency p95** & **Latency `/ask` — p50 / p95 / p99** (`p95 > 1s`) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | **`161.4 s`** (`pending` lúc `40.8 s` + `for: 2m`, đạt `$19.45/giờ`) | **Cost burn rate (USD/giờ)** & **LLM cost (1h)** |
| D | `docker pause` 1 instance (`agent-3`) | `AgentInstanceDown` | **`48.3 s`** (`pending` lúc `16.3 s` + `for: 30s`) | **Instances up** (giảm 1 instance) & **Requests/s theo instance** |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | Không firing (luôn `inactive`) | **Retrieval hit ratio** (mất/về 0), **Tokens/s** giảm, bảng **Agent version** hiện `v1` |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Đổi nhầm `AGENT_VERSION=v1` là **sự cố suy giảm chất lượng ngữ nghĩa (silent quality regression)** chứ không phải lỗi hạ tầng: HTTP vẫn trả `200 OK`, latency thậm chí nhanh hơn và chi phí thấp hơn nên cả 4 Golden Signals hạ tầng đều xanh. Để phát hiện trong production cần kết hợp 3 lớp:
1. **Pre-deploy CI Quality Gate:** Chạy tự động `eval/run_eval.py` trên golden dataset trong CI/CD trước mọi lần deploy/thay đổi config để chặn ngay từ vòng PR/release (accuracy tụt từ `100%` về `4.3%` → exit code `1`).
2. **Online Quality Evaluation & Business Metrics:** Đặt alert trên chính metric nghiệp vụ RAG (ví dụ cảnh báo khi `rate(agent_retrieval_total{result="hit"}[5m]) == 0` trong khi vẫn có traffic `/ask`), kết hợp lấy mẫu ngẫu nhiên (sampling 1–5% traffic thật) chấm điểm bất đồng bộ bằng **LLM-as-a-Judge** và theo dõi tỷ lệ người dùng bấm thumbs-down / hỏi lại.
3. **Canary / Shadow Deployment:** Điều hướng thử 5% lưu lượng vào bản mới và so sánh điểm chất lượng thực tế với bản hiện hành trước khi rollout 100%.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger ([screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)):

- `trace_id`: `a89770dfd30a40cec3d5ec38c7cb5790`
- Tổng thời gian (`POST /ask`): **`1718.16 ms`** (`1717.7 ms` ghi nhận ở middleware ứng dụng; hiển thị `1.7s` trên Jaeger)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**`1694.95 ms`**, chiếm **`98.65%`** tổng thời gian request; trong khi bước `agent.retrieve_context` chỉ mất `21.59 ms` = `1.26%`)
- Dòng log JSON tương ứng (grep theo `trace_id` `a89770dfd30a40cec3d5ec38c7cb5790` từ `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-25T16:17:19.186823+00:00", "level": "INFO", "service": "observable-agent", "instance": "4710dd6da888", "event": "llm_call", "trace_id": "a89770dfd30a40cec3d5ec38c7cb5790", "span_id": "98217546924f5374", "request_id": "5ff03a89bf97", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1694.9}
```

*(Đối chiếu thêm cho trace lỗi `20c0b90e67cac26c6f63639744f5ad70` trong [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png):)*

```json
{"ts": "2026-11-25T16:24:37.810600+00:00", "level": "INFO", "service": "observable-agent", "instance": "93e7f552bbf8", "event": "llm_error", "trace_id": "20c0b90e67cac26c6f63639744f5ad70", "span_id": "f668f964c8e03a2e", "request_id": "e147f15f8b35", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

*(Nguồn dữ liệu: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` — ghi rõ cả dòng riêng `POST /ask` và dòng tổng hợp `Aggregated` của Locust)*

| Số instance | RPS (`POST /ask` / `Aggregated`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures (`POST /ask`) |
|---:|---:|---:|---:|---:|---:|
| 1 | `59.79` / `65.79` | `190` | `220` | `1700` | `72 / 7150` (`1.01%`) |
| 3 | `60.22` / `66.29` | `190` | `220` | `1700` | `63 / 7193` (`0.88%`) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale từ 1 lên 3 instance hầu như KHÔNG làm giảm `p95` (`220 ms`) hay `p99` (`1700 ms`)**, và RPS cũng giữ quanh mức ~`60 req/s` cho `/ask` (~`66 req/s` tổng hợp).
- **Lý do & vị trí nút thắt (Bottleneck):**
  1. **Nút thắt độ trễ nằm ở dịch vụ LLM bên ngoài (I/O-bound upstream latency):** Như đã chứng minh qua Jaeger trace ở mục 4.3, hơn **98% thời gian của mỗi request là ngồi chờ cuộc gọi mạng bất đồng bộ (`await mock_llm.generate`) tới LLM API** (~`180 ms` bình thường, ~`1700 ms` khi rơi vào tail latency), không phải do nghẽn CPU bên trong container FastAPI. Tăng thêm replica cho tầng web không thể làm một cuộc gọi LLM bên ngoài trả lời nhanh hơn.
  2. **Tầng Agent dùng Async I/O chưa chạm trần CPU ở 100 Locust users:** Mỗi Locust user có `wait_time = between(0.5, 2)` giây nghỉ giữa các lần hỏi (trung bình ~`1.25s` nghỉ + `0.23s` xử lý ≈ `1.48s`/vòng → 100 users tạo ra tối đa `100 / 1.48 ≈ 67 req/s`), mức tải I/O bất đồng bộ này 1 container `uvicorn` vẫn xử lý thoải mái mà không bị nghẽn hàng đợi. Tuy nhiên, chạy 3 instances vẫn cực kỳ cần thiết cho **High Availability (chịu lỗi không downtime khi 1 instance dừng/deploy)** và mở rộng trần CPU khi lưu lượng tăng lên hàng trăm RPS hoặc có xử lý tiền xử lý nặng.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Không bao giờ đánh giá độ trễ qua số trung bình (`average`):** Chỉ 3–10% request bị tail latency đã khiến trải nghiệm thực tế ở `p95`/`p99` vọt lên gần 2 giây dù `avg` trông vẫn rất thấp (~`266–363 ms`); mọi SLO về tốc độ phải gắn với percentile.
  2. **Hiệu năng hạ tầng xanh không đồng nghĩa AI trả lời đúng:** Metrics hạ tầng (Prometheus/Grafana) chỉ bắt được lỗi 5xx, độ trễ cao hay hết ngân sách, hoàn toàn mù trước lỗi thoái hóa chất lượng ngữ nghĩa (như mất RAG ở thí nghiệm E). Bắt buộc phải kết hợp **Offline Golden Dataset Eval Gate** trong CI và giám sát chất lượng online, đồng thời so sánh hiệu quả chi phí bằng chỉ số **`Cost / câu đúng`**.
  3. **Liên kết chặt 3 trụ cột Metrics → Traces → Logs qua `trace_id`:** Metrics trên Grafana báo hiệu *khi nào* hệ thống có biến động, Jaeger trace chỉ đích danh *span nào* gây chậm (`chat mock-llm-small` chiếm `98.65%`), và `trace_id` gắn trong JSON log cho phép truy ngược ngay lập tức bản ghi chi tiết của chính request đó.
- **Nếu đưa agent này lên production thật, các metric / alert cần bổ sung thêm:**
  1. **Gateway / Edge Metrics & Synthetic Probes:** Đo tỷ lệ lỗi `502`/`504` và latency ngay tại tầng **Nginx / Load Balancer** (bắt được các request timeout mà tiến trình agent bị treo chưa kịp tự ghi nhận, như đã thấy khi `docker pause` ở thí nghiệm D).
  2. **Time-To-First-Token (TTFT) & Tokens-Per-Second (TPS):** Với giao diện streaming, người dùng cảm nhận độ phản hồi qua thời gian xuất hiện chữ đầu tiên (`llm_ttft_seconds`) hơn là tổng thời gian sinh toàn bộ câu trả lời.
  3. **RAG & Guardrail Quality Alerts:** Cảnh báo khi tỷ lệ `retrieval_miss` tăng đột biến, điểm tương đồng vector (`similarity_score`) tụt thấp (dấu hiệu trôi dữ liệu — data drift), tỷ lệ kích hoạt Rate Limit (`429`) / Cost Guard (`402`) tăng bất thường, hoặc điểm chấm tự động online (LLM-as-judge / user feedback) giảm dưới ngưỡng.
