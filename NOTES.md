# NOTES

Raw notes for the Medium post: things that surprised me or broke, in the order I hit them.

## Step 1: Scaffold

- Decided against a FHIR client library so every request is a visible GET + raw JSON.
- Built politeness into the one client class: GET-only, `_count=50`, max 20 pages, 1s sleep, 30s timeout, on-disk cache.
- Cache keys are the full request URL, so the "next" links (which can be opaque server tokens) are cached too.

## Step 2: Capability check (GET /metadata)

- **SMART was down on 2026-11-10.** TCP and TLS connect in about 0.25s, then the server never sends a single byte. `/metadata` timed out at 30s (httpx) and at 60s (curl), and `Patient?_count=1` timed out at 30s too. "Public test server" means no SLA. Lesson: handle one server being dead without crashing the whole run, and never cache failures.
- HAPI's `/metadata` is **2 MB** of JSON (146 resource types). The CapabilityStatement is the server describing itself, not something small.
- HAPI is on a dated `-SNAPSHOT` build (8.13.10-SNAPSHOT, 2026-09-25). The public test server runs bleeding-edge code.
- HAPI advertises `create`, `update`, `delete` and `patch` on Patient. Anyone on the internet can write to it, which probably explains the junk data I expect to find in step 7.
- Observation has 48 search parameters, including combo ones like `code-value-quantity` (e.g. "HbA1c with value >= 6.5" as a single server-side query). Worth trying later.
- `_filter` is listed, but it's an optional and rarely implemented feature. Listing a parameter doesn't prove it works.
