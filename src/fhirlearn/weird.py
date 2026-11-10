"""Step 7: hunt for odd data on HAPI.

Two sources:
1. Scan what we already fetched in steps 3-5 (from cache).
2. A few targeted, one-page searches that let the server find oddities for us
   (:missing modifier, birthdate prefixes), plus batched _id lookups to check
   whether referenced patients exist.
"""

from __future__ import annotations

import json
from datetime import date

from fhirlearn.client import PAGE_SIZE, FhirClient, entries
from fhirlearn.labs import HBA1C
from fhirlearn.patients import has_name
from fhirlearn.search import T2DM, fetch_all, patient_id_from_ref

MAX_ID_LOOKUP_REQUESTS = 20


def birthdate_oddity(bd: str | None, today: date) -> str | None:
    if not bd:
        return None
    year = int(bd[:4])
    if bd[:10] > today.isoformat():
        return "future"
    if year < 1900:
        return "before 1900"
    return None


def missing_patients(client: FhirClient, ids: list[str]) -> tuple[set[str], int]:
    """Look up ids 50 at a time with Patient?_id=a,b,c. Returns (ids not found, how many ids were checked)."""
    missing, checked = set(), 0
    batches = [ids[i:i + PAGE_SIZE] for i in range(0, len(ids), PAGE_SIZE)][:MAX_ID_LOOKUP_REQUESTS]
    for batch in batches:
        found = {p["id"] for p in entries(client.get("Patient", {"_id": ",".join(batch), "_count": PAGE_SIZE}))}
        missing |= set(batch) - found
        checked += len(batch)
    return missing, checked


def short(resource: dict, keys: tuple[str, ...]) -> str:
    return json.dumps({k: resource.get(k) for k in keys if k in resource}, ensure_ascii=False)[:300]


def main() -> None:
    today = date.today()
    c = FhirClient("hapi")

    patients = entries(c.get("Patient", {"_count": PAGE_SIZE}))
    conds = fetch_all(c, "Condition", {"code": T2DM}).resources
    obs = fetch_all(c, "Observation", {"code": HBA1C}).resources
    print(f"from cache: {len(patients)} patients, {len(conds)} conditions, {len(obs)} observations "
          f"(network calls so far: {c.network_calls})")

    print("\n## A. Targeted one-page searches")
    probes = {
        "Patient with no name (name:missing=true)": ("Patient", {"name:missing": "true"}),
        f"Patient born in the future (birthdate=gt{today})": ("Patient", {"birthdate": f"gt{today}"}),
        "Patient born before 1900 (birthdate=lt1900-01-01)": ("Patient", {"birthdate": "lt1900-01-01"}),
        "Condition with no code (code:missing=true)": ("Condition", {"code:missing": "true"}),
        "Condition with no subject (subject:missing=true)": ("Condition", {"subject:missing": "true"}),
    }
    probe_results = {}
    for label, (rtype, params) in probes.items():
        found = [r for r in entries(c.get(rtype, {**params, "_count": PAGE_SIZE})) if r.get("resourceType") == rtype]
        probe_results[label] = found
        print(f"\n### {label}: {len(found)} on first page")
        for r in found[:8]:
            print("  ", r["id"], short(r, ("name", "birthDate", "gender", "code", "subject", "clinicalStatus")))

    print("\n## B. Scan of fetched data")
    for p in patients:
        odd = birthdate_oddity(p.get("birthDate"), today)
        if odd or not has_name(p):
            print("  patient", p["id"], odd or "no usable name", p.get("birthDate"))
    for r in conds:
        if not (r.get("code") or {}).get("coding"):
            print("  condition with no coding", r["id"])

    print("\n## C. Do referenced patients exist?")
    refs: dict[str, list[str]] = {}
    for kind, res in (("Condition", conds), ("Observation", obs)):
        for r in res:
            pid = patient_id_from_ref((r.get("subject") or {}).get("reference"))
            if pid:
                refs.setdefault(pid, []).append(f"{kind}/{r['id']}")
    # condition subjects first, so they are always checked even if we hit the request cap
    ordered = sorted(refs, key=lambda pid: not any(x.startswith("Condition/") for x in refs[pid]))
    missing, checked = missing_patients(c, ordered)
    print(f"referenced patients: {len(refs)}, checked: {checked}, not found: {len(missing)}")
    for pid in sorted(missing)[:25]:
        print(f"  Patient/{pid}  <- {refs[pid][:3]}{' …' if len(refs[pid]) > 3 else ''}")
    print(f"\n(total network calls this run: {c.network_calls})")
    c.close()


if __name__ == "__main__":
    main()
