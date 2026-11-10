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

## Step 3: Patients

- SMART still down (retried once with curl, 30s timeout, no response). Step 3 ran on HAPI only.
- HAPI's searchset Bundle has **no `total`**. You don't learn how many patients exist without asking (`_summary=count` or `_total=accurate`). Counts in this project will be samples.
- HAPI's "next" link isn't `?page=2`. It's `baseR4?_getpages=<uuid>&_getpagesoffset=50…`, a server-side cursor that can **expire**, so caching matters for reproducible reruns.
- Most of the first page is `nhanes-*` patients uploaded by a third party (`karyon.bio`). They tagged them in `meta.tag` as "Real NHANES measurements; name, MRN and birth date are generated". That's good provenance practice and a nice example of what `meta.tag` is for.
- **Every patient on the page has `lastUpdated` within the same 20 seconds on 2026-09-25**, the same date as the HAPI SNAPSHOT build. The public server looks like it was wiped and reloaded then, so "public test data" isn't stable over time.
- Patient `3015`, a botched HL7 v2 → FHIR conversion:
  - `name.text` is the string `"null null"`, while `family` is `"TestDaniel"` and given is `"AMARI"`
  - `identifier.type.text` is `"null "` (with a trailing space) and `identifier.system` is `"MRN"`, which isn't a URI
  - the phone number is raw v2 markup: `<PID.13.1>(862)438-0782</PID.13.1><PID.13.1>(872)-845-7895</PID.13.1>…` (three numbers in one string)
  - no gender, no birthDate
  - Candidate for the weirdness report (step 7).
- My `has_name()` counts `3015` as named, because `family` is present. Its `text` of "null null" would fool a naive check that only reads `name.text`.
