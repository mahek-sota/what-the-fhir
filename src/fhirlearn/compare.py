"""Step 6: one small SMART vs HAPI table -> article_assets/comparison.md.

Reuses the exact queries from steps 3-5, so on a rerun everything comes from cache/.
A server that is skipped (FHIRLEARN_SERVERS) or fails gets an explicit "n/a" column, never a guessed number.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx

from fhirlearn.client import PAGE_SIZE, SERVERS, FhirClient, active_servers, entries
from fhirlearn.labs import HBA1C, observations_to_df, summarize
from fhirlearn.search import T2DM, fetch_all, subject_patient_ids

OUT = Path(__file__).resolve().parents[2] / "article_assets" / "comparison.md"

ROWS = [
    ("patients", "Patients sampled (1 page of `Patient`)"),
    ("diabetes", "Patients with a type 2 diabetes Condition (SNOMED 44054006)"),
    ("hba1c", "Patients with an HbA1c Observation (LOINC 4548-4)"),
    ("hba1c_high", "…of those, with any HbA1c ≥ 6.5%"),
]


def collect(client: FhirClient) -> dict:
    patients = entries(client.get("Patient", {"_count": PAGE_SIZE}))
    cond = fetch_all(client, "Condition", {"code": T2DM})
    obs = fetch_all(client, "Observation", {"code": HBA1C})
    lab = summarize(observations_to_df(obs.resources))
    return {
        "patients": (len(patients), False),
        "diabetes": (len({p for p in subject_patient_ids(cond.resources) if p}), cond.hit_cap),
        "hba1c": (lab["patients"], obs.hit_cap),
        "hba1c_high": (lab["patients_ge_6_5"], obs.hit_cap),
    }


def render(results: dict[str, dict | str], today: str) -> str:
    names = list(SERVERS)
    lines = [
        f"| | {' | '.join(n.upper() for n in names)} |",
        f"|---|{'---:|' * len(names)}",
    ]
    for key, label in ROWS:
        cells = []
        for n in names:
            r = results.get(n)
            if isinstance(r, dict):
                value, capped = r[key]
                cells.append(f"{value}{'*' if capped else ''}")
            else:
                cells.append("n/a")
        lines.append(f"| {label} | {' | '.join(cells)} |")

    notes = [
        "",
        f"_Generated {today}. Page size 50, at most 20 pages per query. These are counts in what we fetched, not server totals._",
        "",
        "Each row is its own query, so rows are not subsets of each other: the 154 diabetes patients are not drawn from the 50 sampled patients.",
        "",
        "\\* Hit the 20-page cap: more results exist on the server.",
    ]
    for n in names:
        r = results.get(n)
        if not isinstance(r, dict):
            notes += ["", f"**{n.upper()} n/a:** {r}"]
    return "\n".join(lines + notes) + "\n"


def main() -> None:
    results: dict[str, dict | str] = {}
    active = active_servers()
    for name in SERVERS:
        if name not in active:
            results[name] = "skipped (not in FHIRLEARN_SERVERS); server was unreachable during this run."
            continue
        with FhirClient(name) as c:
            try:
                results[name] = collect(c)
                print(f"{name}: ok (network calls: {c.network_calls})")
            except httpx.HTTPError as e:
                results[name] = f"request failed ({type(e).__name__})."
                print(f"{name}: FAILED {type(e).__name__}")
    md = render(results, date.today().isoformat())
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(md)
    print(f"\nwrote {OUT.relative_to(OUT.parents[1])}\n")
    print(md)


if __name__ == "__main__":
    main()
