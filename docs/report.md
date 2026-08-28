# SpeciAI Report

**Repository:** `https://github.com/sdsc-ordes/speciai` **Authors:** Martin
Fontanet, Cyril Matthey-Doret, Robin Franken (SDSC)

## 1. What the software does

`speciai` turns a photograph of a pinned insect specimen into a structured
[Darwin Core](https://dwc.tdwg.org/) record, ready for import into a collection
management system.

A photo goes through four steps:

| #   | Step            | What happens                                                         |
| --- | --------------- | -------------------------------------------------------------------- |
| 1   | Extraction      | A multimodal language model reads the label pixels directly          |
| 2   | Enrichment      | Names matched against GBIF, places against Nominatim (OpenStreetMap) |
| 3   | Post-processing | A fixed table of corrections plus the collection's constant fields   |
| 4   | Human review    | A web form shows the photo beside the filled record for correction   |

The record is then exported as CSV or as JSON.

## 2. What is in the repository

```
src/speciai/       the pipeline (~2.6k lines of Python)
  extract.py       stage 1: the model prompt and the endpoint client
  enrich/          stage 2: GBIF species matching, Nominatim geocoding, date parsing
  postprocess.py   stage 3: the correction rule table and the collection constants
  qr.py            QR decoding and payload mapping
  schema.py        the Darwin Core record definition, single source of truth
  pipeline.py      orchestration of stages 1-3
  web/             stage 4: the review server, form and export
  cli.py           the `speciai extract` / `enrich` / `serve` commands
tests/             393 automated tests
schemas/           the published Darwin Core JSON Schema
tools/scripts/     the benchmark harness (fetch photos, run, score, report)
tools/             build, container, formatting and environment configuration
docs/              this report and the development guide
```

The whole thing runs on one machine (CPU, 16 GB RAM) and calls out to a model
served elsewhere. The model can be swapped with any LLM model that uses an
OpenAI-compatible API. **There is no model bundled inside it.**

## 3. Using it

The software needs one thing configured: the address of a multimodal model. Any
OpenAI-compatible endpoint works, whether that is a commercial API (Claude,
Gemini, ChatGPT, ...) or a model served on institutional hardware (the
benchmarks used EPFL's RCP inference service).

**Installing it.** Needs Python 3.13 or newer and
[uv](https://docs.astral.sh/uv/). From a clone of the repository:

```
uv sync
```

**Configuring the model.** Copy `.dist.env` to `.env` and fill in three values:

```
LLM_BASE_URL=https://inference-rcp.epfl.ch/v1   # or another provider
LLM_MODEL=Qwen/Qwen3.8-27B-fp8                  # the model id served there
LLM_API_KEY=...                                 # the key for that endpoint
```

`LLM_BASE_URL` already defaults to EPFL's RCP service, so only the model id and
the key are strictly needed. The key has no command-line option to avoid having
it in the shell history. Every provider needs its own key, and some providers
need one extra setting, which the README lists.

**For a curator, reviewing photos one at a time:**

```
just run serve
```

Then open `http://127.0.0.1:8000` and:

1. Choose a specimen photo.
2. Watch the two automated stages run (the page updates live; you can navigate
   away and come back).
3. Review the filled form beside the original photo. Fields the pipeline worked
   out itself, rather than read off a label, are badged `Auto-set`.
4. Export as CSV or JSON.

A container image is provided (`docker compose up`) for anyone who would rather
not install Python.

**For scoring a model against the ETH sheet:**

```
just run-benchmark
```

This runs every photo in `examples/bugs/`, scores each field against the ETH
export, and writes a timestamped folder under `runs/` with a per-field score
table, a per-photo detail table, token costs and an HTML report.

## 4. What we did

**Dropped the OCR step.** At first we read the text off the label with OCR
software, then asked a language model to sort that text into the right fields.
It got only 35 to 40% of fields right. Showing the photo straight to the model
does better, so the OCR step is gone. That also removed a family of problems: a
ruler in the frame, a sideways label, a faded letter guessed wrong before
anything could check it. Each photo is now a single request to the model.

**Connected the reference databases.** The species name goes to GBIF, which
returns the full classification and an ID that stays valid even if the species
is renamed later. The place name goes to Nominatim, which returns country,
region, locality and coordinates. If a lookup fails we leave those fields empty
and write a log entry. We never throw the record away.

**Wrote the automatic fixes down in one place.** Some values need tidying, such
as putting country codes in capitals or filling in the continent. Every fix sits
in one table that says which field it reads and which field it changes. The
software then checks three things by itself: no fix ever alters what the label
says, no fix names a field that does not exist, and no fix depends on another
one. We also test that running the fixes twice gives the same answer, so a
curator can press "re-derive" without spoiling the record.

**Added QR code support.** If a QR code is pinned with the specimen, we read it
before the model sees the photo. A curator typed that data in, so we treat it as
correct and the model never gets to disagree. We also ask GBIF about the name
from the code rather than the name on the label. Otherwise a record can end up
with a wasp's name and a butterfly's family.

**Built the review screen.** It shows the photo next to the filled-in record.
Values the software worked out itself are marked, so a curator can tell them
apart from what was read off the label. It warns before anything would discard
edits, and it exports a CSV that Specify can import.

**Built a benchmark on real collection data.** We run 25 photos from the ETH
collection and compare each record against the matching row in the ETH export.
The comparison allows for honest differences: coordinates count as correct
within one degree, people are matched on family name, and for the label
transcription we check that the right words appear. The export is a tidied
database rather than a transcription, so demanding an exact match would be an
unfair test.

**Made the model swappable.** The pipeline works with any provider that speaks
the common OpenAI format. Changing provider means editing a settings file, not
the code.

### Current measured accuracy

Latest run: `runs/20260828-181934`, model `Qwen/Qwen3.8-27B-fp8` on EPFL RCP,
2026-08-28. All 25 photos scored, none failed. Total cost USD 0.0038, and 123
seconds for the whole batch, about 5 seconds per photo.

Accuracy is correct / (correct + wrong + missing), counting only the fields the
ETH sheet has an answer for.

| Group                       | Fields                                                                                                                                                                                                                           | Accuracy    |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| Reliable                    | `catalogNumber`, `family`, `genus`, `specificEpithet`, `subfamily`, `tribe`, `order`, `infraspecificEpithet`, `sex`                                                                                                              | 1.00        |
| Reliable                    | `typeStatus` 0.96, `verbatimIdentification` 0.96, `dateIdentified` 0.95, `identifiedBy` 0.91, `taxonId` 0.88                                                                                                                     | 0.88 - 0.96 |
| Set by collection constants | `kingdom`, `phylum`, `lifeStage`, `geodeticDatum`                                                                                                                                                                                | 0.91 - 1.00 |
| Usable with review          | `preparations` 0.80, `scientificName` 0.64, `recordedBy` 0.46, `eventDate` 0.42                                                                                                                                                  | 0.42 - 0.80 |
| Weak                        | `scientificNameAuthorship` 0.36, `continent` 0.36, `country` 0.35, `countryCode` 0.32, `verbatimEventDate` 0.32, `decimalLatitude` 0.30, `decimalLongitude` 0.30, `verbatimLocality` 0.26, `stateProvince` 0.19, `locality` 0.05 | 0.05 - 0.36 |
| Not comparable              | `verbatimLabel`: 0.71 term recall against a curated summary                                                                                                                                                                      | n/a         |

Three readings matter more than the numbers themselves.

**Taxonomy is solved; geography is not.** Every rank the label supplies is read
correctly, and GBIF fills the rest. The location fields, by contrast, are mostly
_empty_ rather than wrong: 14 of 25 records carry no locality at all. That is
not the labels lacking a place. It is the geocoding step returning nothing for
more than half the photos, and doing so quietly. Fixing that one step should
move seven fields at once.

**Some perfect scores are free.** `kingdom`, `phylum`, `lifeStage` and
`geodeticDatum` are set from a fixed list, not read from the specimen. They
score well by construction and should not be read as evidence the pipeline
works. `lifeStage` in particular is currently forced to `Adult` even where a
label says otherwise, which is the sort of decision that must be the
collection's and not the software's.

## 5. What we plan next

### Accuracy Improvement

- Fix the geocoding step: the label's place hierarchy
  (`CH SH Merishausen : Chlosterfeld`) is currently sent to the geocoder as one
  string, which matches nothing. It must be split and some characters must be
  removed to make it work.
- Fix field-aware formatting (e.g. the use of parenthesis and brackets in
  `scientificNameAuthorship` has a meaning which we did not take into account).
- Review date handling: `verbatimEventDate`.
- Assess the results when using other LLM providers (e.g., OpenAI, Anthropic,
  Google, ...) in the pipeline.
- Explore better prompting techniques and ways to provide context to the LLM
  (web search, images batch, feedback loop, ...).

### UI/UX Review for Users Needs

- Put the current UI in front of two or three curators with a batch of real
  photos, and measure the thing that actually matters: how long a curator takes
  per specimen with the pipeline versus without.
- Validate an exported CSV through a real Specify WorkBench import, end to end.
