# Deployment Information

## Public URL
https://agent-production-6fcdd40d.up.railway.app

## Platform
Railway (Docker multi-stage build from `06-lab-complete/` + managed Railway Redis)

## Test Commands

### CP6 Self-Test (4 HTTP Status Checks — No Secret Leaked)
```bash
BASE="https://agent-production-6fcdd40d.up.railway.app"
# Set AGENT_API_KEY in your shell session before running:

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

### Health & Readiness Check
```bash
curl https://agent-production-6fcdd40d.up.railway.app/health
# Expected: {"status":"ok","uptime_seconds":...,"environment":"production"}

curl https://agent-production-6fcdd40d.up.railway.app/ready
# Expected: {"status":"ready"}
```

### API Test (with authentication)
```bash
curl -X POST https://agent-production-6fcdd40d.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set
- `PORT` (`8000`)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (`${{Redis.REDIS_URL}}` — linked to Railway Redis service)
- `AGENT_API_KEY` *(set securely via Railway Variables, not stored in Git)*
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `LOG_LEVEL` (`INFO`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
