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

Any QR code pinned with the specimen is decoded (zxing-cpp) before stage 1 and
appended to the extraction prompt as data the model must treat as valid: the
payload was keyed in by a curator, so it outranks the model's own reading of the
label. Two codes on one image are both reported, in reading order. An image
without one changes nothing. Only the QR family is read -- a linear accession
barcode encodes a different claim and must not be passed off as QR data.

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
