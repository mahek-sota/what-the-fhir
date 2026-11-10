"""Build article_assets/report.html: a self-contained, interactive report.

Everything comes from cache/ (0 network calls). The template lives next to this file;
the data is injected as one JSON blob, so the page needs no backend.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
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
VERSIONS = ROOT / "article_assets" / "report_versions.json"
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


def cached_future_probe(name: str = "hapi") -> tuple[str, list[dict]]:
    """The 'born in the future' probe from weird.py uses the date it ran on, so find it by URL instead of guessing the date."""
    hits = []
    for f in (DEFAULT_CACHE_DIR / name).glob("*.json"):
        raw = json.loads(f.read_text())
        m = re.search(r"birthdate=gt(\d{4}-\d{2}-\d{2})", raw["url"])
        if m and "/Patient?" in raw["url"]:
            hits.append((f.stat().st_mtime, m.group(1), raw["body"]))
    if not hits:
        raise RuntimeError("no 'born in the future' probe in cache (run python -m fhirlearn.weird first)")
    _, day, body = max(hits)
    return day, entries(body)


def weird_examples() -> list[dict]:
    c = CacheOnlyClient("hapi")
    probe_day, future = cached_future_probe()
    pools = {
        "future": future,
        "old": entries(c.get("Patient", {"birthdate": "lt1900-01-01", "_count": PAGE_SIZE})),
        "nosubject": entries(c.get("Condition", {"subject:missing": "true", "_count": PAGE_SIZE})),
        "patients": entries(c.get("Patient", {"_count": PAGE_SIZE})),
        "hba1c": fetch_all(c, "Observation", {"code": HBA1C}).resources,
    }

    def find(pool: str, rid: str) -> dict:
        return strip_narrative(next(r for r in pools[pool] if r.get("id") == rid))

    return [
        {"title": "A Klingon born in 2340", "ref": "Patient/470809",
         "query": f"Patient?birthdate=gt{probe_day}",
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


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def update_history(history: list[dict], data_hash: str, layout_hash: str, fetched: str,
                   note: str | None, now: str) -> tuple[list[dict], dict, bool]:
    """Add a version when the data or the layout changed since the last one.

    Returns (history, current version, whether a new version was added).
    Rebuilding with nothing changed keeps the current version.
    """
    last = history[-1] if history else None
    changes = []
    if last is None or last["data_hash"] != data_hash:
        changes.append("data")
    if last is None or last["layout_hash"] != layout_hash:
        changes.append("layout")
    if last is not None and not changes:
        return history, last, False
    default_note = {
        ("data", "layout"): "First version" if last is None else "Data refreshed and layout updated",
        ("data",): "Data refreshed",
        ("layout",): "Layout updated",
    }[tuple(changes)]
    entry = {
        "version": len(history) + 1,
        "built": now,
        "fetched": fetched,
        "changes": changes,
        "note": note or default_note,
        "data_hash": data_hash,
        "layout_hash": layout_hash,
    }
    return [*history, entry], entry, True


def pack(html: str) -> str:
    """gzip + base64, so a whole past report fits in a JSON string (about a quarter of its size)."""
    return base64.b64encode(gzip.compress(html.encode(), mtime=0)).decode()


def unpack(packed: str) -> str:
    return gzip.decompress(base64.b64decode(packed)).decode()


def render(template: str, data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return template.replace(PLACEHOLDER, blob)


def version_of(html: str) -> int | None:
    m = re.search(r'"version":\{"version":(\d+)', html)
    return int(m.group(1)) if m else None


def public(entry: dict) -> dict:
    """What the page shows about a version: no hashes, no snapshot payload."""
    out = {k: v for k, v in entry.items() if not k.endswith("_hash") and k != "snapshot"}
    out["archived"] = bool(entry.get("snapshot"))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Build article_assets/report.html from cache/.")
    ap.add_argument("--note", help="what changed in this version (shown in the report's version history)")
    args = ap.parse_args(argv)

    data = build()
    template = TEMPLATE.read_text()
    if PLACEHOLDER not in template:
        raise SystemExit(f"placeholder {PLACEHOLDER!r} missing from {TEMPLATE.name}")

    data_hash = sha(json.dumps({k: v for k, v in data.items() if k != "generated"}, sort_keys=True))
    history = json.loads(VERSIONS.read_text()) if VERSIONS.exists() else []
    prev_last = history[-1] if history else None
    history, current, added = update_history(
        history, data_hash, sha(template), data["fetched"], args.note, datetime.now().strftime("%Y-%m-%d %H:%M"))
    dirty = added

    # A version built before archiving existed has no snapshot. If report.html on disk is that
    # version, archive it before it is overwritten.
    if added and prev_last and not prev_last.get("snapshot") and OUT.exists():
        on_disk = OUT.read_text()
        if version_of(on_disk) == prev_last["version"]:
            prev_last["snapshot"] = pack(on_disk)

    # Render this version on its own (no archive inside, so snapshots never nest) and keep it.
    data["version"] = public(current)
    data["versions"] = [public(h) for h in reversed(history)]
    data["archive"] = {}
    if not current.get("snapshot"):
        current["snapshot"] = pack(render(template, data))
        dirty = True
    data["versions"] = [public(h) for h in reversed(history)]

    # The published page carries every earlier version, compressed.
    data["archive"] = {str(h["version"]): h["snapshot"] for h in history
                       if h.get("snapshot") and h["version"] != current["version"]}
    OUT.write_text(render(template, data))
    if dirty:
        VERSIONS.write_text(json.dumps(history, indent=1) + "\n")
    elif args.note:
        print("note ignored: nothing changed since the last version")

    status = f"new version v{current['version']} ({', '.join(current['changes'])} changed)" if added \
        else f"no changes, still v{current['version']}"
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB, "
          f"{len(data['archive'])} earlier version(s) embedded): {status}")


if __name__ == "__main__":
    main()
