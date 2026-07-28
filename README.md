# AI Agent Dashboard — Backend API

Multi-tenant SaaS backend for managing AI telephone agents, call transcripts, booking requests, a knowledge base, and ERPNext integration.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                          │
│  /api/v1/auth      /api/v1/agents     /api/v1/calls         │
│  /api/v1/companies /api/v1/phones     /api/v1/requests       │
│  /api/v1/users     /api/v1/kb         /api/v1/integrations  │
│  /api/v1/dashboard /api/v1/internal   (Voice Agent API)     │
└──────────────────┬──────────────────────────────────────────┘
                   │
       ┌───────────┴───────────┐
       │                       │
  PostgreSQL               Redis / Celery
  (Multi-tenant data)      (Async tasks)
       │
  ERPNext (via REST API)
```

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL 16 · Redis 7 · Celery · Alembic · Pydantic v2 · JWT · Docker

**Architecture:** Modular monolith. Each domain is a self-contained module under `app/modules/`.

## Local Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.12 (for local non-Docker development)

### 1. Clone and configure

```bash
git clone <repo-url>
cd ai-agent-dashboard
cp .env.example .env
```

Edit `.env` and set secure values for:
- `SECRET_KEY` — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- `CREDENTIAL_ENCRYPTION_KEY` — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `INTERNAL_API_KEY` — any random secret

### 2. Start with Docker

```bash
docker compose up --build
```

The API will be available at http://localhost:8000.

### 3. Run migrations

```bash
docker compose exec api alembic upgrade head
```

### 4. Load seed data

```bash
docker compose exec api python -m scripts.seed
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | JWT signing secret | — |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL | `60` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL | `7` |
| `DATABASE_URL` | PostgreSQL async URL | — |
| `REDIS_URL` | Redis connection URL | — |
| `CELERY_BROKER_URL` | Celery broker (Redis) | — |
| `CELERY_RESULT_BACKEND` | Celery backend (Redis) | — |
| `CREDENTIAL_ENCRYPTION_KEY` | Fernet key for credentials | — |
| `INTERNAL_API_KEY` | Key for Voice Agent internal API | — |
| `CORS_ORIGINS` | JSON list of allowed CORS origins | — |
| `STORAGE_ENDPOINT` | MinIO / S3 endpoint | — |
| `STORAGE_ACCESS_KEY` | Storage access key | — |
| `STORAGE_SECRET_KEY` | Storage secret key | — |
| `STORAGE_BUCKET` | Storage bucket name | — |

## Database Migrations

```bash
# Generate a new migration
alembic revision --autogenerate -m "description"

# Apply all migrations
alembic upgrade head

# Roll back one step
alembic downgrade -1
```

## Seed Data / Demo Accounts

After running migrations, load demo data:

```bash
python -m scripts.seed
# or via Docker:
docker compose exec api python -m scripts.seed
```

**Demo credentials** (development only — never use in production):

| Email | Password | Role |
|---|---|---|
| `superadmin@example.com` | `SuperAdmin123!` | Super Admin |
| `admin@demo-car-rental.com` | `Admin123!` | Company Admin |
| `operator@demo-car-rental.com` | `Operator123!` | Operator |
| `admin@demo-restaurant.com` | `Admin123!` | Company Admin |
| `operator@demo-restaurant.com` | `Operator123!` | Operator |

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt pytest pytest-asyncio httpx

# Run all tests
pytest app/tests/ -v

# Run with coverage
pytest app/tests/ -v --tb=short
```

## API Documentation

Start the server and open:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Multi-Tenant Model

Every request is scoped to the authenticated user's `company_id`. The JWT payload includes:

```json
{
  "sub": "user-uuid",
  "company_id": "company-uuid",
  "role": "company_admin"
}
```

All database queries automatically filter by `company_id`. A user can never access data belonging to another company.

## User Roles

| Role | Access |
|---|---|
| `super_admin` | All companies, platform statistics, company management |
| `company_admin` | All resources within their company |
| `operator` | Read calls and requests, update request status |

## Celery Workers

Workers handle background tasks:

- **`sync_request_to_erpnext`** — Syncs completed call requests to ERPNext with retry logic (3 attempts, 120 s backoff)
- **`process_knowledge_document`** — Processes uploaded documents (placeholder for vector embedding)

Start the worker:

```bash
celery -A app.workers.celery_app worker --loglevel=info -Q calls,integrations
# or via Docker Compose (started automatically)
```

## ERPNext Integration

### Configuration

When creating an ERPNext integration, set the `configuration` JSON:

```json
{
  "customer_doctype": "Customer",
  "request_doctype": "Booking Request",
  "customer_group": "All Customer Groups",
  "territory": "All Territories",
  "field_mapping": {
    "customer_name": "customer_name",
    "customer_phone": "mobile_no",
    "request_type": "request_type",
    "vehicle_type": "vehicle_type",
    "pickup_location": "pickup_location",
    "pickup_date": "pickup_date",
    "return_date": "return_date"
  }
}
```

### Flow

1. Call completes → `POST /api/v1/calls/{id}/complete`
2. Backend creates a `Request` record
3. Celery task `sync_request_to_erpnext` is queued
4. Worker finds or creates ERPNext Customer by phone
5. Worker creates a document in `request_doctype`
6. External reference is saved to the `Request` record

### Test Connection

```http
POST /api/v1/integrations/{id}/test
Authorization: Bearer <token>
```

## Internal Voice Agent API

Used exclusively by the LiveKit Voice Agent service.

```
GET  /api/v1/internal/voice/resolve-agent?phone_number=+96880001234
POST /api/v1/internal/voice/calls
POST /api/v1/internal/voice/calls/{id}/messages
POST /api/v1/internal/voice/calls/{id}/complete
```

All requests require the header:

```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

### Resolve Agent Example

```bash
curl -H "X-Internal-Api-Key: your-key" \
  "http://localhost:8000/api/v1/internal/voice/resolve-agent?phone_number=%2B96880001234"
```

Response:

```json
{
  "company_id": "...",
  "agent_id": "...",
  "agent_name": "Car Rental Booking Agent",
  "language": "en",
  "greeting_message": "Welcome to Demo Car Rental!",
  "system_prompt": "You are a professional car rental booking assistant...",
  "voice_provider": "openai",
  "voice_id": "alloy",
  "stt_provider": "openai",
  "stt_model": "whisper-1",
  "llm_provider": "openai",
  "llm_model": "gpt-4.1-mini"
}
```

## Domain, Nginx, and HTTPS

Nginx is the public reverse proxy on ports `80` and `443`. The API itself is
only exposed to the internal Docker network on port `8000`. Certbot shares its
certificate and ACME challenge volumes with Nginx and checks for renewals every
12 hours.

### 1. Configure DNS and firewall

Create an `A` record for the API hostname pointing to the server's public IP.
If the server has IPv6, configure the matching `AAAA` record as well. Allow
inbound TCP ports `80` and `443` in the server firewall/security group.

### 2. Configure the environment

Set these values in `.env`:

```dotenv
DOMAIN=api.example.com
LETSENCRYPT_EMAIL=admin@example.com
CORS_ORIGINS=["https://dashboard.example.com"]
```

Use only the hostname in `DOMAIN`; do not include `https://` or a path.

### 3. Start the stack

```bash
docker compose up -d --build
```

On the first start, Nginx uses a one-day self-signed fallback certificate so
that it can start before the real certificate exists.

### 4. Request the first Let's Encrypt certificate

After DNS resolves to this server, run:

```bash
docker compose run --rm --entrypoint /bin/sh certbot -c \
  'certbot certonly --webroot --webroot-path=/var/www/certbot \
  --domain "$DOMAIN" --email "$LETSENCRYPT_EMAIL" \
  --agree-tos --no-eff-email'

docker compose restart nginx
```

Verify the deployment:

```bash
curl -I https://api.example.com/health
```

The long-running `certbot` service renews eligible certificates automatically.
Nginx reloads its configuration every 12 hours so renewed certificates are
picked up without recreating the stack.

## Project Structure

```
app/
├── main.py                    — FastAPI application, router registration
├── core/
│   ├── config.py              — Settings via pydantic-settings
│   ├── database.py            — Async SQLAlchemy engine and session
│   ├── security.py            — JWT, bcrypt, Fernet encryption
│   ├── dependencies.py        — Auth guards, TenantDependency
│   ├── permissions.py         — UserRole enum
│   └── exceptions.py          — Custom HTTP exceptions
├── modules/
│   ├── auth/                  — Login, refresh, logout, /me
│   ├── companies/             — Company CRUD
│   ├── users/                 — User management
│   ├── agents/                — AI agent configuration + templates
│   ├── phone_numbers/         — Phone number management
│   ├── calls/                 — Call lifecycle + transcripts
│   ├── requests/              — Booking/service requests
│   ├── knowledge_base/        — Q&A items + documents
│   ├── integrations/          — ERPNext + webhook connectors
│   └── dashboard/             — Statistics + internal Voice Agent API
├── workers/
│   ├── celery_app.py          — Celery configuration
│   ├── call_tasks.py          — Document processing tasks
│   └── integration_tasks.py  — ERPNext sync tasks
└── tests/                     — Pytest test suite
alembic/                       — Database migrations
scripts/
└── seed.py                    — Demo data seeder
```
