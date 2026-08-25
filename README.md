<p align="center">
  <img src="./docs/assets/logo.svg" alt="project logo" width="250">
</p>

<h1 align="center">
  speciai
</h1>
<p align="center">
</p>

[![Current Release](https://img.shields.io/github/release/sdsc-ordes/speciai.svg?label=release)](https://github.com/sdsc-ordes/speciai/releases/latest)
[![Pipeline Status](https://img.shields.io/github/actions/workflow/status/sdsc-ordes/speciai/normal.yaml?label=ci)](https://github.com/sdsc-ordes/speciai/actions/workflows/normal.yaml)
[![License label](https://img.shields.io/badge/License-MIT-blue.svg?)](https://mit-license.org/)

**Authors:**

- [Martin Fontanet](mailto:martin.fontanet@epfl.ch)
- [Cyril Matthey-Doret](mailto:cyril.matthey-doret@epfl.ch)
- [Robin Franken](mailto:robin.franken@epfl.ch)

# Insect specimen digitization

Ingests images of specimen with various human-written labels to produce
structured [Darwin Core](https://dwc.tdwg.org/) records.

```mermaid
flowchart TD
    IMG(["Specimen image"])
    DWC(["Darwin Core JSON"])
    ENRICHED(["Enriched JSON"])
    VALID(["Validated JSON"])
    CSV(["CSV"])
    JSONOUT(["JSON"])

    EXTRACT[Field extraction]
    ENRICH[Enrichment]
    REVIEW[Human review and corrections]
    EXPORT[Export]

    LLM{{"Multimodal LLM via an OpenAI-compatible endpoint"}}
    QR{{"QR codes decoded (zxing-cpp) and fed to the prompt as fact"}}
    ENRICHTECH{{"Nominatim (geopy) · GBIF species match"}}
    FORM{{"Interactive pre-filled form"}}

    IMG --> EXTRACT --> DWC --> ENRICH --> ENRICHED --> REVIEW --> VALID --> EXPORT
    EXPORT --> CSV
    EXPORT --> JSONOUT
    REVIEW -->|corrections| ENRICH

    EXTRACT -.- LLM
    EXTRACT -.- QR
    ENRICH -.- ENRICHTECH
    REVIEW -.- FORM

    classDef data fill:#eef3fc,stroke:#4c6ef5,color:#1a1a1a;
    classDef proc fill:#fff4e6,stroke:#e8590c,color:#1a1a1a;
    classDef tech fill:none,stroke:#868e96,stroke-dasharray: 3 3,color:#495057;

    class IMG,DWC,ENRICHED,VALID,CSV,JSONOUT data;
    class EXTRACT,ENRICH,REVIEW,EXPORT proc;
    class LLM,QR,ENRICHTECH,FORM tech;
```

## Stages

| #   | Stage        | Tool / model                           | Output                    |
| --- | ------------ | -------------------------------------- | ------------------------- |
| 1   | Extraction   | Multimodal LLM (OpenAI-compatible API) | Darwin Core–keyed JSON    |
| 2   | Enrichment   | Nominatim (geopy), GBIF species match  | Authority-resolved values |
| 3   | Human review | Interactive pre-filled form            | Confirmed / edited record |

## Infrastructure

- **Storage**: S3 with prefixes `images/` and `models/`
- **Compute**: local only (CPU, 16GB RAM)
- **Secrets**: `.env` encrypted with `age` + `sops`. Covers S3 credentials and
  API tokens.

## Open Questions

- [x] Validate `doctr` on real label images.
- [x] Benchmark Gemma 4 vs. fine-tuned BERT for zero-shot Darwin Core field
      classification.
- [ ] Confirm output format requirements (json-ld or plain Darwin Core JSON)
- [x] Identify relevant sources for enrichment.
- [ ] Should we use a workflow manager (metaflow, temporal) to connect steps.

## Extraction model

The `extract` and `serve` commands read specimen images through an
OpenAI-compatible chat-completions endpoint. The model must be multimodal -- it
reads the label pixels directly, with no OCR step. There is no in-process model:
to run one locally, serve it yourself (vLLM, llama.cpp, Ollama) and point
`--llm-base-url` at it.

    uv run speciai extract --llm-base-url https://api.openai.com/v1 --model gpt-4o-mini specimen.jpg

- `--llm-base-url` (required): base URL of the endpoint, e.g.
  `http://localhost:8000/v1` for a locally served model.
- `--model` (required): model id the endpoint serves.
- `LLM_API_KEY` (env var, loaded from `.env`): API key sent to the endpoint.

## QR codes

Any QR code pinned with the specimen is decoded (zxing-cpp) before stage 1. A
curator typed the payload in, so it outranks both the model's reading of the
label and the enrichment lookups. Two codes on one image are both read, in
reading order, and an image without one changes nothing. Only QR codes are read:
a linear accession barcode states something else and must not be passed off as
QR data.

A payload comes in one of two shapes.

**A structured record**, holding Darwin Core fields under short keys:

```json
{
  "m1p": "[ETHZ Entomology]",
  "m2v": "1.0",
  "f": "Chrysididae",
  "b": "Chrysidinae",
  "t": "Chrysidini",
  "g": "Stilbum",
  "s": "calens",
  "u": "subcalens",
  "a": "Linsenmaier, 1951",
  "id": "Paolo Rosa",
  "idD": "2019",
  "x": "Female"
}
```

These fields are written onto the record after enrichment, replacing whatever
the model read or GBIF matched. The model never sees them.

| Key | Field             | Key   | Field                  |
| --- | ----------------- | ----- | ---------------------- |
| `f` | `family`          | `u`   | `infraspecificEpithet` |
| `b` | `subfamily`       | `id`  | `identifiedBy`         |
| `t` | `tribe`           | `idD` | `dateIdentified`       |
| `g` | `genus`           | `x`   | `sex`                  |
| `s` | `specificEpithet` |       |                        |

`a` (authority) and the name parts compose two more fields, so the example above
yields `scientificName` = `Stilbum calens subcalens (Linsenmaier, 1951)` and
`scientificNameAuthorship` = `Linsenmaier, 1951`. Payloads store the authority
inconsistently, so brackets wrapping the whole of it come off first: a payload
holding `(Muller, 1764)` still yields `Brachytron pratense (Muller, 1764)` and
not a doubled pair. Brackets that are part of the authorship survive, as in
`Ematurga atomaria ([Denis & Schiffermuller], 1775)`.

`m1p` (provider) and `m2v` (schema version) are discarded, unknown keys are
logged and skipped, and a value the schema refuses is dropped on its own rather
than costing the record. No `verbatim*` field is ever touched: the QR code is
not the label.

**Anything else**, such as a bare `ETHZ-ENT0082619`, is appended to the
extraction prompt as data the model must treat as valid.

## Post-processing

Fields that are the same for every specimen in a collection are set last of all,
after extraction, enrichment and the QR codes, by
`speciai.postprocess.apply_constants`. The defaults are:

| Field     | Value        |
| --------- | ------------ |
| `kingdom` | `Animalia`   |
| `phylum`  | `Arthropoda` |

A constant replaces whatever the pipeline read or matched, since no label or
lookup knows the collection better. A replacement of a value that differed is
logged, because it usually means an identification went wrong further up.

`pipeline.run` takes the mapping as its `constants` argument, so a caller can
set its own fields, or pass `None` to skip the step:

```python
run(image, extractor, constants={"kingdom": "Animalia", "preparations": "pinned"})
run(image, extractor, constants=None)
```

A field name no record has, or a value the schema refuses, raises rather than
landing quietly in every record of the run.

## Web review UI

Install the dependencies and start the server:

    uv sync
    just run serve --llm-base-url http://localhost:8000/v1 --model MODEL_ID

`serve` requires the same `--llm-base-url` / `--model` options as `extract` (see
[Extraction model](#extraction-model)).

Or run it in a container (image: `tools/images/Containerfile`); `./data` is
mounted at `/app/data`. Compose reads `LLM_BASE_URL`, `LLM_MODEL` and
`LLM_API_KEY` from the environment or a git-ignored `.env`, and fails fast if
the first two are unset:

    docker compose up             # or: podman compose up / just image::serve

Open http://127.0.0.1:8000, choose a specimen image, watch it go through extract
-> enrich, review the Darwin Core record beside the image, and export it as a
CSV or JSON.

Workflow:

1. **Upload**: Drag or choose an image on the start page.
2. **Progress**: The browser streams live stage updates (extract, enrich) via
   Server-Sent Events. You can leave the page and return.
3. **Review**: Shows the original image alongside the pre-filled Darwin Core
   form. Edit any field before exporting.
4. **Export**: "Export CSV" downloads a Specify-WorkBench-compatible file whose
   column headers are DarwinCore terms. "Export JSON" returns the same record as
   JSON.

## Installation

Describe the installation instruction here.

## Usage

Describe the installation instruction here.

## Development

Read first the [Contribution Guidelines](/CONTRIBUTING.md).

For technical documentation on setup and development, see the
[Development Guide](docs/development-guide.md)

## Acknowledgement

Acknowledge all contributors and external collaborators here.

## Copyright

Copyright © 2026-2028 Swiss Data Science Center (SDSC),
[www.datascience.ch](http://www.datascience.ch/). All rights reserved. The SDSC
is jointly established and legally represented by the École Polytechnique
Fédérale de Lausanne (EPFL) and the Eidgenössische Technische Hochschule Zürich
(ETH Zürich). This copyright encompasses all materials, software, documentation,
and other content created and developed by the SDSC.
