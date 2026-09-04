# IncidentPilot — Production Deployment & Operations Guide

## 1. Deployment Architecture

IncidentPilot follows a lightweight, modular service architecture designed for high availability and low latency during technical incident management.

```
                     ┌──────────────────────────────────────────────┐
                     │          Internet / Edge / CDN               │
                     │  TLS Termination & DDoS Mitigation (Cloudflare)│
                     └──────────────────────┬───────────────────────┘
                                            │
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │          Ingress / Reverse Proxy             │
                     │      (Nginx / AWS ALB / Traefik)             │
                     └──────────────┬───────────────────────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               │                                         │
               ▼                                         ▼
┌───────────────────────────────┐       ┌───────────────────────────────┐
│     IncidentPilot API (App 1) │       │     IncidentPilot API (App 2) │
│  - FastAPI (Python 3.10)      │       │  - FastAPI (Python 3.10)      │
│  - Static War Room Assets     │       │  - Static War Room Assets     │
│  - Intelligence Rule Engine   │       │  - Intelligence Rule Engine   │
│  - Sandboxed Action Executors │       │  - Sandboxed Action Executors │
└──────────────┬────────────────┘       └──────────────┬────────────────┘
               │                                       │
               ├───────────────────┬───────────────────┤
               │                   │                   │
               ▼                   ▼                   ▼
┌─────────────────────────┐ ┌──────────────┐ ┌─────────────────────────┐
│   PostgreSQL 16 Engine  │ │  Agora RTC   │ │  External Integrations  │
│  - Primary Instance     │ │  Audio Cloud │ │  - Slack Web API        │
│  - Read Replicas        │ │  (Voice Room)│ │  - Jira REST API        │
│  - Append-Only Auditing │ └──────────────┘ │  - Datadog Telemetry    │
└─────────────────────────┘                  └─────────────────────────┘
```

---

## 2. Required Environment Variables

| Variable | Type | Required in Prod? | Default | Description & Sensitivity |
| :--- | :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | String | **Yes** | `development` | Options: `development`, `test`, `production`. |
| `LOG_LEVEL` | String | No | `INFO` | Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |
| `DATABASE_URL` | String | **Yes** | — | **PostgreSQL Required in Prod!** `postgresql+psycopg://user:pass@host:5432/dbname`. |
| `JWT_SECRET` | Secret | **Yes** | — | **Secret!** Minimum 32-character high-entropy secret. |
| `JWT_ALGORITHM` | String | No | `HS256` | JWT signing algorithm. |
| `JWT_ISSUER` | String | No | `incidentpilot` | Token issuer claim. |
| `JWT_AUDIENCE` | String | No | `incidentpilot-api` | Token audience claim. |
| `CORS_ORIGINS` | JSON List | **Yes** | `[]` | Explicit origin list (e.g. `["https://warroom.company.com"]`). Wildcard `*` prohibited. |
| `DB_POOL_SIZE` | Integer | No | `10` | SQLAlchemy connection pool size. |
| `DB_MAX_OVERFLOW` | Integer | No | `20` | Max overflow connections beyond pool size. |
| `DB_POOL_TIMEOUT` | Integer | No | `30` | Seconds to wait before timing out on pool checkout. |
| `DB_POOL_RECYCLE` | Integer | No | `1800` | Connection recycle period in seconds. |
| `AGORA_APP_ID` | String | Optional | — | Agora Application ID for RTC voice participation. |
| `AGORA_APP_CERTIFICATE` | Secret | Optional | — | **Secret!** Agora Application Certificate for token generation. |
| `SLACK_BOT_TOKEN` | Secret | Optional | — | **Secret!** Slack bot token (`xoxb-...`) for channel broadcasts. |
| `JIRA_BASE_URL` | String | Optional | — | Atlassian Jira cloud instance URL. |
| `JIRA_API_TOKEN` | Secret | Optional | — | **Secret!** Jira REST API user token. |
| `MONITORING_API_KEY` | Secret | Optional | — | **Secret!** Monitoring provider API key (Datadog/CloudWatch). |

---

## 3. Build Commands

### Local Container Build
```bash
docker build -t incidentpilot:latest .
```

### Multi-Platform / CI Container Build
```bash
docker buildx build --platform linux/amd64,linux/arm64 -t incidentpilot:0.1.0 --push .
```

---

## 4. Run & Startup Commands

### Docker Compose (API + PostgreSQL)
```bash
docker compose up -d --build
```

### Production Container Execution (Standalone)
```bash
docker run -d \
  --name incidentpilot-api \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  -e LOG_LEVEL=INFO \
  -e DATABASE_URL="postgresql+psycopg://incidentpilot:DB_PASS@postgres-host:5432/incidentpilot" \
  -e JWT_SECRET="your-32-char-min-high-entropy-jwt-secret" \
  -e CORS_ORIGINS='["https://incidentpilot.yourcompany.com"]' \
  -e AGORA_APP_ID="your-agora-app-id" \
  -e AGORA_APP_CERTIFICATE="your-agora-app-certificate" \
  -e WORKERS=4 \
  incidentpilot:latest
```

### Manual Host Execution
```bash
# 1. Activate environment
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows

# 2. Run Database Migrations
cd apps/api
alembic upgrade head

# 3. Start Production Server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 5. Health & Diagnostic Probes

- **General Health Check**: `GET /health` (or `GET /healthz`)
  - Validates process responsiveness and database connectivity.
  - Returns `200 OK` with JSON `{"status":"ok","database":"ok","version":"0.1.0","environment":"production"}`.
  - Returns `503 Service Unavailable` if database is down.
- **Kubernetes Liveness Probe**: `GET /health/live`
  - Returns `200 OK` (`{"status":"alive"}`) when container is running.
- **Kubernetes Readiness Probe**: `GET /health/ready`
  - Returns `200 OK` (`{"status":"ready"}`) only when the database is reachable.

---

## 6. Database Migrations Runbook

Alembic handles automated forward and backward schema migrations:

```bash
# Check current migration revision
alembic current

# Run forward migrations to latest version
alembic upgrade head

# Rollback one migration revision
alembic downgrade -1
```

---

## 7. Remaining Production Risks & Mitigations

| Risk Factor | Description | Mitigation Strategy |
| :--- | :--- | :--- |
| **Network Partition to Database** | Sudden RDS/PostgreSQL disconnection during an active incident. | `pool_pre_ping=True` and connection recycling ensure stale connections are evicted; `/health/ready` probe halts traffic to failed pods. |
| **Agora RTC API Outage** | External Agora infrastructure degraded during live incident. | App degrades gracefully: text and structured intelligence matrix remain functional if audio connection fails. |
| **Third-Party Rate Limits (Slack/Jira)** | Slack/Jira 429 rate limit during high-velocity updates. | Bounded exponential backoff retries in `BaseIntegrationClient` with automatic backoff delays. |
| **Secret Rotation** | Periodic rotation of JWT secret or Agora certificates. | Environment-driven configuration enables zero-downtime rolling updates on Kubernetes/ECS. |
