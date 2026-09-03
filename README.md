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
| `LIVEKIT_URL` | LiveKit server URL used for SIP provisioning | — |
| `LIVEKIT_API_KEY` | Server-side LiveKit API key | — |
| `LIVEKIT_API_SECRET` | Server-side LiveKit API secret | — |
| `LIVEKIT_SIP_ENDPOINT` | LiveKit SIP hostname, without `sip:` | — |
| `LIVEKIT_AGENT_NAME` | Agent dispatched for inbound calls | `ai-agent-dashboard-inbound` |
| `WEB_TEST_CALL_MAX_DURATION_SECONDS` | Hard browser test-call limit | `600` |
| `WEB_TEST_CALL_TOKEN_TTL_SECONDS` | Browser join-token validity, including setup time | `660` |
| `ASTERISK_PROVISIONER_URL` | Private URL of the central FreePBX provisioner | — |
| `ASTERISK_PROVISIONER_API_KEY` | Shared secret for the provisioner API | — |
| `ASTERISK_PUBLIC_SIP_URI` | Public Asterisk SIP URI used as the provider destination | — |
| `ASTERISK_REQUEST_TIMEOUT_SECONDS` | Provisioner HTTP timeout | `15` |
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
- **`app.workers.knowledge_tasks.process_document`** — Extracts uploaded PDF, DOCX, TXT, Markdown,
  and CSV documents, chunks their text, and publishes a new tenant knowledge version

Start the worker:

```bash
celery -A app.workers.celery_app worker --loglevel=info -Q calls,integrations,notifications,knowledge
# or via Docker Compose (started automatically)
```

## Knowledge Base and low-latency voice sync

Knowledge can be company-wide (`agent_id=null`) or assigned to one Agent. Company admins can
manage Q&A entries, upload documents directly to private MinIO storage, inspect processing errors,
and retry failed documents. External document registration remains available but accepts only a
public HTTPS URL during processing; private and loopback destinations are rejected.

```http
GET  /api/v1/knowledge-base/templates
POST /api/v1/knowledge-base/templates/restaurant/apply
POST /api/v1/knowledge-base/templates/car_rental/apply
POST /api/v1/knowledge-base/documents/upload
GET  /api/v1/knowledge-base/documents/{document_id}
POST /api/v1/knowledge-base/documents/{document_id}/retry
```

Direct upload is multipart form data with `file` and optional `agent_id`. Supported formats are
PDF, DOCX, TXT, Markdown, and CSV. The default maximum is 20 MiB. The worker extracts and chunks
text; it does not execute macros, scripts, or instructions found inside documents.

Restaurant and car-rental starter templates contain editable operational Q&A entries. Applying a
template is idempotent for the selected company/Agent scope: matching questions are skipped rather
than duplicated.

Every successful Q&A mutation, completed document processing, or deletion increments
`companies.knowledge_version`. The existing Voice Agent resolve call returns that version. Voice
workers keep a process-wide cache keyed by `(agent_id, knowledge_version)` and download an internal
snapshot only on a cache miss. During a call, retrieval uses an in-memory multilingual lexical and
fuzzy vector index in LiveKit's `on_user_turn_completed` hook. It performs no Backend or embedding
API request for each caller question and avoids the extra model round trip of a tool call.

```dotenv
MAX_KNOWLEDGE_UPLOAD_BYTES=20971520
KNOWLEDGE_CHUNK_SIZE_CHARS=1400
KNOWLEDGE_CHUNK_OVERLAP_CHARS=180
KNOWLEDGE_SNAPSHOT_MAX_CHARS=250000
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

## Self-service phone numbers

The dashboard and public API expose one `Phone Numbers` resource. Internally, provider credentials
and infrastructure remain isolated from the number-to-agent mapping, but clients only need the
returned phone-number `id`. Every customer call follows the same route: provider -> central
Asterisk -> central LiveKit SIP trunk -> Voice Agent. Customers select `twilio` or `generic_sip`;
`asterisk` is the platform gateway and is not a customer provider option.

Create and provision a generic SIP connection:

```http
POST /api/v1/phone-numbers
Authorization: Bearer <company-admin-token>
Content-Type: application/json

{
  "name": "Office SIP",
  "provider": "generic_sip",
  "phone_number": "+96824000000",
  "agent_id": "<agent-uuid>",
  "sip": {
    "mode": "ip_trunk",
    "allowed_addresses": ["203.0.113.10/32"],
    "transport": "tcp"
  }
}
```

Then call `POST /api/v1/phone-numbers/{phone_number_id}/provision`. In `ip_trunk` mode our
Asterisk is configured automatically and the response returns
`provider_setup.destination_sip_uri`; the customer only configures that destination in the
provider panel. `allowed_addresses` must contain the provider's signaling IP/CIDR ranges.

For providers that support outbound registration, use the fully automatic mode on our side:

```json
{
  "sip": {
    "mode": "registration",
    "server_uri": "sip:provider.example.com",
    "server_port": 5061,
    "auth_username": "customer-user",
    "auth_password": "customer-password",
    "transport": "tls"
  }
}
```

For Twilio, send `account_sid`, `auth_token`, and `phone_number_sid` in the `twilio` object.
Provisioning configures the Twilio Elastic SIP Trunk with Asterisk as its Origination URI. Normal
GET/list responses never expose provider secrets.

Useful lifecycle endpoints:

- `GET /api/v1/phone-numbers`
- `GET /api/v1/phone-numbers/{phone_number_id}`
- `PATCH /api/v1/phone-numbers/{phone_number_id}`
- `POST /api/v1/phone-numbers/{phone_number_id}/test`
- `POST /api/v1/phone-numbers/{phone_number_id}/disconnect`
- `DELETE /api/v1/phone-numbers/{phone_number_id}` — disconnects provider resources first, then
  deletes the connection and number mapping

The former `/api/v1/phone-connections` compatibility endpoints have been removed. All dashboard
and API integrations must use `/api/v1/phone-numbers`.

`ip_trunk` initially becomes `awaiting_provider_setup`, registration becomes `registering`, and
Twilio becomes `testing`. A successful test or first resolved inbound call activates the mapping.
Credentials are encrypted with `CREDENTIAL_ENCRYPTION_KEY`. Apply migrations through
`0008_employee_extensions` using `alembic upgrade head` before deploying.

## Employee SIP extensions

Phone numbers are public DIDs and no longer contain an `extension` field. Employee extensions are
separate, tenant-scoped resources provisioned automatically on the shared FreePBX server.

```http
POST /api/v1/extensions
Authorization: Bearer <company-admin-token>
Content-Type: application/json

{
  "extension": "100",
  "display_name": "Sales",
  "employee_name": "Ali",
  "transport": "udp"
}
```

The create response contains `server`, `port`, `transport`, `username`, and a generated SIP
password. The password is returned only on create and password rotation; list and detail responses
never expose it. Configure those values in an employee's IP phone, Zoiper, Linphone, or MicroSIP.

Lifecycle endpoints:

- `GET /api/v1/extensions`
- `PATCH /api/v1/extensions/{extension_id}`
- `POST /api/v1/extensions/{extension_id}/rotate-password`
- `POST /api/v1/extensions/{extension_id}/enable`
- `POST /api/v1/extensions/{extension_id}/disable`
- `DELETE /api/v1/extensions/{extension_id}`

The same extension number may exist in different companies. FreePBX uses isolated tenant contexts,
and the Voice Agent resolves transfers by extension number or case-insensitive `display_name`
through the call's company before sending SIP REFER. `employee_name` is not a transfer target. If
multiple active extensions have the same display name, the caller must use the extension number.
The caller cannot provide an arbitrary phone number or SIP URI.

Before applying migration `0008`, verify that legacy extension-based mappings did not create the
same DID more than once:

```sql
SELECT phone_number, COUNT(*)
FROM phone_numbers
GROUP BY phone_number
HAVING COUNT(*) > 1;
```

The query must return no rows. The migration intentionally stops instead of guessing which legacy
agent mapping should own a duplicated DID.

### Cleaning up legacy per-number LiveKit trunks

The Asterisk-first flow uses one central LiveKit trunk and does not create customer trunks. If the
installation previously used per-number LiveKit provisioning, LiveKit may still refuse a duplicate
central trunk that serves a number already owned by a legacy trunk
(`Conflicting inbound SIP Trunks: "ST_..." and "<new>"`). Inspect and remove those legacy trunks
manually before creating the central trunk:

```bash
docker compose exec api python -m scripts.livekit_sip_trunks list --number +19714361744
```

```bash
docker compose exec api python -m scripts.livekit_sip_trunks rules --trunk-id ST_rT2teHJyoaoa
```

Delete the dispatch rules bound to the trunk before the trunk itself, then provision the
connection again:

```bash
docker compose exec api python -m scripts.livekit_sip_trunks delete-rule SDR_xxxxxxxx
```

```bash
docker compose exec api python -m scripts.livekit_sip_trunks delete ST_rT2teHJyoaoa
```

## Outbound campaigns

Migration `0010_outbound_campaigns` adds tenant-scoped outbound campaigns, recipients, attempts,
do-not-call entries, and `inbound`/`outbound` call direction. All PSTN traffic still uses the
customer's connected Phone Number and the shared FreePBX/Asterisk gateway.

Supported campaign types:

- `ai_conversation`: Asterisk calls the recipient and, after answer, bridges the call to the
  configured LiveKit Voice Agent. Contact fields are loaded once as outbound context.
- `voice_broadcast`: the Backend generates one WAV from `message_text`, stores it in MinIO, caches
  it on Asterisk, and Asterisk plays the same file to every answered recipient without LiveKit.
  TTS output is normalized to uncompressed PCM16 mono at 8 kHz before upload so FreePBX can play it
  reliably on an `ulaw`/`alaw` phone channel.
- `voice_broadcast_keypad`: broadcast plus DTMF actions. Supported action values are `hangup`,
  `repeat`, `ai`, `opt_out`, and `extension:100`. `opt_out` immediately adds the number to the
  tenant do-not-call list.

Main endpoints:

```http
POST /api/v1/outbound-campaigns
GET  /api/v1/outbound-campaigns
GET  /api/v1/outbound-campaigns/{campaign_id}
PATCH /api/v1/outbound-campaigns/{campaign_id}
POST /api/v1/outbound-campaigns/{campaign_id}/contacts/import
GET  /api/v1/outbound-campaigns/{campaign_id}/recipients
POST /api/v1/outbound-campaigns/{campaign_id}/validate
POST /api/v1/outbound-campaigns/{campaign_id}/audio
GET  /api/v1/outbound-campaigns/{campaign_id}/audio
POST /api/v1/outbound-campaigns/{campaign_id}/test-call
POST /api/v1/outbound-campaigns/{campaign_id}/schedule
POST /api/v1/outbound-campaigns/{campaign_id}/start
POST /api/v1/outbound-campaigns/{campaign_id}/pause
POST /api/v1/outbound-campaigns/{campaign_id}/resume
POST /api/v1/outbound-campaigns/{campaign_id}/cancel
GET  /api/v1/outbound-campaigns/{campaign_id}/results/export
POST /api/v1/outbound-campaigns/single-call
GET  /api/v1/outbound-campaigns/do-not-call
POST /api/v1/outbound-campaigns/do-not-call
```

Example AI campaign:

```json
{
  "name": "Appointment confirmations",
  "campaign_type": "ai_conversation",
  "phone_number_id": "<connected-phone-number-uuid>",
  "agent_id": "<active-agent-uuid>",
  "message_text": "Confirm tomorrow's appointment and offer another time if needed.",
  "timezone": "America/Denver",
  "calling_window_start": "09:00:00",
  "calling_window_end": "18:00:00",
  "max_concurrency": 2,
  "max_attempts": 2,
  "retry_delay_minutes": 30
}
```

Example keypad broadcast:

```json
{
  "name": "Reservation reminder",
  "campaign_type": "voice_broadcast_keypad",
  "phone_number_id": "<connected-phone-number-uuid>",
  "message_text": "Your reservation is tomorrow. Press 1 to repeat, 2 to speak to our AI assistant, 3 for Sales, or 9 to opt out.",
  "voice": "coral",
  "keypad_actions": {
    "1": "repeat",
    "2": "ai",
    "3": "extension:100",
    "9": "opt_out"
  }
}
```

Generate/approve the broadcast audio before validation or start:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message_text":"Your reservation is tomorrow.","voice":"coral"}' \
  https://api.example.com/api/v1/outbound-campaigns/$CAMPAIGN_ID/audio
```

Send the current editor text in the `/audio` request as shown above. The operation saves that text
and voice before generating the WAV, preventing a stale previously saved message from being used.
An empty body remains supported and generates from the campaign's already persisted values.

To play the generated WAV in the Dashboard, request a short-lived tenant-scoped download URL:

```http
GET /api/v1/outbound-campaigns/{campaign_id}/audio
```

```json
{
  "url": "https://storage.example.com/...signed...",
  "expires_in_seconds": 900,
  "media_id": "..."
}
```

Set the returned `url` as the browser `<audio src>` value. Request a fresh URL after it expires;
never persist the signed URL as campaign state.

CSV and XLSX imports require a `phone_number` column in E.164 form. Optional standard columns are
`first_name`, `last_name`, `language`, `timezone`, `external_id`, `consent_at`, and `do_not_call`.
Every other column is retained in `custom_fields` and is available to an AI campaign. Duplicate
numbers are skipped. Invalid rows are returned with their source row number. Maximum import size is
controlled by `OUTBOUND_MAX_IMPORT_ROWS`.

```csv
phone_number,first_name,last_name,timezone,external_id,consent_at,appointment_date
+14155550101,John,Smith,America/Denver,C-101,2026-08-01T10:00:00Z,2026-08-25
+14155550102,Sarah,Jones,America/Chicago,C-102,2026-08-02T10:00:00Z,2026-08-26
```

The Celery worker enforces the campaign and platform concurrency caps, subscription state/monthly
minutes, recipient timezone/calling window, retry delay, and do-not-call suppression. Celery Beat
starts scheduled campaigns and rechecks running campaigns. Calls outside their local window are
deferred to the next opening time.

Configure the Backend `.env`:

```dotenv
OPENAI_API_KEY=...
OUTBOUND_MAX_IMPORT_ROWS=10000
OUTBOUND_MAX_CONCURRENCY_PER_COMPANY=5
OUTBOUND_DISPATCH_INTERVAL_SECONDS=15
ASTERISK_PROVISIONER_URL=http://asterisk-private-ip:9443
ASTERISK_PROVISIONER_API_KEY=shared-secret
```

For generic SIP `ip_trunk` connections, provide `sip.server_uri` as the provider's outbound
termination URI in addition to `allowed_addresses`; inbound-only trunks cannot place calls.
Twilio provisioning now creates a Termination Credential List and SIP credential automatically,
associates it with the Elastic SIP Trunk, and sends the encrypted credential to Asterisk. Existing
Twilio connections created before this release must be disconnected and provisioned again once.

Run the Backend stack:

```bash
docker compose run --rm api alembic upgrade head
docker compose up -d --build api celery-worker celery-beat redis db minio minio-init
docker compose logs -f api celery-worker celery-beat
```

Run the automated API tests:

```bash
docker compose run --rm api pytest app/tests/test_outbound_campaigns.py -q
```

## Internal Voice Agent API

Used exclusively by the LiveKit Voice Agent service.

```
GET  /api/v1/internal/voice/resolve-agent?phone_number=+96880001234
POST /api/v1/internal/voice/calls
POST /api/v1/internal/voice/calls/{id}/messages
POST /api/v1/internal/voice/calls/{id}/complete
POST /api/v1/internal/voice/recordings/asterisk
```

All requests require the header:

```
X-Internal-Api-Key: <INTERNAL_API_KEY>
```

The Asterisk upload endpoint accepts multipart fields `linked_id` and `recording`. The linked ID
must already be present in the Call metadata; uploaded WAV files are stored in the private
MinIO/S3 bucket. Authenticated Dashboard clients obtain a temporary download URL from
`GET /api/v1/calls/{id}/recording-url`.

When the API runs in Docker Compose, its storage endpoint defaults to `http://minio:9000` and the
`minio-init` one-shot service creates the private bucket. Set `STORAGE_ENDPOINT_DOCKER` only when
Compose should use an external S3-compatible service. Recording uploads default to 50 MiB and
temporary download links default to 900 seconds; configure them with
`MAX_RECORDING_UPLOAD_BYTES` and `RECORDING_PRESIGNED_URL_EXPIRE_SECONDS`.
Set `STORAGE_PUBLIC_ENDPOINT=https://api.example.com` to the browser-reachable HTTPS Nginx
origin; when omitted, Docker Compose derives it from `DOMAIN`. It is used only to sign download
links, while uploads continue through the private Docker endpoint. Nginx streams the bucket path
(for example `/ai-agent-dashboard/...`) to MinIO without rewriting the signed URI and supports
byte ranges so browser audio controls can seek within a recording. The bucket remains private and
objects require a temporary presigned URL returned by
`GET /api/v1/calls/{id}/recording-url`.

### Resolve Agent Example

Realtime agents use a server-owned hybrid pipeline: OpenAI `gpt-realtime` receives the caller's
audio and returns text, then ElevenLabs `eleven_flash_v2_5` streams the spoken response. API
clients select this mode with `use_realtime=true` and may set only the ElevenLabs `voice_id` for
the Realtime path. `realtime_provider`, `realtime_model`, and `voice_provider` are read-only;
`tts_provider` and `tts_model` remain writable only for Pipeline agents and are ignored and
canonicalized by the Backend whenever `use_realtime=true`.

```json
{
  "name": "Realtime Sales Agent",
  "language": "en",
  "use_realtime": true,
  "voice_id": "JBFqnCBsd6RMkjVDRZzb"
}
```

Pipeline agents (`use_realtime=false`) may continue to configure their separate STT, LLM, and TTS
fields. Apply migration `0012_realtime_elevenlabs` after deploying this change; it converts
existing Realtime agents to the fixed hybrid configuration.

Authenticated Company Admins populate the voice selector from one unified
catalog endpoint:

```http
GET /api/v1/agents/voices
```

The Backend reads every page from both ElevenLabs **My Voices** and the public
Voice Library, merges duplicate `voice_id` values, and returns the complete
result. It does not expose `verified_languages`. Example response:

```json
{
  "voices": [
    {
      "public_owner_id": "PUBLIC_OWNER_ID",
      "voice_id": "VOICE_ID",
      "name": "Sales Voice",
      "category": "professional",
      "preview_url": "https://...",
      "labels": {"language": "en", "gender": "female"},
      "public_owner_id": "PUBLIC_OWNER_ID",
      "in_my_voices": false
    }
  ],
  "total": 745,
  "cached": false
}
```

Results are cached for `ELEVENLABS_VOICE_CACHE_SECONDS`; use
`GET /api/v1/agents/voices?force_refresh=true` when an immediate refresh is
needed. Configure `ELEVENLABS_API_KEY` in the Backend as well as the Voice Agent.
The key is server-only and is never included in responses.

The frontend only sends the selected `voice_id` in the normal Agent create or
update request. For Realtime Agents, and pipeline Agents whose `tts_provider` is
`elevenlabs`, the Backend checks My Voices before saving. If the selected public
voice is missing, it finds its `public_owner_id` from the full library and adds
it to My Voices automatically. Existing My Voices are not added again. An
unknown `voice_id` returns `VALIDATION_ERROR`; an ElevenLabs failure returns
`INTEGRATION_ERROR`. Voice Library access and My Voices limits remain subject to
the ElevenLabs account plan.

### Browser test calls

An authenticated tenant user can test any Agent belonging to their company without connecting a
phone number:

```http
POST /api/v1/agents/{agent_id}/test-calls
GET  /api/v1/agents/test-calls/usage
```

The POST response contains `livekit_url`, a short-lived `access_token`, `room_name`, `call_id`,
`participant_identity`, `max_duration_seconds`, and `expires_at`. The token is restricted to that
single room, can publish only microphone audio, and explicitly dispatches
`LIVEKIT_AGENT_NAME`. Never expose `LIVEKIT_API_SECRET` in the frontend.

Minimal browser integration with `livekit-client`:

```ts
import { Room } from "livekit-client";

const session = await api.post(`/api/v1/agents/${agentId}/test-calls`);
const room = new Room();
await room.connect(session.livekit_url, session.access_token);
await room.localParticipant.setMicrophoneEnabled(true);

// Stop button / component cleanup
room.disconnect();
```

Start the visible countdown from `max_duration_seconds` after `room.connect()` succeeds. The Voice
Agent closes the session at 600 seconds even if the browser timer is bypassed. Browser test calls
use the Agent's normal greeting, models, selected voice, prompt, Knowledge Base, transcript,
summary, outcome, and extracted-data pipeline. SIP transfer is intentionally unavailable: the
transfer tool is not exposed to the model, and the internal transfer endpoint rejects test Calls.

Each session is stored in `calls` with `source=web_test`; normal calls use `source=telephony`.
`GET /api/v1/agents/test-calls/usage` returns test seconds/minutes for the current subscription
period. `GET /api/v1/billing/usage` includes test usage in `minutes_used` and additionally returns
`telephony_minutes_used`, `web_test_minutes_used`, and
`web_test_max_duration_seconds_per_call`. The calls list can be filtered with
`GET /api/v1/calls?source=web_test`.

The Dashboard origin must be present in `CORS_ORIGINS`, and the browser must be allowed to use its
microphone. Apply migration `0013_web_test_calls` and deploy the Backend and Voice Agent together.

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

## Self-Service Registration and Onboarding

Customers can register a company and its first `company_admin` without Super
Admin intervention:

```http
POST /api/v1/auth/signup
POST /api/v1/auth/verify-email
POST /api/v1/auth/resend-verification
POST /api/v1/auth/forgot-password
POST /api/v1/auth/reset-password
GET  /api/v1/onboarding/status
PATCH /api/v1/onboarding/company
POST /api/v1/onboarding/complete
```

Signup creates the Company, first administrator, and hashed one-time
verification token in one database transaction. The Company starts in
`pending_verification`. Email verification returns access and refresh tokens,
starts a 14-day trial, and changes the Company status to `trial`.

Raw verification, password-reset, and refresh tokens are never stored in the
database. Verification and reset tokens are single-use and expire. Password
reset also revokes every active refresh token for the user.

The onboarding company endpoint accepts the optional `agent_template` values
`restaurant`, `car_rental`, `customer_support`, or `blank`. Template agents are
created as drafts. It also accepts `phone_connection` values
`managed_number`, `sip_trunk`, or `skip`; managed-number and SIP requests are
stored as pending telephony connections and do not modify production telephony
configuration.

For development, `EMAIL_PROVIDER=console` writes email content to worker logs.
For production configure `EMAIL_PROVIDER=smtp` and the `SMTP_*` environment
variables. The Celery worker must consume the `notifications` queue.

### Public website voice preview

The website's server-side proxy can request a personalized MP3 greeting:

```http
POST /api/v1/public/voice-preview
Authorization: Bearer <WEBSITE_API_KEY>
Content-Type: application/json

{
  "company_name": "Acme Pizza",
  "voice": "coral"
}
```

The response is `audio/mpeg` and says: `Thanks for calling Acme Pizza. You're through to the AI
agent — how can I help you today?` Supported voices are `alloy`, `ash`, `ballad`, `coral`, `echo`,
`fable`, `onyx`, `nova`, `sage`, `shimmer`, `verse`, `marin`, and `cedar`. The fixed template cannot
be replaced by the caller. Requests are limited to 10 per client IP per hour.

Configure `OPENAI_API_KEY` and optionally `TTS_PREVIEW_MODEL` (default `tts-1`) on the Backend. Keep
`WEBSITE_API_KEY` in the website's server-side proxy; do not embed it in browser JavaScript.

Apply the signup migration before deploying the new API:

```bash
docker compose run --rm api alembic upgrade head
docker compose up -d --build --force-recreate api celery-worker
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

## Super Admin client overview

Super Admin accounts can inspect cross-company package and usage data without a
tenant/company context:

```http
GET /api/v1/admin/clients?page=1&page_size=20
GET /api/v1/admin/clients/{company_id}
GET /api/v1/admin/plans
PATCH /api/v1/admin/clients/{company_id}/subscription
```

The client report includes agent and integration counts, the assigned package,
and UTC calendar-month call minutes used and remaining. A package can be
assigned with:

```json
{
  "plan_id": "00000000-0000-0000-0000-000000000102",
  "status": "active"
}
```

Default package limits are seeded by migration `0003_billing_admin`; adjust
them in the `plans` table to match the commercial pricing rules.

## Billing and subscriptions API

Migration `0005_billing_invoices` adds monthly prices, pending plan changes,
scheduled cancellation, invoices, and payment history. Monetary values use the
smallest currency unit (`9900` means USD 99.00) to avoid floating-point errors.

Tenant endpoints:

```http
GET  /api/v1/billing/plans
GET  /api/v1/billing/subscription
GET  /api/v1/billing/usage
GET  /api/v1/billing/invoices
GET  /api/v1/billing/invoices/{invoice_id}
GET  /api/v1/billing/payments
POST /api/v1/billing/subscription/change
POST /api/v1/billing/subscription/cancel
POST /api/v1/billing/subscription/resume
```

A paid plan change creates an open invoice and leaves the existing plan active.
The pending plan becomes active only after the invoice has been paid in full.
Free plans switch immediately. Cancellation is scheduled for the end of the
current period and can be resumed before then.

### Subscription entitlement enforcement

Paid features are checked server-side; dashboard clients must not rely only on
disabled buttons. A subscription must be `active` or `trial`, the current time
must be inside its billing period, and its plan must still be active. A scheduled
cancellation continues to work until the end of the paid period.

| Operation | Enforcement |
| --- | --- |
| Create an agent | Active subscription + `plan.max_agents` |
| Create an integration | Active subscription + `plan.max_integrations` |
| Create/run/schedule/resume an outbound campaign | Active subscription; execution also requires remaining monthly minutes |
| Start a browser test call | Active subscription + remaining monthly minutes |
| Resolve an inbound or outbound AI call | Active subscription + remaining monthly minutes |

Agent and integration checks lock the company's unique subscription row until
the create transaction commits. This prevents simultaneous requests from both
using the final available slot on PostgreSQL. A `null` plan limit means
unlimited. Browser test, inbound, and outbound durations all consume the same
`monthly_minutes` allowance shown by `GET /api/v1/billing/usage`.

Entitlement failures use the standard structured error response:

```json
{
  "error": {
    "code": "PLAN_LIMIT_REACHED",
    "message": "The plan limit for agents has been reached.",
    "details": {"resource": "agents", "used": 1, "limit": 1}
  }
}
```

Frontend clients should handle `SUBSCRIPTION_REQUIRED`,
`SUBSCRIPTION_INACTIVE`, `SUBSCRIPTION_PERIOD_INACTIVE`, `PLAN_UNAVAILABLE`,
`PLAN_LIMIT_REACHED`, and `MONTHLY_MINUTES_EXHAUSTED`. If a worker encounters
one of these conditions, it pauses the outbound campaign and stores the code and
details in `settings.pause_reason` and `settings.pause_details`.

Super Admin endpoints:

```http
POST  /api/v1/admin/billing/plans
PATCH /api/v1/admin/billing/plans/{plan_id}
DELETE /api/v1/admin/billing/plans/{plan_id}
GET   /api/v1/admin/billing/invoices
GET   /api/v1/admin/billing/invoices/{invoice_id}
POST  /api/v1/admin/billing/invoices
POST  /api/v1/admin/billing/invoices/{invoice_id}/payments
POST  /api/v1/admin/billing/invoices/{invoice_id}/void
GET   /api/v1/admin/billing/payments
```

The payment endpoint records a verified/manual or externally confirmed payment;
it does not collect card details. Connect Stripe or another payment provider by
verifying its webhook first and then recording the provider reference through
this API. Reusing the same external reference is idempotent only when invoice and
amount are identical.

### Stripe Checkout

Stripe-hosted Checkout and the Customer Portal are available for company admins:

```http
POST /api/v1/billing/stripe/checkout-session
POST /api/v1/billing/stripe/portal-session
POST /api/v1/billing/stripe/webhook
```

Send only the internal `plan_id` to the Checkout endpoint. The API resolves the
trusted `stripe_price_id` configured on the plan and returns `session_id` and
`checkout_url`. Redirect the browser to that URL. Do not activate access from
the frontend success redirect; the signed webhook activates the plan.

Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` in `.env`. Optionally set
`STRIPE_CHECKOUT_SUCCESS_URL` and `STRIPE_CHECKOUT_CANCEL_URL`; otherwise they
default to the `/billing` page under `FRONTEND_URL`. Configure the Stripe webhook
destination as:

```text
https://<API_DOMAIN>/api/v1/billing/stripe/webhook
```

Subscribe it to `checkout.session.completed`,
`checkout.session.async_payment_succeeded`, `invoice.paid`,
`invoice.payment_failed`, `customer.subscription.updated`, and
`customer.subscription.deleted`. Webhook event IDs are persisted so duplicate
deliveries are safe. Successful renewal invoices and payments are mirrored into
the local billing history.

Each paid local plan must have a recurring Stripe Price ID. A super admin can
set it through `POST /api/v1/admin/billing/plans` or `PATCH` the existing plan:

```json
{
  "stripe_price_id": "price_..."
}
```

Once a company has a Stripe subscription, use the Customer Portal for later
plan changes, payment-method updates, invoices, and cancellation management.

Apply the schema before using these endpoints:

```bash
docker compose run --rm api alembic upgrade head
```

## SMTP test

Run the automated SMTP tests first. They use a fake SMTP server and verify TLS,
authentication, sender/recipient headers, and text/HTML content without sending
a real email:

```bash
docker compose run --rm api pytest app/tests/test_smtp_email.py -q
```

Expected result:

```text
2 passed
```

To test the real SMTP provider, configure `.env`:

```dotenv
EMAIL_PROVIDER=smtp
EMAIL_FROM=no-reply@yourdomain.com
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USERNAME=your-username
SMTP_PASSWORD=your-password
SMTP_USE_TLS=true
```

Then send one real diagnostic email:

```bash
docker compose run --rm api python -m scripts.test_smtp you@example.com
```

Expected output:

```text
SMTP accepted the test message for you@example.com.
```

This output confirms that the SMTP server accepted the message. Inbox delivery
can still depend on the provider's SPF, DKIM, DMARC, and spam policies. Do not
commit real SMTP credentials to Git.

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
