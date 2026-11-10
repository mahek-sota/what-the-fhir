"""Step 3: fetch one page of Patients, look at the Bundle, flatten to a DataFrame."""

from __future__ import annotations

from collections import Counter

import httpx
import pandas as pd

from fhirlearn.client import PAGE_SIZE, active_servers, FhirClient, entries, next_link


def has_name(patient: dict) -> bool:
    """True if any HumanName has a family, a given, or free-text name."""
    for n in patient.get("name") or []:
        if n.get("family") or any(g for g in n.get("given") or []) or n.get("text"):
            return True
    return False


def patients_to_df(patients: list[dict]) -> pd.DataFrame:
    rows = [
        {
            "id": p.get("id"),
            "gender": p.get("gender"),
            "birthDate": p.get("birthDate"),
            "has_name": has_name(p),
        }
        for p in patients
    ]
    return pd.DataFrame(rows, columns=["id", "gender", "birthDate", "has_name"])


def bundle_skeleton(bundle: dict) -> dict:
    """The Bundle with entries collapsed, so you can see its shape."""
    first = bundle.get("entry", [{}])[0]
    return {
        "resourceType": bundle.get("resourceType"),
        "type": bundle.get("type"),
        "total": bundle.get("total", "(not provided)"),
        "link": [{"relation": l["relation"], "url": l["url"][:90] + ("…" if len(l["url"]) > 90 else "")}
                 for l in bundle.get("link", [])],
        "entry": f"[{len(bundle.get('entry', []))} items, each like: "
                 f"{{fullUrl: {first.get('fullUrl')!r}, resource: {{…Patient…}}, search: {first.get('search')}}}]",
    }


def fetch_patient_page(client: FhirClient) -> dict:
    return client.get("Patient", {"_count": PAGE_SIZE})


def main() -> None:
    for name in active_servers():
        with FhirClient(name) as c:
            print(f"\n=== {name.upper()}  GET {c.build_url('Patient', {'_count': PAGE_SIZE})}")
            try:
                bundle = fetch_patient_page(c)
            except httpx.HTTPError as e:
                print(f"FAILED: {type(e).__name__}: {e}")
                continue
            print(f"(network calls: {c.network_calls})")

            print("\n-- Bundle skeleton")
            for k, v in bundle_skeleton(bundle).items():
                print(f"  {k}: {v}")
            print(f"  next link present: {next_link(bundle) is not None}")

            pats = entries(bundle)
            field_counts = Counter(k for p in pats for k in p)
            print(f"\n-- Top-level Patient fields across {len(pats)} patients (field: how many have it)")
            for k, n in field_counts.most_common():
                print(f"  {k:<22} {n}")

            df = patients_to_df(pats)
            print("\n-- DataFrame (first 10 rows)")
            print(df.head(10).to_string(index=False))
            print("\n-- Quick stats")
            print(f"  rows: {len(df)}")
            print(f"  gender: {df['gender'].value_counts(dropna=False).to_dict()}")
            print(f"  has_name: {df['has_name'].value_counts().to_dict()}")
            print(f"  missing birthDate: {df['birthDate'].isna().sum()}")


if __name__ == "__main__":
    main()
