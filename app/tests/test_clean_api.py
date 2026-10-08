"""HTTP-level tests for the data-cleaning endpoints. No database needed."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def upload(client, content, filename="data.csv", options=None):
    data = {"file": (io.BytesIO(content), filename)}
    if options is not None:
        data["options"] = json.dumps(options)
    return client.post("/api/clean", data=data, content_type="multipart/form-data")


def test_sample_endpoint_serves_a_csv(client):
    response = client.get("/api/clean/sample")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.get_data(as_text=True).startswith(" Customer Name ,")


def test_cleaning_the_sample_round_trips(client):
    sample = client.get("/api/clean/sample").data
    response = upload(client, sample, "messy_customers_sample.csv")
    assert response.status_code == 200
    body = response.get_json()
    assert body["summary"]["rows_in"] == 13
    assert body["summary"]["rows_out"] == 10
    assert body["columns"][0] == "customer_name"
    assert body["filename"] == "messy_customers_sample.csv"
    assert body["cleaned_filename"] == "messy_customers_sample_cleaned.csv"
    assert body["cleaned_csv"].startswith("customer_name,e_mail,")
    assert body["steps"] and body["preview"]["rows"]


def test_options_are_applied(client):
    response = upload(client, b"name\n JOHN \n", options={"trim_whitespace": False, "standardize_text": False})
    assert response.status_code == 200
    assert response.get_json()["summary"]["cells_changed"] == 0


def test_invalid_options_are_rejected(client):
    response = upload(client, b"a\n1\n", options={"not_a_real_option": True})
    assert response.status_code == 422
    assert "unknown option" in response.get_json()["error"]


def test_missing_file_is_a_400(client):
    response = client.post("/api/clean", data={}, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_unparseable_csv_is_a_422_with_a_readable_message(client):
    response = upload(client, b"a,b\n1,2,3\n")
    assert response.status_code == 422
    assert "could not parse" in response.get_json()["error"]


def test_empty_file_is_a_422(client):
    assert upload(client, b"").status_code == 422


def test_oversized_upload_gets_a_json_413(client):
    too_big = b"a,b\n" + b"1,2\n" * 700_000  # about 2.8 MB, over the 2 MB limit
    response = upload(client, too_big)
    assert response.status_code == 413
    assert "too large" in response.get_json()["error"]


def test_uploaded_filename_is_sanitized(client):
    response = upload(client, b"a\n1\n", filename="../../etc/My Data.csv")
    body = response.get_json()
    assert "/" not in body["filename"] and ".." not in body["filename"]
    assert body["cleaned_filename"].endswith("_cleaned.csv")


def test_windows_1252_files_are_accepted(client):
    response = upload(client, "name\nJosé\n".encode("cp1252"))
    assert response.status_code == 200
    assert "José" in response.get_json()["cleaned_csv"]


def test_clean_only_accepts_post(client):
    assert client.get("/api/clean").status_code == 405


def test_index_lists_the_new_endpoints(client):
    endpoints = client.get("/").get_json()["endpoints"]
    assert "/api/clean" in endpoints
    assert "/api/clean/sample" in endpoints
