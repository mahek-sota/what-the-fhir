import httpx

from fhirlearn.client import FhirClient
from fhirlearn.search import fetch_all, patient_id_from_ref, subject_patient_ids


def test_patient_id_from_ref():
    assert patient_id_from_ref("Patient/123") == "123"
    assert patient_id_from_ref("https://x.org/fhir/Patient/abc-1") == "abc-1"
    assert patient_id_from_ref("Patient/123/_history/2") == "123"
    assert patient_id_from_ref("Group/9") is None
    assert patient_id_from_ref("urn:uuid:1234") is None
    assert patient_id_from_ref(None) is None
    assert patient_id_from_ref("") is None


def test_subject_patient_ids_missing_subject():
    assert subject_patient_ids([{"subject": {"reference": "Patient/1"}}, {}, {"subject": {}}]) == ["1", None, None]


def test_fetch_all_filters_type_and_reports_cap(tmp_path):
    def handler(request):
        page = int(request.url.params.get("page", "0"))
        return httpx.Response(200, json={
            "resourceType": "Bundle",
            "link": [{"relation": "next", "url": f"https://f.example/Condition?page={page + 1}"}],
            "entry": [
                {"resource": {"resourceType": "Condition", "id": f"c{page}"}},
                {"resource": {"resourceType": "OperationOutcome"}},
            ],
        })

    c = FhirClient("t", "https://f.example", cache_dir=tmp_path, sleep_seconds=0,
                   transport=httpx.MockTransport(handler), max_pages=2)
    res = fetch_all(c, "Condition", {"code": "x"})
    assert [r["id"] for r in res.resources] == ["c0", "c1"]
    assert res.pages == 2 and res.hit_cap
