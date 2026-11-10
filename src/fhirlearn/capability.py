"""Step 2: GET /metadata (the CapabilityStatement) and summarize what each server supports."""

from __future__ import annotations

import httpx

from fhirlearn.client import SERVERS, FhirClient

FOCUS = ("Patient", "Condition", "Observation")


def summarize(cap: dict, focus: tuple[str, ...] = FOCUS) -> dict:
    """Pull FHIR version, software, and per-resource interactions + search params from a CapabilityStatement."""
    rest = next((r for r in cap.get("rest", []) if r.get("mode") == "server"), {})
    resources = {r["type"]: r for r in rest.get("resource", [])}
    out = {
        "fhirVersion": cap.get("fhirVersion"),
        "software": " ".join(
            filter(None, [cap.get("software", {}).get("name"), cap.get("software", {}).get("version")])
        ),
        "resource_type_count": len(resources),
        "resources": {},
    }
    for rtype in focus:
        r = resources.get(rtype)
        if r is None:
            out["resources"][rtype] = None
            continue
        out["resources"][rtype] = {
            "interactions": sorted(i["code"] for i in r.get("interaction", [])),
            "search_params": sorted(p["name"] for p in r.get("searchParam", [])),
        }
    return out


def main() -> None:
    for name in SERVERS:
        with FhirClient(name) as c:
            print(f"\n=== {name.upper()}  {c.base_url}")
            try:
                cap = c.get("metadata")
            except httpx.HTTPError as e:
                print(f"FAILED: {type(e).__name__}: {e}")
                continue
            s = summarize(cap)
            print(f"(network calls: {c.network_calls}; 0 means served from cache/)")
            print(f"FHIR version : {s['fhirVersion']}")
            print(f"Software     : {s['software'] or '(not stated)'}")
            print(f"Resource types supported: {s['resource_type_count']}")
            for rtype, info in s["resources"].items():
                if info is None:
                    print(f"  {rtype}: NOT SUPPORTED")
                    continue
                print(f"  {rtype}")
                print(f"    interactions : {', '.join(info['interactions'])}")
                print(f"    search params ({len(info['search_params'])}): {', '.join(info['search_params'])}")


if __name__ == "__main__":
    main()
