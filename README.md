# what-the-fhir

A small, **read-only** Python project that explores two public FHIR R4 test servers using plain REST calls and raw JSON. There's no FHIR client library, so every request is a visible `GET`.

- SMART: https://r4.smarthealthit.org
- HAPI: https://hapi.fhir.org/baseR4

It was written while learning FHIR, as material for a Medium post. [`NOTES.md`](NOTES.md) has the raw notes on what surprised me or broke along the way.

## What it does

| Step | Module | Request(s) | What you get |
|---|---|---|---|
| 2 | `fhirlearn.capability` | `GET /metadata` | FHIR version, plus the interactions and search parameters for Patient, Condition and Observation |
| 3 | `fhirlearn.patients` | `GET /Patient?_count=50` | The Bundle structure, Patient fields, and a DataFrame (`id, gender, birthDate, has_name`) |
| 4 | `fhirlearn.search` | `GET /Condition?code=http://snomed.info/sct\|44054006` | Type 2 diabetes Conditions, paged, with distinct patients counted via `subject` |
| 5 | `fhirlearn.labs` | `GET /Observation?code=http://loinc.org\|4548-4` | HbA1c readings with units normalized (% and mmol/mol), and patients with a reading ≥ 6.5% |
| 6 | `fhirlearn.compare` | (reuses steps 3–5) | [`article_assets/comparison.md`](article_assets/comparison.md) |
| 7 | `fhirlearn.weird` | `:missing` / `birthdate=gt…` probes, `Patient?_id=…` lookups | [`article_assets/weird.md`](article_assets/weird.md) |

## How to run

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest                                 # offline tests, no network

python -m fhirlearn.capability         # step 2
python -m fhirlearn.patients           # step 3
python -m fhirlearn.search             # step 4
python -m fhirlearn.labs               # step 5
python -m fhirlearn.compare            # step 6 -> article_assets/comparison.md
python -m fhirlearn.weird              # step 7 (HAPI only)
python -m fhirlearn.report             # interactive page -> article_assets/report.html (from cache only)
```

`article_assets/report.html` is a single self-contained page with all the results embedded: every request, the Bundle structure, charts and the weird records. Open it in a browser; no Python needed.

### The report and results are a snapshot

`report.html`, `comparison.md`, `weird.md` and the tables below show what the servers returned on **2026-11-10**. They don't update themselves, and both servers are public sandboxes whose data changes (HAPI seems to be wiped and reloaded from time to time). The page says this near the top and shows the fetch date.

To refresh everything:

```bash
rm -rf cache/hapi cache/smart        # throw away the old responses
python -m fhirlearn.capability       # re-fetch /metadata
python -m fhirlearn.compare          # re-fetch steps 3-5, rewrites comparison.md
python -m fhirlearn.weird            # re-run the weirdness probes
python -m fhirlearn.report --note "December refresh"   # rebuild report.html from the new cache
```

### Report versions

The report shows its version at the top (for example `v2 · 2026-12-01`) and lists every version in a "Report versions" section at the bottom. The history lives in `article_assets/report_versions.json`; commit it with the report.

- Each `python -m fhirlearn.report` run checks whether the **data** (the fetched results) or the **layout** (`report_template.html`) changed since the last version. If either did, it records the next version number.
- Rebuilding with nothing changed keeps the current version, so you can rerun it freely.
- `--note "..."` describes the change in the history. Without it you get a default such as "Data refreshed" or "Layout updated".
- **Past versions live inside `report.html`.** Each version is stored compressed (about 50 KB each) and embedded in the latest page. In the "Report versions" table, **Open vN** shows that version in a new browser tab, exactly as it was built, with a banner marking it as archived. There are no separate per-version files.
- `report_versions.json` keeps the same compressed copies so the next build can carry them forward. Don't delete it, or the archive starts over.

Some parts won't update on their own:

- The five weird records are picked by hand in `report.py`. If one has been deleted from HAPI, the report build stops with an error.
- The weirdness probes compare birth dates against the fixed date 2026-11-10.
- The outage timeline and some captions in the report describe this one session.
- `weird.md` and the results tables in this README are written by hand. Update them yourself.

Skip a server that is down:

```bash
FHIRLEARN_SERVERS=hapi python -m fhirlearn.compare
```

### Being polite to public servers

All requests go through `fhirlearn.client.FhirClient`, which:

- only sends `GET` (there is no method for anything else),
- asks for small pages (`_count=50`) and follows at most **20 pages** per search,
- sleeps 1 second before each real request and uses a 30-second timeout,
- caches every raw response in `cache/<server>/` (gitignored), so reruns don't touch the server.

To fetch fresh data, delete `cache/`. Note that HAPI's "next" links are temporary server cursors, so an old cached run and a new run may not line up page for page.

## Results

From the run on 2026-11-10:

| | SMART | HAPI |
|---|---:|---:|
| FHIR version / software | 4.0.0 / Smile CDR 2019.08.PRE | 4.0.1 / HAPI FHIR 8.13.10-SNAPSHOT |
| Patients sampled (1 page of `Patient`) | 50 | 50 |
| Patients with a type 2 diabetes Condition (SNOMED 44054006) | 47 | 154 |
| Patients with an HbA1c Observation (LOINC 4548-4) | 163* | 888* |
| …of those, with any HbA1c ≥ 6.5% | 14* | 309* |

\* Hit the 20-page cap: more results exist on the server. Each row is its own query, so the rows are not subsets of each other.

**SMART was unreachable for most of the session.** TCP and TLS connected, but no response came back for hours. It recovered later the same day, and the SMART column comes from that later run.

The two servers feel very different. SMART holds tidy synthetic (Synthea) patients, where every Patient has the same 13+ fields and every HbA1c uses exactly `%` + UCUM. HAPI is a free-for-all written to by many people, with 6 unit spellings for the same test, missing required fields and impossible values.

Highlights from [`weird.md`](article_assets/weird.md): a patient born in 2340, a patient born in year 0000, a Condition with no content at all, an HbA1c of 112%, and HL7 v2 markup leaking into a phone number.

## Limitations

- **Public test data.** Both servers hold synthetic or demo data that anyone can write to (HAPI's `/metadata` advertises create, update and delete). Nothing here says anything about real patients or real prevalence.
- **Counts are samples, not totals.** The 20-page cap stops a search at 1,000 results, and HAPI doesn't return `Bundle.total`. Rows marked `*` were cut off.
- **Data changes.** HAPI seems to be wiped and reloaded from time to time (all sampled patients were last updated within 20 seconds on 2026-09-25), and people write to it constantly. Rerunning without the cache will give different numbers.
- **"Patients sampled" is one page.** It's the first 50 Patients the server returned, not a random sample.
- **One code per concept.** Diabetes is matched only on SNOMED `44054006`, and HbA1c only on LOINC `4548-4`. Records coded with ICD-10 only, with other HbA1c LOINC codes (e.g. `17856-6`), or with free text only are missed.
- **HbA1c cleaning is deliberately simple.** `%` and `percent` are accepted, mmol/mol is converted (`% = 0.09148 × mmol/mol + 2.152`), and anything labeled % but outside 3–20 is flagged and excluded, not "fixed". That floor excludes 83 of SMART's synthetic readings (2.4–2.9%), which doesn't change its ≥ 6.5% count. A patient counts as ≥ 6.5% if *any* usable reading reaches it.
- **Reference check is partial.** Step 7 checked 1,000 of the 1,031 referenced patients before reaching the request cap.
- **A public server can simply not answer.** SMART hung for hours on 2026-11-10. `FHIRLEARN_SERVERS` lets you skip a server, and the cache means a finished run never needs it again.
