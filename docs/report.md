# SpeciAI Report

**Repository:** `https://github.com/sdsc-ordes/speciai` **Authors:** Martin
Fontanet, Cyril Matthey-Doret, Robin Franken (SDSC)

## 1. What the software does

`speciai` turns a photo of an insect specimen and its labels into a structured
[Darwin Core](https://dwc.tdwg.org/) record. The record is ready to import into
a collection management system.

A photo goes through four steps:

| #   | Step            | What happens                                                         |
| --- | --------------- | -------------------------------------------------------------------- |
| 1   | Extraction      | A multimodal language model reads the label pixels directly          |
| 2   | Enrichment      | Names matched against GBIF, places against Nominatim (OpenStreetMap) |
| 3   | Post-processing | A fixed table of corrections plus the collection's constant fields   |
| 4   | Human review    | A web form shows the photo beside the filled record for correction   |

The record then comes out as CSV or JSON.

## 2. What is in the repository

```
src/speciai/       the pipeline (~2.7k lines of Python)
  extract.py       stage 1: the model prompt and the endpoint client
  enrich/          stage 2: GBIF species matching, Nominatim geocoding, date parsing
  postprocess.py   stage 3: the correction rule table and the collection constants
  qr.py            QR decoding and payload mapping
  schema.py        the Darwin Core record definition, single source of truth
  pipeline.py      orchestration of stages 1-3
  web/             stage 4: the review server, form and export
  cli.py           the `speciai extract` / `enrich` / `serve` commands
tests/             415 automated tests
schemas/           the published Darwin Core JSON Schema
tools/scripts/     the benchmark harness (fetch photos, run, score, report)
tools/             build, container, formatting and environment configuration
docs/              this report and the development guide
```

It all runs on one machine (CPU, 16 GB RAM). The model itself runs somewhere
else.

## 3. Running it

You need to set one thing: the address of a multimodal model. Any
OpenAI-compatible endpoint works. That can be a commercial API (Claude, Gemini,
ChatGPT and so on) or a model on your own hardware. We used EPFL's RCP inference
service for the benchmarks. There is also a container image, so you do not have
to install Python. The README has the setup steps.

You can use it in two ways. A curator opens the review server and picks a photo.
The pipeline fills in a form next to the photo. Fields the software worked out
on its own, instead of reading them off a label, get an `Auto-set` badge. The
curator then exports the record as CSV or JSON.

## 4. What we did

**Dropped the OCR step.** At first we used OCR to read the text off the label.
Then we asked a language model to sort that text into fields. This got only 35
to 40% of fields right. Showing the photo straight to the model works better, so
we removed the OCR step. That also removed a set of problems: a ruler in the
frame, a sideways label, a faded letter guessed wrong before anything could
check it. Each photo is now one request.

**Connected the reference databases.** The species name goes to GBIF. GBIF
returns the full classification and an ID that stays valid if the species is
renamed later. The place name goes to Nominatim, which returns country, region,
locality and coordinates. If a lookup fails, we leave those fields empty and
write a log entry. We never throw the record away.

**Wrote the automatic fixes down in one place.** Some values need tidying.
Country codes need capitals, for example, and the continent can be filled in.
Every fix sits in one table. The table names the field it reads and the field it
changes. The software then checks three things on its own: no fix changes what
the label says, no fix names a field that does not exist, and no fix depends on
another fix. Running the fixes twice gives the same answer, so a curator can
press "re-derive" without spoiling the record.

**Added QR code support.** If a QR code is pinned with the specimen, we read it
before the model sees the photo. A curator typed that data in, so we treat it as
correct, and the model does not get to disagree. We also ask GBIF about the name
from the code, not the name on the label. Otherwise a record can end up with a
wasp's name and a butterfly's family.

**Built the review screen.** It shows the photo next to the filled-in record. It
marks the values the software worked out on its own. It warns before anything
would throw away edits. It exports a CSV that Specify can import.

**Built a benchmark on real collection data.** We compare each record against
the matching row in the ETH export. The comparison allows for fair differences.
Coordinates count as correct within one degree. People are matched on family
name. For the label transcription we check that the right words show up. The ETH
export is a tidied database, not a transcription, so asking for an exact match
would not be fair.

**Made the model swappable.** To change provider you edit a settings file. You
do not touch the code.

### Current measured accuracy

Our best run so far used `Qwen/Qwen3.8-27B-fp8` on EPFL RCP, in late August
2026, over a sample of 25 photos. Every photo scored and none failed. It cost
USD 0.0038 and took about 5 seconds per photo.

Accuracy is correct / (correct + wrong + missing). We only count fields the ETH
sheet has an answer for.

| Group                       | Fields                                                                                                                                                                                                                           | Accuracy    |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| Reliable                    | `catalogNumber`, `family`, `genus`, `specificEpithet`, `subfamily`, `tribe`, `order`, `infraspecificEpithet`, `sex`                                                                                                              | 1.00        |
| Mostly reliable             | `typeStatus` 0.96, `verbatimIdentification` 0.96, `dateIdentified` 0.95, `identifiedBy` 0.91, `taxonId` 0.88                                                                                                                     | 0.88 - 0.96 |
| Set by collection constants | `kingdom`, `phylum`, `lifeStage`, `geodeticDatum`                                                                                                                                                                                | 0.91 - 1.00 |
| Usable with review          | `preparations` 0.80, `scientificName` 0.64, `recordedBy` 0.46, `eventDate` 0.42                                                                                                                                                  | 0.42 - 0.80 |
| Weak                        | `scientificNameAuthorship` 0.36, `continent` 0.36, `country` 0.35, `countryCode` 0.32, `verbatimEventDate` 0.32, `decimalLatitude` 0.30, `decimalLongitude` 0.30, `verbatimLocality` 0.26, `stateProvince` 0.19, `locality` 0.05 | 0.05 - 0.36 |
| Not comparable              | `verbatimLabel`: 0.71 term recall against a curated summary                                                                                                                                                                      | n/a         |

Two points matter more than the numbers.

**Taxonomy works, geography does not.** Every rank the label gives is read
correctly, and GBIF fills in the rest. The location fields are mostly empty
rather than wrong. 14 of the 25 records have no locality at all. The labels do
have places on them. The problem is that the geocoding step returns nothing for
more than half the photos, and it fails quietly. Fixing that one step should
improve seven fields at once.

**Some perfect scores are free.** `kingdom`, `phylum`, `lifeStage` and
`geodeticDatum` come from a fixed list. We do not read them from the specimen.
They score well because of how they are set, so they do not show that the
pipeline works. `lifeStage` is always set to `Adult`, even when a label says
otherwise. That choice should belong to the collection, not to the software.

## 5. What we plan next

### Accuracy

- Fix the geocoding step. The place hierarchy on the label
  (`CH SH Merishausen : Chlosterfeld`) goes to the geocoder as one string, which
  matches nothing. We need to split it and strip some characters.
- Fix field-aware formatting. The brackets and parentheses in
  `scientificNameAuthorship` carry a meaning that we ignored.
- Review how we handle dates, starting with `verbatimEventDate`.
- Test other LLM providers (OpenAI, Anthropic, Google and so on).
- Try better prompting, and other ways to give the model context: web search,
  batches of images, a feedback loop.

### UI and UX

- Put the current UI in front of two or three curators with a batch of real
  photos. Measure the thing that matters: how long a curator takes per specimen
  with the pipeline, and without it.
- Test an exported CSV through a real Specify WorkBench import, start to finish.
