# what-the-fhir

A small, read-only Python project that explores two public FHIR R4 test servers using plain REST calls (no FHIR client library):

- SMART: https://r4.smarthealthit.org
- HAPI: https://hapi.fhir.org/baseR4

Work in progress. Full README comes at the end.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
