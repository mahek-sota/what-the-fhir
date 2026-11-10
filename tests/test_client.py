"""Offline tests for the client: no network, a fake transport stands in for the server."""

import httpx

from fhirlearn.client import FhirClient, entries, next_link


def make_client(tmp_path, handler, **kw):
    return FhirClient(
        "test",
        "https://fhir.example/base",
        cache_dir=tmp_path,
        sleep_seconds=0,
        transport=httpx.MockTransport(handler),
        **kw,
    )


def test_get_is_cached(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        assert request.method == "GET"
        return httpx.Response(200, json={"resourceType": "CapabilityStatement"})

    c = make_client(tmp_path, handler)
    assert c.get("metadata")["resourceType"] == "CapabilityStatement"
    assert c.get("metadata")["resourceType"] == "CapabilityStatement"
    assert len(calls) == 1 and c.network_calls == 1

    # a fresh client reads from the same on-disk cache
    c2 = make_client(tmp_path, handler)
    c2.get("metadata")
    assert len(calls) == 1 and c2.network_calls == 0


def test_paging_follows_next_and_respects_cap(tmp_path):
    def handler(request):
        page = int(request.url.params.get("page", "0"))
        bundle = {
            "resourceType": "Bundle",
            "link": [{"relation": "next", "url": f"https://fhir.example/base/Patient?page={page + 1}"}],
            "entry": [{"resource": {"resourceType": "Patient", "id": str(page)}}],
        }
        return httpx.Response(200, json=bundle)

    c = make_client(tmp_path, handler, max_pages=3)
    pages = list(c.iter_pages("Patient"))
    assert len(pages) == 3
    assert [entries(b)[0]["id"] for b in pages] == ["0", "1", "2"]


def test_default_count_param(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.params.get("_count"))
        return httpx.Response(200, json={"resourceType": "Bundle"})

    c = make_client(tmp_path, handler)
    list(c.iter_pages("Patient"))
    assert seen == ["50"]


def test_next_link_absent():
    assert next_link({"link": [{"relation": "self", "url": "x"}]}) is None
