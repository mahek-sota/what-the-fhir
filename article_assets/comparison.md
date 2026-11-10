| | SMART | HAPI |
|---|---:|---:|
| Patients sampled (1 page of `Patient`) | 50 | 50 |
| Patients with a type 2 diabetes Condition (SNOMED 44054006) | 47 | 154 |
| Patients with an HbA1c Observation (LOINC 4548-4) | 163* | 888* |
| …of those, with any HbA1c ≥ 6.5% | 14* | 309* |

_Generated 2026-11-10. Page size 50, at most 20 pages per query. These are counts in what we fetched, not server totals._

Each row is its own query, so rows are not subsets of each other: the 154 diabetes patients are not drawn from the 50 sampled patients.

\* Hit the 20-page cap: more results exist on the server.
