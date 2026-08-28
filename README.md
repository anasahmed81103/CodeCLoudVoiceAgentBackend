# CareCloud Patient Registration

Voice agent (later) + REST API + SQLite. This pass is the API and database. The phone/LLM layer will call these endpoints after the caller confirms their info.

```
Caller → Voice AI (later) → REST API (this repo) → SQLite (patients.db)
```

**Why this stack:** FastAPI for a small typed JSON API, SQLite so data survives restarts with no extra services. Swap `DATABASE_URL` to Postgres later if needed.

## Setup

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
| `DATABASE_URL` | `sqlite:///./patients.db` | Database. Do not hardcode secrets; voice API keys will go here later. |

## API

Every response: `{ "data": ..., "error": null }`

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/patients` | Filters: `?last_name=` `?date_of_birth=` `?phone_number=` |
| GET | `/patients/{id}` | UUID |
| POST | `/patients` | 201; validates all fields server-side |
| PUT | `/patients/{id}` | Partial update |
| DELETE | `/patients/{id}` | Soft-delete (`deleted_at`); no hard delete |

Status codes: 200, 201, 400, 404, 422, 500.

Seeded on first run:

- Jane Doe `11111111-1111-4111-8111-111111111111` phone `4155552671`
- Carlos O'Brien `22222222-2222-4222-8222-222222222222` phone `2125550199`

## Validation (also enforced in the DB via types/nullability)

Required: first_name, last_name, date_of_birth (MM/DD/YYYY, not future), sex (Male/Female/Other/Decline to Answer), phone_number (US 10-digit), address_line_1, city, state (2-letter), zip_code (12345 or ZIP+4).

Optional: email, address_line_2, insurance_*, preferred_language (default English), emergency_contact_*.

Auto: patient_id (UUID), created_at / updated_at (UTC).

Creates/updates log the saved payload to stdout.

## Limitations

- Voice number / LLM not wired yet. Agent should `POST /patients` on confirm, and `GET /patients?phone_number=` to detect a returning caller (bonus).
- SQLite is simple, not for high concurrency.
- No auth (not required for the take-home; PHI would need it in production).
