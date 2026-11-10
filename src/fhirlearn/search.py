"""Step 4: code search for type 2 diabetes Conditions, follow paging, count distinct patients."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import httpx

from fhirlearn.client import active_servers, FhirClient, entries, next_link

T2DM = "http://snomed.info/sct|44054006"


@dataclass
class SearchResult:
    resources: list[dict] = field(default_factory=list)
    pages: int = 0
    hit_cap: bool = False  # True if there was still a "next" link when we stopped


def fetch_all(client: FhirClient, resource_type: str, params: dict) -> SearchResult:
    """Follow next links up to the client's page cap, collecting only resources of the requested type."""
    res = SearchResult()
    last = None
    for bundle in client.iter_pages(resource_type, params):
        res.pages += 1
        last = bundle
        # skip OperationOutcome / _include'd entries: keep only the type we asked for
        res.resources += [r for r in entries(bundle) if r.get("resourceType") == resource_type]
    res.hit_cap = last is not None and next_link(last) is not None
    return res


def patient_id_from_ref(ref: str | None) -> str | None:
    """'Patient/123', 'https://x/fhir/Patient/123', 'Patient/123/_history/2' -> '123'. Non-Patient refs -> None."""
    if not ref:
        return None
    parts = ref.rstrip("/").split("/")
    if "_history" in parts:
        parts = parts[: parts.index("_history")]
    if len(parts) >= 2 and parts[-2] == "Patient":
        return parts[-1]
    return None


def subject_patient_ids(resources: list[dict]) -> list[str | None]:
    return [patient_id_from_ref((r.get("subject") or {}).get("reference")) for r in resources]


def main() -> None:
    for name in active_servers():
        with FhirClient(name) as c:
            print(f"\n=== {name.upper()}  GET {c.build_url('Condition', {'code': T2DM, '_count': 50})}")
            try:
                res = fetch_all(c, "Condition", {"code": T2DM})
            except httpx.HTTPError as e:
                print(f"FAILED: {type(e).__name__}: {e}")
                continue
            conds = res.resources
            pids = subject_patient_ids(conds)
            distinct = {p for p in pids if p}
            print(f"(network calls: {c.network_calls})")
            print(f"pages fetched: {res.pages}   stopped at page cap: {res.hit_cap}")
            print(f"Condition resources: {len(conds)}   distinct Condition ids: {len({x['id'] for x in conds})}")
            print(f"distinct patients (via subject): {len(distinct)}")
            print(f"conditions with no usable Patient subject: {sum(p is None for p in pids)}")

            ref_shapes = Counter(
                "missing" if not (r.get("subject") or {}).get("reference")
                else ("absolute" if "://" in r["subject"]["reference"] else "relative")
                for r in conds
            )
            print(f"subject reference styles: {dict(ref_shapes)}")
            per_patient = Counter(p for p in pids if p)
            print(f"most conditions for one patient: {per_patient.most_common(3)}")

            codings = Counter(
                (cd.get("system"), cd.get("code"), cd.get("display"))
                for r in conds for cd in (r.get("code") or {}).get("coding", [])
            )
            print("codings seen on the matched Conditions (system, code, display): count")
            for k, n in codings.most_common(10):
                print(f"  {k}: {n}")
            clin = Counter(
                ((r.get("clinicalStatus") or {}).get("coding") or [{}])[0].get("code") for r in conds
            )
            print(f"clinicalStatus: {dict(clin)}")


if __name__ == "__main__":
    main()
