"""Build article_assets/report.html: a self-contained, interactive report.

Everything comes from cache/ (0 network calls). The template lives next to this file;
the data is injected as one JSON blob, so the page needs no backend.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from fhirlearn.capability import summarize as summarize_capability
from fhirlearn.client import DEFAULT_CACHE_DIR, PAGE_SIZE, SERVERS, FhirClient, entries, next_link
from fhirlearn.labs import HBA1C, THRESHOLD_PCT, observations_to_df, summarize as summarize_labs, unit_label
from fhirlearn.patients import has_name
from fhirlearn.search import T2DM, fetch_all, subject_patient_ids

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = Path(__file__).with_name("report_template.html")
OUT = ROOT / "article_assets" / "report.html"
PLACEHOLDER = "/*__REPORT_DATA__*/null"


class CacheOnlyClient(FhirClient):
    """A FhirClient that refuses to touch the network: the report must be built from cache alone."""

    def get(self, path_or_url, params=None):
        url = self.build_url(path_or_url, params)
        if not self._cache_path(url).exists():
            raise RuntimeError(f"not in cache (run the step modules first): {url}")
        return super().get(path_or_url, params)


def strip_narrative(resource: dict) -> dict:
    """Drop the generated XHTML 'text' block: it is long and just repeats the data."""
    return {k: v for k, v in resource.items() if k != "text"}


def request_log() -> list[dict]:
    rows = []
    for name in SERVERS:
        base = SERVERS[name]
        for f in (DEFAULT_CACHE_DIR / name).glob("*.json"):
            raw = json.loads(f.read_text())
            body, url = raw["body"], raw["url"]
            path = url[len(base):] if url.startswith(base) else url
            rows.append({
                "server": name,
                "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%H:%M:%S"),
                "ts": f.stat().st_mtime,
                "url": url,
                "path": path or "/",
                "resourceType": body.get("resourceType"),
                "entries": len(body.get("entry", [])) if body.get("resourceType") == "Bundle" else None,
                "hasNext": next_link(body) is not None,
                "kb": round(f.stat().st_size / 1024, 1),
            })
    rows.sort(key=lambda r: r["ts"])
    for i, r in enumerate(rows, 1):
        r["n"] = i
        del r["ts"]
    return rows


def server_data(name: str) -> dict:
    c = CacheOnlyClient(name)
    cap = summarize_capability(c.get("metadata"))
    patient_bundle = c.get("Patient", {"_count": PAGE_SIZE})
    patients = entries(patient_bundle)
    conds = fetch_all(c, "Condition", {"code": T2DM})
    obs = fetch_all(c, "Observation", {"code": HBA1C})
    df = observations_to_df(obs.resources)
    lab = summarize_labs(df)

    usable = df[df["pct"].notna() & df["patient_id"].notna()]
    per_patient_max = usable.groupby("patient_id")["pct"].max().round(2).tolist()

    displays = Counter()
    systems = Counter()
    for r in conds.resources:
        for cd in (r.get("code") or {}).get("coding", []):
            systems[cd.get("system")] += 1
            if cd.get("code") == "44054006":
                displays[cd.get("display") or "(no display)"] += 1

    excluded = df[df["status"] != "ok"][["id", "patient_id", "raw_value", "unit", "status"]]
    return {
        "name": name,
        "base": SERVERS[name],
        "capability": cap,
        "patients": {
            "rows": [
                {"id": p.get("id"), "gender": p.get("gender"), "birthDate": p.get("birthDate"),
                 "has_name": has_name(p), "fields": len(p)}
                for p in patients
            ],
            "fieldCounts": Counter(k for p in patients for k in p).most_common(),
            "example": strip_narrative(patients[0]),
        },
        "bundle": {
            "resourceType": patient_bundle.get("resourceType"),
            "type": patient_bundle.get("type"),
            "link": patient_bundle.get("link", []),
            "entry": [
                {**{k: v for k, v in e.items() if k != "resource"}, "resource": strip_narrative(e["resource"])}
                for e in patient_bundle.get("entry", [])[:2]
            ],
            "entryCount": len(patient_bundle.get("entry", [])),
        },
        "diabetes": {
            "pages": conds.pages,
            "capped": conds.hit_cap,
            "conditions": len(conds.resources),
            "patients": len({p for p in subject_patient_ids(conds.resources) if p}),
            "displays": displays.most_common(),
            "systems": systems.most_common(),
        },
        "hba1c": {
            "pages": obs.pages,
            "capped": obs.hit_cap,
            "observations": lab["observations"],
            "patients": lab["patients"],
            "patientsHigh": lab["patients_ge_6_5"],
            "readings": usable["pct"].round(2).tolist(),
            "perPatientMax": per_patient_max,
            "units": Counter(unit_label(o) for o in obs.resources).most_common(),
            "status": Counter(df["status"]).most_common(),
            "excluded": excluded.to_dict(orient="records"),
        },
    }


def weird_examples() -> list[dict]:
    c = CacheOnlyClient("hapi")
    today = "2026-11-10"
    pools = {
        "future": entries(c.get("Patient", {"birthdate": f"gt{today}", "_count": PAGE_SIZE})),
        "old": entries(c.get("Patient", {"birthdate": "lt1900-01-01", "_count": PAGE_SIZE})),
        "nosubject": entries(c.get("Condition", {"subject:missing": "true", "_count": PAGE_SIZE})),
        "patients": entries(c.get("Patient", {"_count": PAGE_SIZE})),
        "hba1c": fetch_all(c, "Observation", {"code": HBA1C}).resources,
    }

    def find(pool: str, rid: str) -> dict:
        return strip_narrative(next(r for r in pools[pool] if r.get("id") == rid))

    return [
        {"title": "A Klingon born in 2340", "ref": "Patient/470809",
         "query": f"Patient?birthdate=gt{today}",
         "why": "The server accepted a birth date 314 years in the future. FHIR's date type checks the format, not whether the date makes sense.",
         "resource": find("future", "470809")},
        {"title": "Born on Christmas Eve, year zero", "ref": "Patient/470065",
         "query": "Patient?birthdate=lt1900-01-01",
         "why": "The FHIR date pattern does not allow the year 0000, because the calendar has no year zero. HAPI stored it anyway, and someone came back to edit the record (versionId 2).",
         "resource": find("old", "470065")},
        {"title": "A Condition with nothing in it", "ref": "Condition/23936",
         "query": "Condition?subject:missing=true",
         "why": "No code, no patient, no status. R4 says Condition.subject is required, so this should not be valid.",
         "resource": find("nosubject", "23936")},
        {"title": "An HbA1c of 112%", "ref": "Observation/81833",
         "query": "Observation?code=http://loinc.org|4548-4",
         "why": "HbA1c is the share of hemoglobin with sugar attached, so it can't exceed 100%. A real 12% is already very high. The unit is properly UCUM-coded, which makes it look legitimate.",
         "resource": find("hba1c", "81833")},
        {"title": "An HL7 v2 message leaks into FHIR", "ref": "Patient/3015",
         "query": "Patient?_count=50",
         "why": "A converter from HL7 v2 (the older message format) copied raw field markers into the phone number, three numbers in one string, and turned empty name parts into the text \"null null\".",
         "resource": find("patients", "3015")},
    ]


def fetched_date() -> str:
    """Date of the newest cached response: when the data in the report was actually fetched."""
    newest = max(f.stat().st_mtime for name in SERVERS for f in (DEFAULT_CACHE_DIR / name).glob("*.json"))
    return datetime.fromtimestamp(newest).strftime("%Y-%m-%d")


def build() -> dict:
    servers = {name: server_data(name) for name in SERVERS}
    return {
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "fetched": fetched_date(),
        "threshold": THRESHOLD_PCT,
        "pageSize": PAGE_SIZE,
        "servers": servers,
        "requests": request_log(),
        "weird": weird_examples(),
    }


def main() -> None:
    data = build()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text()
    if PLACEHOLDER not in html:
        raise SystemExit(f"placeholder {PLACEHOLDER!r} missing from {TEMPLATE.name}")
    OUT.write_text(html.replace(PLACEHOLDER, blob))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB, "
          f"{len(data['requests'])} requests summarized, 0 network calls)")


if __name__ == "__main__":
    main()
