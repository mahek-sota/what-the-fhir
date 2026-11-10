"""Step 5: HbA1c Observations (LOINC 4548-4). Normalize values, count patients >= 6.5%."""

from __future__ import annotations

from collections import Counter

import httpx
import pandas as pd

from fhirlearn.client import active_servers, FhirClient
from fhirlearn.search import fetch_all, patient_id_from_ref

HBA1C = "http://loinc.org|4548-4"
THRESHOLD_PCT = 6.5  # ADA diagnostic threshold for diabetes (= 48 mmol/mol)
PLAUSIBLE_PCT = (3.0, 20.0)  # outside this, a "%" value is almost certainly a data error
PERCENT_UNITS = {"%", "percent"}


def ifcc_to_ngsp(mmol_per_mol: float) -> float:
    """mmol/mol (IFCC) -> % (NGSP). Standard master equation."""
    return 0.09148 * mmol_per_mol + 2.152


def normalize_hba1c(obs: dict) -> tuple[float | None, str]:
    """Return (value in %, status). status is 'ok', 'converted', or a reason the value can't be used."""
    q = obs.get("valueQuantity")
    if q is None:
        return None, "no valueQuantity"
    v = q.get("value")
    if not isinstance(v, (int, float)):
        return None, "non-numeric value"
    if q.get("comparator"):
        return None, f"comparator {q['comparator']}"
    unit = (q.get("code") or q.get("unit") or "").strip()
    if unit in PERCENT_UNITS or (q.get("unit") or "").strip() in PERCENT_UNITS:
        lo, hi = PLAUSIBLE_PCT
        if not lo <= v <= hi:
            return None, "implausible % value"
        return float(v), "ok"
    if unit == "mmol/mol":
        return round(ifcc_to_ngsp(v), 2), "converted"
    return None, f"unknown unit {unit!r}"


def unit_label(obs: dict) -> str:
    q = obs.get("valueQuantity") or {}
    return f"unit={q.get('unit')!r} system={'UCUM' if q.get('system') == 'http://unitsofmeasure.org' else q.get('system')!r} code={q.get('code')!r}"


def observations_to_df(observations: list[dict]) -> pd.DataFrame:
    rows = []
    for o in observations:
        pct, status = normalize_hba1c(o)
        rows.append({
            "id": o.get("id"),
            "patient_id": patient_id_from_ref((o.get("subject") or {}).get("reference")),
            "raw_value": (o.get("valueQuantity") or {}).get("value"),
            "unit": unit_label(o),
            "pct": pct,
            "status": status,
        })
    return pd.DataFrame(rows, columns=["id", "patient_id", "raw_value", "unit", "pct", "status"])


def summarize(df: pd.DataFrame) -> dict:
    usable = df[df["pct"].notna() & df["patient_id"].notna()]
    return {
        "observations": len(df),
        "patients": df["patient_id"].nunique(),
        "patients_ge_6_5": usable.loc[usable["pct"] >= THRESHOLD_PCT, "patient_id"].nunique(),
        "unusable_observations": int(df["pct"].isna().sum()),
    }


def main() -> None:
    for name in active_servers():
        with FhirClient(name) as c:
            print(f"\n=== {name.upper()}  GET {c.build_url('Observation', {'code': HBA1C, '_count': 50})}")
            try:
                res = fetch_all(c, "Observation", {"code": HBA1C})
            except httpx.HTTPError as e:
                print(f"FAILED: {type(e).__name__}: {e}")
                continue
            df = observations_to_df(res.resources)
            s = summarize(df)
            print(f"(network calls: {c.network_calls})  pages: {res.pages}  stopped at page cap: {res.hit_cap}")
            print(f"HbA1c observations: {s['observations']}")
            print(f"distinct patients: {s['patients']}")
            print(f"patients with any reading >= {THRESHOLD_PCT}%: {s['patients_ge_6_5']}")
            print(f"observations we could not use: {s['unusable_observations']}")
            print("\n-- unit spellings")
            for k, n in Counter(df["unit"]).most_common():
                print(f"  {n:>4}  {k}")
            print("\n-- value status")
            for k, n in Counter(df["status"]).most_common():
                print(f"  {n:>4}  {k}")
            bad = df[df["status"] != "ok"]
            if len(bad):
                print("\n-- not-ok rows")
                print(bad.to_string(index=False))


if __name__ == "__main__":
    main()
