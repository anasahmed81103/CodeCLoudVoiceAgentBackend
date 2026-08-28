"""API tests for the patient REST contract."""

from copy import deepcopy

VALID_PATIENT = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "date_of_birth": "12/10/1815",
    "sex": "Female",
    "phone_number": "2024567890",
    "email": "ada@example.com",
    "address_line_1": "1600 Pennsylvania Avenue NW",
    "address_line_2": "Apt 1",
    "city": "Washington",
    "state": "DC",
    "zip_code": "20001",
    "insurance_provider": "Aetna",
    "insurance_member_id": "AET12345",
    "preferred_language": "English",
    "emergency_contact_name": "William King",
    "emergency_contact_phone": "2024567891",
}


def _create(client, **overrides):
    payload = deepcopy(VALID_PATIENT)
    payload.update(overrides)
    return client.post("/patients", json=payload)


def _assert_envelope(response):
    body = response.json()
    assert "data" in body
    assert "error" in body
    return body


def test_create_patient_returns_201_and_envelope(client):
    response = _create(client)
    body = _assert_envelope(response)
    assert response.status_code == 201
    assert body["error"] is None
    data = body["data"]
    assert data["first_name"] == "Ada"
    assert data["last_name"] == "Lovelace"
    assert data["date_of_birth"] == "12/10/1815"
    assert data["phone_number"] == "2024567890"
    assert data["state"] == "DC"
    assert data["patient_id"]
    assert data["created_at"].endswith("Z")
    assert data["deleted_at"] is None


def test_create_normalizes_phone_state_and_sex(client):
    response = _create(
        client,
        phone_number="+1 (202) 456-7890",
        state="dc",
        sex="female",
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["phone_number"] == "2024567890"
    assert data["state"] == "DC"
    assert data["sex"] == "Female"


def test_create_allows_hyphen_and_apostrophe_names(client):
    response = _create(client, first_name="Mary-Anne", last_name="O'Brien")
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["first_name"] == "Mary-Anne"
    assert data["last_name"] == "O'Brien"


def test_create_defaults_preferred_language(client):
    payload = deepcopy(VALID_PATIENT)
    del payload["preferred_language"]
    response = client.post("/patients", json=payload)
    assert response.status_code == 201
    assert response.json()["data"]["preferred_language"] == "English"


def test_create_rejects_invalid_inputs(client):
    cases = [
        {"first_name": "Ada3"},
        {"last_name": ""},
        {"date_of_birth": "13/40/1990"},
        {"date_of_birth": "01/01/2999"},
        {"date_of_birth": "1990-01-01"},
        {"sex": "Unknown"},
        {"phone_number": "123"},
        {"phone_number": "0123456789"},
        {"email": "not-an-email"},
        {"state": "California"},
        {"zip_code": "1234"},
        {"zip_code": "123456"},
        {"insurance_member_id": "ID-WITH-DASH"},
        {"emergency_contact_phone": "555"},
        {"city": ""},
    ]
    for override in cases:
        response = _create(client, **override)
        assert response.status_code == 422, override
        body = _assert_envelope(response)
        assert body["data"] is None
        assert body["error"]["message"]
        assert body["error"]["details"]


def test_create_accepts_zip_plus_four(client):
    response = _create(client, zip_code="20001-1234")
    assert response.status_code == 201
    assert response.json()["data"]["zip_code"] == "20001-1234"


def test_create_omits_optional_fields(client):
    payload = {
        "first_name": "Lin",
        "last_name": "Wang",
        "date_of_birth": "03/22/1992",
        "sex": "Other",
        "phone_number": "4155550198",
        "address_line_1": "1 Market Street",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94105",
    }
    response = client.post("/patients", json=payload)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["email"] is None
    assert data["insurance_provider"] is None
    assert data["emergency_contact_name"] is None


def test_get_patient_and_404(client):
    created = _create(client).json()["data"]
    response = client.get(f"/patients/{created['patient_id']}")
    assert response.status_code == 200
    assert response.json()["data"]["last_name"] == "Lovelace"

    missing = client.get("/patients/99999999-9999-4999-8999-999999999999")
    assert missing.status_code == 404
    body = _assert_envelope(missing)
    assert body["data"] is None
    assert body["error"]["message"] == "Patient not found"


def test_get_invalid_uuid_is_422(client):
    response = client.get("/patients/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["data"] is None


def test_list_patients_and_filters(client):
    _create(client)
    _create(
        client,
        first_name="Grace",
        last_name="Hopper",
        date_of_birth="12/09/1906",
        phone_number="3124567890",
        email="grace@example.com",
    )

    all_patients = client.get("/patients")
    assert all_patients.status_code == 200
    assert len(all_patients.json()["data"]) == 2

    by_name = client.get("/patients", params={"last_name": "hopper"})
    assert len(by_name.json()["data"]) == 1
    assert by_name.json()["data"][0]["first_name"] == "Grace"

    by_dob = client.get("/patients", params={"date_of_birth": "12/10/1815"})
    assert len(by_dob.json()["data"]) == 1
    assert by_dob.json()["data"][0]["last_name"] == "Lovelace"

    by_phone = client.get("/patients", params={"phone_number": "(312) 456-7890"})
    assert len(by_phone.json()["data"]) == 1
    assert by_phone.json()["data"][0]["first_name"] == "Grace"


def test_list_rejects_invalid_filter_values(client):
    response = client.get("/patients", params={"phone_number": "123"})
    assert response.status_code == 422
    assert response.json()["data"] is None

    response = client.get("/patients", params={"date_of_birth": "2020-01-01"})
    assert response.status_code == 422


def test_partial_update(client):
    created = _create(client).json()["data"]
    response = client.put(
        f"/patients/{created['patient_id']}",
        json={"city": "Arlington", "state": "VA", "email": None},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["city"] == "Arlington"
    assert data["state"] == "VA"
    assert data["email"] is None
    assert data["first_name"] == "Ada"
    assert data["updated_at"] >= created["updated_at"]


def test_update_validates_fields(client):
    created = _create(client).json()["data"]
    response = client.put(
        f"/patients/{created['patient_id']}",
        json={"date_of_birth": "01/01/2999"},
    )
    assert response.status_code == 422


def test_soft_delete_hides_record(client):
    created = _create(client).json()["data"]
    patient_id = created["patient_id"]

    deleted = client.delete(f"/patients/{patient_id}")
    assert deleted.status_code == 200
    body = deleted.json()["data"]
    assert body["deleted_at"] is not None

    assert client.get(f"/patients/{patient_id}").status_code == 404
    assert client.get("/patients").json()["data"] == []
    assert client.put(f"/patients/{patient_id}", json={"city": "Boston"}).status_code == 404
    assert client.delete(f"/patients/{patient_id}").status_code == 404


def test_invalid_json_is_400(client):
    response = client.post(
        "/patients",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    body = _assert_envelope(response)
    assert body["data"] is None
    assert "JSON" in body["error"]["message"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}, "error": None}
