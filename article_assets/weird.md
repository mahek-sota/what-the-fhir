# Weird data on the public HAPI FHIR server

Found on 2026-11-10 at https://hapi.fhir.org/baseR4. Anyone can write to this server, so expect these to change or disappear.

## 1. A Klingon born in 2340: `Patient/470809`

`name: Worf, Son of Mogh` · `birthDate: 2340-12-09` · `gender: male` · `deceasedBoolean: false`

Found with `Patient?birthdate=gt2026-11-10`. The server accepted a birth date 314 years in the future. FHIR's `date` type checks the *format*, not whether the date makes sense.

## 2. Jesus Christ, born on Christmas Eve of year zero: `Patient/470065`

`name: Jesus Christ` · `birthDate: 0000-12-24` · MRN `470065`

Found with `Patient?birthdate=lt1900-01-01`. The FHIR `date` regex doesn't allow the year `0000` (there's no year zero in the calendar), but HAPI stored it anyway. The record is on `versionId: 2`, so someone came back to edit it.

## 3. A Condition that is nothing at all: `Condition/23936`

```json
{"resourceType": "Condition", "id": "23936", "meta": {"versionId": "1", "lastUpdated": "2026-09-26T15:53:51.736-04:00"}}
```

It has no code, no patient and no status. R4 says `Condition.subject` is required, so this shouldn't be valid. HAPI stored it anyway. A close relative is `Condition/97074`: type 2 diabetes (SNOMED 44054006) that belongs to no one.

## 4. An HbA1c of 112%: `Observation/81833`

`code: LOINC 4548-4` · `valueQuantity: 112 %` (UCUM-coded, so it looks fully legitimate) · subject `Patient/81827`

HbA1c is the share of your hemoglobin that has sugar attached, so it can't exceed 100%. A real reading of 12% is already very high. Nearby: `Observation/77070` at 85%, and 18 `obs-lab-ehr-{a,b}-pNNN-d0` readings of exactly 45 "percent". Those look like mmol/mol numbers put in a % field.

## 5. An HL7 v2 message that leaked into FHIR: `Patient/3015`

```json
"name":    [{"text": "null null", "family": "TestDaniel", "given": ["AMARI"]}],
"telecom": [{"value": "<PID.13.1>(862)438-0782</PID.13.1><PID.13.1>(872)-845-7895</PID.13.1><PID.13.1>(872)-845-7885</PID.13.1>"}]
```

A converter from HL7 v2 (the older pipe-delimited message format) to FHIR put the raw v2 field markers into the phone number, three numbers in one string. It also turned two empty name fields into the text `"null null"`. There's no gender and no birth date.

---

## Honorable mentions

- **The test-automation family**: `Patient/464380`, `464388`, `464414` … at least 9 patients named "Asha QaAuto<timestamp>", all born `2027-11-04`. Someone's test suite creates a new patient on every run and never cleans up.
- **`Patient/283856`**: "1kkk lll", born 1890-12-12, which is what keyboard-mashing looks like in FHIR.
- **"No code" doesn't mean what you'd think**: `Condition?code:missing=true` returned Conditions like `292787` that *do* have `code.text: "Asthma"`. They have no *coding*, meaning no machine-readable code. To a server, free text doesn't count as a code.
- **Patients pointed to by an ID instead of a link**: `Condition/91869` and `Condition/145005` refer to their patient by an `identifier` (a Brazilian national ID, a `VERIFY-TEMP-001`) rather than a `Patient/123` reference. FHIR allows this, but you can't follow the link, so `subject:missing=true` reports them as having no subject.

## The weird thing that wasn't: dangling references

I checked whether the patients referenced by our diabetes Conditions and HbA1c Observations exist, by looking them up 50 at a time with `Patient?_id=a,b,c…`. Of 1,031 referenced patients, 1,000 were checked (the request cap stopped the rest) and **all 1,000 exist**. HAPI rejects a write that points to a patient that doesn't exist (it enforces referential integrity), so the junk on this server is junk *inside* valid records, not broken links between them.
