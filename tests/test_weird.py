from datetime import date

import httpx

from fhirlearn.client import FhirClient
from fhirlearn.weird import birthdate_oddity, missing_patients

TODAY = date(2026, 11, 10)


def test_birthdate_oddity():
    assert birthdate_oddity("2340-12-09", TODAY) == "future"
    assert birthdate_oddity("0000-12-24", TODAY) == "before 1900"
    assert birthdate_oddity("1899", TODAY) == "before 1900"
    assert birthdate_oddity("1980-05", TODAY) is None
    assert birthdate_oddity(None, TODAY) is None


def test_missing_patients_batches_ids(tmp_path):
    existing = {"a", "c"}
    seen = []

    def handler(request):
        ids = request.url.params["_id"].split(",")
        seen.append(ids)
        return httpx.Response(200, json={"resourceType": "Bundle", "entry": [
            {"resource": {"resourceType": "Patient", "id": i}} for i in ids if i in existing]})

    c = FhirClient("t", "https://f.example", cache_dir=tmp_path, sleep_seconds=0, transport=httpx.MockTransport(handler))
    missing, checked = missing_patients(c, ["a", "b", "c"])
    assert missing == {"b"} and checked == 3 and seen == [["a", "b", "c"]]
