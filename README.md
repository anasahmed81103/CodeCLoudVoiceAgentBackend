# CareCloud Patient Registration

Voice-based patient intake for a U.S. healthcare registration flow. This repository currently delivers the **persistent database** and **REST API**. The telephony / LLM voice agent will call this same service once those credentials are available.

When a caller finishes registration, the agent will `POST /patients`. A later call can retrieve that same record — data survives process restarts because it is stored in a SQLite file (or any SQLAlchemy URL you configure).

## Architecture

```
Phone call  →  Voice AI agent (later)  →  REST API  →  SQLite
                                      ↗
                         Reviewers / dashboard
```

| Layer | Responsibility |
| --- | --- |
| `app/routers/patients.py` | HTTP endpoints, status codes |
| `app/services/patients.py` | Create / read / update / soft-delete. Voice tools should call this module (or the HTTP API) rather than talking to SQLAlchemy directly |
| `app/schemas.py` + `app/validation.py` | Server-side demographic rules from the spec |
| `app/models.py` | Relational schema, check constraints, indexes |
| `app/seed.py` | Two demo patients inserted when the database is empty |

The voice agent is intentionally not in this pass. Keeping persistence behind a service layer means the LLM can be wired in later without changing the data model.

## Tech stack

| Choice | Why |
| --- | --- |
| **Python + FastAPI** | Typed request bodies, automatic OpenAPI docs, first-class validation errors — fits a small production API under time pressure |
| **Pydantic v2** | One validation path for HTTP and, later, LLM tool arguments |
| **SQLAlchemy 2.x + SQLite** | Real constraints and indexes, file-backed persistence, no extra infra. The same models can point at PostgreSQL by changing `DATABASE_URL` |
| **SQLite file (`patients.db`)** | Survives restarts; reviewers can inspect the file if needed |

## API

Envelope on every response:

```json
{ "data": { }, "error": null }
```

On failure `data` is `null` and `error` is `{ "message": "...", "details": [ { "field": "...", "message": "..." } ] }` (or `details: null`).

| Method | Path | Status | Notes |
| --- | --- | --- | --- |
| `GET` | `/patients` | 200 | Optional filters: `last_name`, `date_of_birth` (`MM/DD/YYYY`), `phone_number` |
| `GET` | `/patients/{id}` | 200 / 404 | UUID path parameter |
| `POST` | `/patients` | 201 / 422 | Full create; required fields validated server-side |
| `PUT` | `/patients/{id}` | 200 / 404 / 422 | Partial updates (`exclude_unset`) |
| `DELETE` | `/patients/{id}` | 200 / 404 | Soft-delete: sets `deleted_at`, does not remove the row |
| `GET` | `/health` | 200 | Liveness |

Soft-deleted records are excluded from list and get. A second delete or update returns 404.

Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Data model and validation

Required: `first_name`, `last_name`, `date_of_birth`, `sex`, `phone_number`, `address_line_1`, `city`, `state`, `zip_code`.

Optional: `email`, `address_line_2`, `insurance_provider`, `insurance_member_id`, `preferred_language` (default `English`), `emergency_contact_name`, `emergency_contact_phone`.

Auto: `patient_id` (UUID), `created_at`, `updated_at` (UTC).

| Field | Rule |
| --- | --- |
| Names | 1–50 letters; spaces, hyphens, apostrophes allowed (`O'Brien`, `Mary-Anne`) |
| `date_of_birth` | Real calendar date, `MM/DD/YYYY`, not in the future. Stored as `DATE`, returned as `MM/DD/YYYY` |
| `sex` | `Male`, `Female`, `Other`, `Decline to Answer` (aliases like `f` / `male` accepted, then stored canonically) |
| `phone_number` | Valid U.S. NANP 10-digit; `+1`, dashes, and parentheses accepted; **stored as 10 digits** |
| `email` | Valid email if provided |
| `state` | 2-letter USPS code, 50 states + DC; stored uppercase |
| `zip_code` | `12345` or `12345-6789` |
| `insurance_member_id` | Alphanumeric, 1–50 |

Phone numbers are **not** unique at the database level. Households share numbers; the voice agent will use `GET /patients?phone_number=` (or `find_by_phone`) to offer an update instead of a duplicate create.

## Setup

Requires Python 3.10+.

```powershell
cd project
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

macOS / Linux: `source venv/bin/activate` and `cp .env.example .env`.

On first start the app creates `patients.db` and seeds two records:

- Jane Doe — `11111111-1111-4111-8111-111111111111` — phone `4155552671`
- Carlos O'Brien — `22222222-2222-4222-8222-222222222222` — phone `2125550199`

```powershell
curl http://127.0.0.1:8000/patients
curl http://127.0.0.1:8000/patients/11111111-1111-4111-8111-111111111111
```

### Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./patients.db` | SQLAlchemy URL. Use Postgres in production if you want concurrent writes |
| `LOG_LEVEL` | `INFO` | Stdout logging. Create / update / soft-delete log the full patient payload (required for this assessment; treat as PHI in a real deployment) |

Do not put API keys in source. Voice-provider secrets will go in `.env` when that layer is added.

## Tests

```powershell
pytest -q
```

Coverage includes field validation, envelope shape, filters, partial PUT, and soft-delete behavior.

## Known limitations and trade-offs

- **Voice agent is not wired yet.** Telephony, STT/TTS, and the LLM prompt come next. The API and schema are built so that layer can POST confirmed data (and look up returning callers by phone).
- **SQLite** is the right default for a take-home (zero ops, restart-safe). It is a poor fit for high write concurrency; swap `DATABASE_URL` to PostgreSQL without changing application code.
- **No API authentication.** The brief did not require it. A production PHI store would need authn/z, TLS, and tighter log redaction.
- **ZIP CHECK constraint uses SQLite `GLOB`.** Revisit that constraint if you migrate to Postgres.
- **`preferred_language` cannot be cleared to empty**; explicit `null` on PUT resets it to `English`.
- Mid-call telephony drops, LLM retries, and conversation logging belong to the voice layer.

## Next: voice agent

The agent should:

1. Collect required demographics conversationally, then offer optional insurance / emergency contact / language.
2. Read back every field and wait for confirmation.
3. `POST /patients` (or `create_patient` in `app.services.patients`).
4. On success, speak a short confirmation and hang up. On API failure, tell the caller the record was not saved.
5. Bonus: `GET /patients?phone_number=` before create; if a hit, offer `PUT /patients/{id}` instead.
