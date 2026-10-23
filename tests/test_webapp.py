"""Local web app: binds to localhost, groups dropped folders into clients, grades, and serves reports."""
import io
import shutil

import pytest

from src import webapp
from tests.harness import CLIENTS


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp, "RUNS", tmp_path / "runs")      # don't litter outputs/web during tests
    return webapp.app.test_client()


def _upload(paths_and_files, consent=False):
    data = {"files": [(io.BytesIO(f.read_bytes()), p) for p, f in paths_and_files],
            "paths": [p for p, _ in paths_and_files]}
    if consent:
        data["consent"] = "yes"
    return data


def test_binds_to_localhost_only():
    assert webapp.HOST == "127.0.0.1"


def test_grouping():
    g = webapp.group_uploads
    assert g(["a.pdf", "b.pdf"]) == {"Uploaded_Client": ["a.pdf", "b.pdf"]}
    assert g(["Smith/a.pdf", "Smith/b.pdf"]) == {"Smith": ["Smith/a.pdf", "Smith/b.pdf"]}
    assert g(["batch/Smith/a.pdf", "batch/Jones/b.pdf", "batch/README.pdf"]) == {
        "Smith": ["batch/Smith/a.pdf"], "Jones": ["batch/Jones/b.pdf"]}
    assert g(["Smith/a.pdf", "Jones/b.pdf"]) == {"Smith": ["Smith/a.pdf"], "Jones": ["Jones/b.pdf"]}


def test_get_grade_redirects_to_upload_page(client):
    resp = client.get("/grade")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/")


def test_drop_a_folder_of_clients(client):
    files = []
    for cid in ("C08", "C21"):
        folder = next(CLIENTS.glob(f"{cid}_*"))
        files += [(f"test_clients/{folder.name}/{p.name}", p) for p in folder.glob("*.pdf")]
    resp = client.post("/grade", data=_upload(files), content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    url = resp.get_json()["url"]
    assert url.endswith("/summary.html")
    page = client.get(url).get_data(as_text=True)
    assert "Kevin Marsh" in page and "Michelle Grady" in page and "Grade more clients" in page
    report = client.get(url.replace("summary.html", "clients/C08_Marsh_Kevin.html")).get_data(as_text=True)
    assert "aum.rollover_100k" in report and "000-00-0801" not in report
    assert client.get("/").get_data(as_text=True).count("Open ranking") == 1


def test_single_client_goes_straight_to_its_report(client):
    folder = next(CLIENTS.glob("C08_*"))
    resp = client.post("/grade", data=_upload([(p.name, p) for p in folder.glob("*.pdf")]),
                       content_type="multipart/form-data")
    assert "/clients/" in resp.get_json()["url"]


def test_real_looking_client_without_consent_is_not_graded(client):
    pdf = next(CLIENTS.glob("C08_*")) / "2025_Form_1040_and_Schedules.pdf"
    resp = client.post("/grade", data=_upload([("Smith/" + pdf.name, pdf)]), content_type="multipart/form-data")
    page = client.get(resp.get_json()["url"]).get_data(as_text=True)
    assert "Not graded" in page or "not graded" in page


def test_consent_checkbox_allows_grading(client):
    pdf = next(CLIENTS.glob("C08_*")) / "2025_Form_1040_and_Schedules.pdf"
    resp = client.post("/grade", data=_upload([("Smith/" + pdf.name, pdf)], consent=True),
                       content_type="multipart/form-data")
    page = client.get(resp.get_json()["url"]).get_data(as_text=True)
    assert "Not graded" not in page
