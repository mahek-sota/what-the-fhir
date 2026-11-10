from fhirlearn.capability import summarize

CAP = {
    "resourceType": "CapabilityStatement",
    "fhirVersion": "4.0.1",
    "software": {"name": "Demo", "version": "1.0"},
    "rest": [{
        "mode": "server",
        "resource": [
            {"type": "Patient", "interaction": [{"code": "read"}, {"code": "search-type"}],
             "searchParam": [{"name": "gender", "type": "token"}, {"name": "birthdate", "type": "date"}]},
            {"type": "Observation", "interaction": [{"code": "read"}]},
        ],
    }],
}


def test_summarize():
    s = summarize(CAP)
    assert s["fhirVersion"] == "4.0.1"
    assert s["software"] == "Demo 1.0"
    assert s["resource_type_count"] == 2
    assert s["resources"]["Patient"]["search_params"] == ["birthdate", "gender"]
    assert s["resources"]["Observation"]["search_params"] == []
    assert s["resources"]["Condition"] is None
