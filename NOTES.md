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

## Step 4: Type 2 diabetes search (Condition?code=http://snomed.info/sct|44054006)

- SMART still down (third check, no response in 30s).
- HAPI: 4 pages, 159 Conditions, **154 distinct patients**. Didn't hit the 20-page cap, so on this day that's the full result set and not just a sample.
- **The same SNOMED code has 12 different `display` strings**: "Diabetes mellitus type 2 (disorder)", "Type 2 diabetes mellitus", "Diabetes", "Diabetes melitus tipe 2" (Indonesian), and two with no display at all. Search by `code`, never by display text. The display is only a label for humans and every uploader writes their own.
- About 30 Conditions carry **both** SNOMED and ICD-10-CM `E11.9` codings in one `CodeableConcept`. That's the point of `coding` being a list: one concept, several code systems. Two use plain ICD-10 (`.../icd-10`), not ICD-10-CM, which is a different system URI for a near-identical code.
- Condition `97074` has **no `subject` at all**, even though `Condition.subject` is *required* (1..1) in R4. HAPI accepted it anyway. Diabetes, but nobody has it. Weirdness candidate.
- A patient literally named `example` has 2 diabetes conditions. Also `helasync-test-001`. These are someone's test fixtures living on the shared server.
- All subject references were relative (`Patient/123`); none were absolute URLs or `urn:uuid:`. My parser handles all three anyway.
- Unlike the Patient data, these Conditions have `lastUpdated` dates spread after the 2026-09-25 reload (e.g. 2026-10-11), so people are actively writing to HAPI.

## Step 5: HbA1c (Observation?code=http://loinc.org|4548-4)

- **SMART hang, part 2.** One run sat on an open connection to SMART for over 5 minutes despite a 30s httpx timeout. A diagnostic `curl -m 20` then took **251 seconds** and received **0 bytes**, so the server isn't trickling data. Something in the network path hangs, and even curl's wall-clock limit didn't fire on time. I first guessed "slow trickle defeats httpx's per-read timeout". That was wrong, and the curl test disproved it. Fix on our side: `FHIRLEARN_SERVERS=hapi` skips a dead server instead of waiting on it.
- HAPI: **hit the 20-page cap** (1,000 observations), so these are sample counts, not totals. 888 distinct patients in the sample; 309 have at least one usable reading ≥ 6.5%.
- Every HbA1c used `valueQuantity` (no `valueString` like "6.8%", no `>` comparators). That's tidier than I expected.
- **Six different ways to write the unit** for the same test: `%` + UCUM + code `%` (956), `percent` + UCUM + `%` (18), `%` with no system and no code (15), `%` + UCUM + no code (8), `%` + no system + code `%` (1), `mmol/mol` with no system (2). The human `unit` label and the machine `code` are separate fields, and people fill in either, both, or neither.
- **mmol/mol vs %**: HbA1c has two unit conventions (IFCC mmol/mol, used in UK/EU; NGSP %, used in the US). 48 mmol/mol ≈ 6.5%. Converted with % = 0.09148 × mmol/mol + 2.152. Patient `77057`: 64 mmol/mol → 8.0%.
- **Impossible values labeled `%`** (excluded, not "fixed"):
  - `81833`: HbA1c **112%**, UCUM-coded and everything. More than 100% of your hemoglobin is glycated.
  - `77070`: **85%**. Patient `77065` *also* has a 64 mmol/mol reading. Looks like someone typed mmol/mol numbers into a % field.
  - 18 observations `obs-lab-ehr-{a,b}-pNNN-d0` all have exactly **45 "percent"**, in mirrored pairs from two pretend EHRs ("ehr-a" and "ehr-b") two days apart. 45 is very plausible as **mmol/mol** (≈ 6.3%), so it's probably a unit bug in someone's EHR-merge test generator.
- Patient `57525` has 11 readings from 3.03% to 3.12%, slowly creeping up over two years. Under 4% is physiologically very unusual. I kept them, since 3% isn't impossible, but they're clearly synthetic.
- Design choice for the article: I **flag and exclude** implausible values instead of guessing a conversion. Silently "correcting" lab values is how you get wrong clinical numbers.

## Step 6: Comparison table

- SMART still unreachable (5th check, 2026-11-10, hard-killed at 35s). The SMART column is "n/a". I chose not to fill it with numbers from memory or docs: the table only shows what this code actually fetched.
- The table reused the cached responses from steps 3–5 (0 network calls). The cache paid for itself here.
- Gotcha for readers: "patients sampled" (50) is *smaller* than "diabetes patients" (154). Every row is an independent search, not a funnel. A FHIR search on Condition doesn't need the patients in hand first.
- An interesting follow-up I didn't do: `Patient?_has:Condition:subject:code=…` (reverse chaining) would ask the server "patients who have a diabetes condition" directly.

## Step 7: Weirdness report

- 25 new requests to HAPI (5 one-page probe searches + 20 batched `_id` lookups). Nothing to SMART.
- **Let the server find the weirdness.** `name:missing=true`, `code:missing=true`, `subject:missing=true`, `birthdate=gt…` and `birthdate=lt1900-01-01` are all standard FHIR search features (the `:missing` modifier and the `gt`/`lt` prefixes). That's far more efficient than downloading everything and scanning it.
- My scan of the data I'd already fetched found *nothing* odd (no missing names or bad birth dates in the 50-patient page, no uncoded diabetes conditions, by construction). The weirdness only showed up when I asked for it. Sampling one page tells you very little about a messy dataset.
- `code:missing=true` matches Conditions that **have** `code.text` but no `coding`. The `:missing` modifier works on what the server *indexes*, not on what the JSON contains.
- `subject:missing=true` matches Conditions whose subject is an `identifier`, i.e. a reference by ID that has no `reference` URL to follow.
- **No dangling patient references** (0 of 1,000 checked). HAPI enforces referential integrity on write, but not required fields (`Condition/23936` has no subject) or valid dates (`0000-12-24`). So it checks that the links between records are valid, but not the contents of each record.
- Patient `166997` has a masked Chinese name (`林○○`) and a real-looking Taichung street address and mobile number. Possibly real-ish data uploaded to a public server. I deliberately left it out of weird.md.
- Pop culture on the test server: Worf (born 2340), Jesus Christ (born 0000-12-24), plus German "Max Musterman", the German equivalent of "John Doe".

## Step 8: README

- SMART checked a sixth and final time on 2026-11-10: still no response. The whole project ran HAPI-only. For the article, "the server you planned around may simply not answer" is a genuine lesson about public test infrastructure.
- Total footprint on HAPI: about 50 GET requests across all steps, all cached locally.
