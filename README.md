# CareCloud Voice AI — Patient Registration

A voice-based intake agent on a real U.S. number. Callers register as a new patient through natural conversation. Confirmed demographics are validated server-side, stored in PostgreSQL, and exposed through a REST API. A second call still sees the first call’s data.

## Live demo

| | |
| --- | --- |
| **Phone** | [+1 (810) 279-1519](tel:+18102791519) |
| **API** | https://codecloud-voice-agent.onrender.com |
| **OpenAPI docs** | https://codecloud-voice-agent.onrender.com/docs |
| **List patients** | https://codecloud-voice-agent.onrender.com/patients |
| **Health** | https://codecloud-voice-agent.onrender.com/health |
| **Vapi webhook** | `POST https://codecloud-voice-agent.onrender.com/vapi-webhook` |

> Render’s free web service sleeps after inactivity. The first request (or first call that hits the webhook) can take **50+ seconds** to wake. If the line is silent at first, wait and try again.

### Reviewer: place a call (about 3 minutes)

1. Dial **+1 (810) 279-1519** from any phone.
2. Speak naturally. The agent is an intake coordinator, not an IVR menu. Give required demographics in any order; correct yourself if needed (“Actually, that’s D-A-V-I-S”).
3. Required fields: first name, last name, date of birth (`MM/DD/YYYY`, not in the future), sex (`Male` / `Female` / `Other` / `Decline to Answer`), 10-digit U.S. phone, street address, city, 2-letter state, ZIP (5-digit or ZIP+4).
4. Optional fields are offered, not forced: *“I can also collect your insurance information, emergency contact, and preferred language. Would you like to provide any of those?”*
5. The agent **reads everything back** and waits for confirm or corrections **before** saving.
6. On success you should hear something like *“You're all set, [First Name].”* then a graceful hangup.
7. Confirm persistence:
   - Open [GET /patients](https://codecloud-voice-agent.onrender.com/patients) or filter `?phone_number=your10digits`.
   - Call the number again. If that phone already exists, the agent should say it already has a record and offer to **update** instead of create.

**Demo seed records** (present after first empty-database start):

| Name | `patient_id` | Phone |
| --- | --- | --- |
| Jane Doe | `11111111-1111-4111-8111-111111111111` | `4155552671` |
| Carlos O'Brien | `22222222-2222-4222-8222-222222222222` | `2125550199` |

```text
GET https://codecloud-voice-agent.onrender.com/patients?last_name=Doe
GET https://codecloud-voice-agent.onrender.com/patients?phone_number=4155552671
GET https://codecloud-voice-agent.onrender.com/patients/11111111-1111-4111-8111-111111111111
```

---

## Architecture

```
Caller
  │  +1 (810) 279-1519
  ▼
Vapi (telephony + STT + LLM + TTS)
  │  POST /vapi-webhook  (tool-calls, end-of-call-report)
  ▼
FastAPI on Render
  │  same Pydantic models as REST
  ▼
PostgreSQL (Render)
  │
  └── REST  GET/POST/PUT/DELETE /patients
```

Separation of concerns:

| Layer | Responsibility |
| --- | --- |
| **Vapi** | U.S. number, speech-to-text, LLM conversation, text-to-speech, call control |
| **FastAPI** | Webhooks, REST, HTTP status codes, envelope, logging |
| **Pydantic** | Server-side demographic rules (the voice agent is not trusted alone) |
| **SQLAlchemy + PostgreSQL** | Typed columns, required/nullable constraints, UTC timestamps, soft-delete |

The voice agent does **not** talk to SQL directly. After the caller confirms, Vapi invokes tools on `/vapi-webhook`, which run the same persist path as `POST` / `PUT /patients`.

### Tech stack justification

| Choice | Why |
| --- | --- |
| **Vapi** | Fastest path to a dialable number with STT, LLM function-calling, and TTS. Sub-second turn-taking vs wiring Twilio + Deepgram + ElevenLabs by hand in a short take-home. |
| **FastAPI** | Async webhook handling (Vapi tool-calls are latency-sensitive), Pydantic v2 schemas shared by HTTP and tools, OpenAPI at `/docs` for reviewers. |
| **PostgreSQL on Render** | Relational store with durable disk. Data survives process restarts and deploys (unlike SQLite on Render’s ephemeral filesystem). `created_at` / `updated_at` stored as UTC. |
| **Python 3.12** | Pinned in `.python-version`. Render’s default 3.14 is newer than this stack was tested against. |

---

## Patient demographic data model

U.S. healthcare-style minimum dataset. Validation runs on every write (REST and Vapi).

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `first_name` | string | Yes | 1–50 chars; letters, spaces, hyphens, apostrophes |
| `last_name` | string | Yes | Same |
| `date_of_birth` | date | Yes | Real calendar date, **not in the future**, API format **MM/DD/YYYY** |
| `sex` | enum | Yes | `Male`, `Female`, `Other`, `Decline to Answer` |
| `phone_number` | string | Yes | U.S. 10-digit (stored as 10 digits; `+1` / punctuation accepted) |
| `email` | string | No | Valid email if provided |
| `address_line_1` | string | Yes | Street address |
| `address_line_2` | string | No | Apt / suite / unit |
| `city` | string | Yes | 1–100 characters |
| `state` | string | Yes | Valid 2-letter U.S. abbreviation (50 states + DC); stored uppercase |
| `zip_code` | string | Yes | `12345` or ZIP+4 `12345-6789` |
| `insurance_provider` | string | No | Payer name |
| `insurance_member_id` | string | No | Alphanumeric, 1–50 |
| `preferred_language` | string | No | Default **English** |
| `emergency_contact_name` | string | No | Full name |
| `emergency_contact_phone` | string | No | Valid U.S. 10-digit if provided |
| `patient_id` | UUID | Auto | Generated on insert |
| `created_at` | timestamp | Auto | UTC |
| `updated_at` | timestamp | Auto | UTC, set on update and soft-delete |
| `deleted_at` | timestamp | Auto | Null until soft-delete; list/get hide those rows |

Phone numbers are **not** unique in the database (households share lines). Returning-caller detection is `lookup_patient` / `GET /patients?phone_number=`.

---

## Vapi function tools

Server URL: `https://codecloud-voice-agent.onrender.com/vapi-webhook`

Tool failures still return **HTTP 200** with `{ "toolCallId", "error": "<single-line string>" }` so the model can speak the problem instead of going silent. Success uses `{ "toolCallId", "result": "..." }`.

| Tool | Arguments | Behavior |
| --- | --- | --- |
| `lookup_patient` | `phone_number` (required) | Finds a non-deleted patient. If found, returns name + `patient_id` and instructs the agent to offer an update. If not, continue registration. |
| `register_patient` | Full demographic payload (required fields mandatory) | Validates with `PatientIn`, inserts a UUID row, logs the payload, returns success text for *“You're all set, [First Name].”* |
| `update_patient` | `patient_id` (required) + any subset of fields | Partial update via `PatientUpdate`; omitted keys are unchanged. |

The agent must **confirm with the caller before** `register_patient` or `update_patient`. Invalid tool input (future DOB, 3-digit phone, bad state, etc.) comes back as a field-level error string so the agent re-prompts **that field only**.

End-of-call reports are logged to stdout (`vapi.call_ended` + transcript) for observability.

### System prompt (as configured on the assistant)

```
You are a warm U.S. healthcare intake coordinator. Speak naturally, not like a menu.

Collect required fields: first name, last name, date of birth (MM/DD/YYYY, not in the future),
sex (Male, Female, Other, or Decline to Answer), 10-digit U.S. phone, street address,
city, 2-letter state, ZIP (5-digit or ZIP+4).

Do not require optional fields. After required fields, ask:
"I can also collect your insurance information, emergency contact, and preferred language. Would you like to provide any of those?"

If a value is invalid, re-prompt only that field. Handle corrections and out-of-order answers.

When you have a phone number, call lookup_patient first. If a record exists, say:
"It looks like we already have a record for [First] [Last]. Would you like to update your information instead?"
and use update_patient if they say yes.

Before saving, read back every collected field and ask them to confirm or correct.
Only then call register_patient (or update_patient). If the tool returns an error, tell them
the record was not saved and offer to fix the listed fields. Never pretend a save succeeded.

On success say: "You're all set, [First Name]." then end the call.
If they want to start over, discard what you have and begin again.
Preferred language defaults to English if they skip it.
```

---

## REST API

Base: `https://codecloud-voice-agent.onrender.com`

Every JSON response uses:

```json
{ "data": {}, "error": null }
```

On failure, `data` is `null` and `error` is a string (field errors joined for 422). Status codes used: **200**, **201**, **400** (malformed JSON), **404**, **422** (validation), **500**.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/patients` | List active patients. Optional `?last_name=` (case-insensitive), `?date_of_birth=MM/DD/YYYY`, `?phone_number=` (normalized) |
| `GET` | `/patients/{patient_id}` | One patient by UUID |
| `POST` | `/patients` | Create; returns the row including `patient_id` (**201**) |
| `PUT` | `/patients/{patient_id}` | **Partial** update — send only fields to change |
| `DELETE` | `/patients/{patient_id}` | Soft-delete: sets `deleted_at`, does not drop the row |
| `GET` | `/health` | Liveness for Render |
| `POST` | `/vapi-webhook` | Vapi only (not the REST envelope) |

Interactive explorer: [/docs](https://codecloud-voice-agent.onrender.com/docs). For PUT, send e.g. `{ "first_name": "Jean" }` — do not send Swagger’s placeholder `"string"` on every field.

Creates and updates log the full saved payload to stdout (`patient.created` / `patient.updated`).

---

## Local development

Python 3.12 recommended (see `.python-version`).

```powershell
git clone https://github.com/anasahmed81103/CodeCLoudVoiceAgentBackend.git
cd CodeCLoudVoiceAgentBackend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

macOS / Linux: `python3 -m venv venv`, `source venv/bin/activate`, `cp .env.example .env`.

Then: http://127.0.0.1:8000/docs

Local default DB is SQLite (`./patients.db`) so you can run without Postgres. Production on Render uses PostgreSQL via `DATABASE_URL`.

### Environment variables

Copy `.env.example`. **Never commit secrets.**

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Local: no (defaults to `sqlite:///./patients.db`). Production: yes | Render Postgres internal URL. `postgres://` is rewritten to `postgresql://`. |
| `VAPI_WEBHOOK_SECRET` | Production: yes | Shared secret. Vapi must send `Authorization: Bearer <secret>` or `X-Vapi-Secret`. If empty, the webhook is unauthenticated (local only). |
| `PORT` | Render only | Set by Render. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`. The app does not read `PORT` itself. |

`.env` template:

```env
DATABASE_URL=sqlite:///./patients.db
VAPI_WEBHOOK_SECRET=
```

On Render, set `DATABASE_URL` to the Postgres connection string and `VAPI_WEBHOOK_SECRET` to the same value configured on the Vapi server credential. Health check path: `/health`.

---

## Design decisions, trade-offs, and limitations

**Vapi vs Twilio stack.** Vapi owns the phone number, STT, LLM, and TTS so the take-home can focus on conversation design, tool contracts, and a correct data/API layer. The cost is vendor lock-in and less control over raw audio pipelines.

**Postgres on Render vs SQLite in prod.** SQLite is used locally. Render’s container filesystem is ephemeral, so production uses Render PostgreSQL so Call 2 still sees Call 1 after deploys and restarts.

**Confirm-then-write.** Nothing is persisted until the caller confirms and a tool succeeds. A mid-call drop does not leave a half-saved patient. The trade-off: a hangup during read-back means they must call again.

**Tool errors are spoken, not HTTP 500.** Vapi requires HTTP 200 on `tool-calls` with an `error` string. A 500 from the webhook is silence on the phone.

**No unique constraint on phone.** Duplicate detection is application-level (`lookup_patient`) so two family members can share a number if needed.

**No REST authentication.** The brief did not require it. The live `/patients` API is reachable without a key. A real PHI system would need authn/z, TLS-only access, and log redaction. Webhook auth is the shared `VAPI_WEBHOOK_SECRET`.

**Render free tier cold start.** Sleep after idle adds 50+ seconds. Reviewers may need a second dial if the first attempt hits a sleeping instance.

**Validation is Pydantic-first.** Column types and nullability are enforced in SQL; enum/format rules live in Pydantic so the voice agent and REST share one contract.

**Soft-delete has no restore endpoint.** Deleted rows stay in the table with `deleted_at` set and are omitted from GET list/get.

**Optional multi-language / dashboard / tests** were out of scope for the core score. Spanish can be spoken if the caller asks; there is no separate locale pipeline. `preferred_language` is a stored field (default English).

---

## Repository layout

```
main.py              FastAPI app, models, validation, REST, Vapi webhook
requirements.txt     Pinned runtime deps (including psycopg2-binary)
.env.example         DATABASE_URL, VAPI_WEBHOOK_SECRET
.python-version      3.12.8 for Render
README.md            This file
```
