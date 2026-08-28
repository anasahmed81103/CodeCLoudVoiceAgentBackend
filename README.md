# CareCloud Patient Registration

Voice intake agent (Vapi) + FastAPI + SQLite. Callers register a patient by phone; records persist and are queryable over REST.

```
Caller → Vapi (LLM + telephony) → POST /vapi-webhook → SQLite
                                 ↗
                    Reviewers → REST API
```

**Why this stack:** FastAPI for a small typed JSON API. SQLite for zero-ops persistence (use a Render disk, or swap `DATABASE_URL` to Render Postgres). Vapi for the number, STT/TTS, and LLM so we can focus on tools and validation.

## Setup (local)

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Docs: http://127.0.0.1:8000/docs

## Env

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./patients.db` | SQLite file, or `postgresql://...` on Render |
| `VAPI_WEBHOOK_SECRET` | empty | Shared secret. If set, Vapi must send `Authorization: Bearer <secret>` or `X-Vapi-Secret` |

Do not hardcode API keys.

## Render

Start command:

```
uvicorn main:app --host 0.0.0.0 --port $PORT
```

**SQLite on Render is wiped on every deploy unless you attach a persistent disk.** Mount a disk at `/data` and set:

```
DATABASE_URL=sqlite:////data/patients.db
```

Otherwise use Render Postgres and paste its internal URL into `DATABASE_URL` (add `psycopg2-binary` to `requirements.txt` if you go that route). Without one of those, Call 2 will not see Call 1.

Health check path: `/health`

After deploy, Vapi Server URL:

```
https://<your-service>.onrender.com/vapi-webhook
```

## API

Every REST response: `{ "data": ..., "error": null }`

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/patients` | Filters: `?last_name=` `?date_of_birth=` `?phone_number=` |
| GET | `/patients/{id}` | UUID |
| POST | `/patients` | 201; server-side validation |
| PUT | `/patients/{id}` | Partial update |
| DELETE | `/patients/{id}` | Soft-delete (`deleted_at`) |
| POST | `/vapi-webhook` | Vapi tools + end-of-call log (not the REST envelope) |

Status codes: 200, 201, 400, 404, 422, 500.

Seeded on first empty DB:

- Jane Doe `11111111-1111-4111-8111-111111111111` phone `4155552671`
- Carlos O'Brien `22222222-2222-4222-8222-222222222222` phone `2125550199`

## Vapi assistant

Paste this as the **system prompt**. Tools must hit `/vapi-webhook`.

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

Custom tools (all `server.url` = your `/vapi-webhook`):

1. `lookup_patient` — `phone_number` (string, required)
2. `register_patient` — required demographics + optional email, address_line_2, insurance_*, preferred_language, emergency_contact_*
3. `update_patient` — `patient_id` (required) plus any fields to change

`date_of_birth` must be `MM/DD/YYYY`. `sex` must be one of the four enum values. Phones: 10 digits.

## Limitations

- Deploy must use a Render disk or Postgres or Call 2 loses data.
- No patient-API auth (not required for the take-home).
- Mid-call drop: nothing is saved until the caller confirms and a tool writes. That is intentional.
- If the DB write fails, the webhook returns an `error` string so Vapi can speak it (not silence).
