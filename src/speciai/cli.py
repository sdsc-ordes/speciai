import argparse
import csv
import json
import os

from pathlib import Path
from dotenv import load_dotenv

from speciai.enrich import enrich_record
from speciai.pipeline import run as pipeline_run
from speciai.schema import DarwinCoreRecord
from speciai.extract import (
    DEFAULT_THINKING,
    OMIT_TEMPERATURE,
    THINKING_CHOICES,
    Extractor,
    parse_temperature,
    thinking_extra_body,
)

# Any OpenAI-compatible endpoint serving a multimodal model works. EPFL's RCP
# inference service is the default because it is what the benchmarks in `runs/` were
# scored against; see README.md for the other providers.
DEFAULT_LLM_BASE_URL = "https://inference-rcp.epfl.ch/v1"


def _env(name: str, default: str | None = None) -> str | None:
    """Read an environment variable, treating an empty value as unset.

    Compose and CI both pass a variable through as the empty string when the host
    has not set it, which must mean "use the default" and not "the endpoint is ''".
    """
    return os.getenv(name) or default


def _temperature(value: str | None) -> float | None:
    """Adapt :func:`parse_temperature` to argparse's error reporting."""
    try:
        return parse_temperature(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _add_llm_options(parser: argparse.ArgumentParser) -> None:
    """Add the endpoint options every command that calls a model shares.

    Each one falls back to an environment variable, which ``.env`` can supply, so a
    deployment configures the endpoint once instead of on every invocation. The API
    key is deliberately env-only: a key in ``argv`` lands in the shell history and in
    every process listing on the machine.
    """
    parser.add_argument(
        "--llm-base-url",
        default=_env("LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
        help="OpenAI-compatible endpoint base URL (env: LLM_BASE_URL). "
        f"Default: {DEFAULT_LLM_BASE_URL}",
    )
    parser.add_argument(
        "--model",
        default=_env("LLM_MODEL"),
        help="Model id the endpoint serves (env: LLM_MODEL). Required.",
    )
    parser.add_argument(
        "--thinking",
        choices=sorted(THINKING_CHOICES),
        default=_env("LLM_THINKING", DEFAULT_THINKING),
        help="Whether a vLLM-hosted reasoning model emits a thinking trace "
        f"(env: LLM_THINKING). Default: {DEFAULT_THINKING}. Use 'none' to send no "
        "such field, for a provider that rejects one it does not define.",
    )
    parser.add_argument(
        "--temperature",
        type=_temperature,
        default=_temperature(_env("LLM_TEMPERATURE")),
        help=f"Sampling temperature, or {OMIT_TEMPERATURE!r} to send none at all "
        "(env: LLM_TEMPERATURE). Default: 0.0, which keeps a run reproducible. "
        "Claude models reject the parameter and need 'none'.",
    )


def _media_url(image_path: Path) -> str | None:
    """Look up an image's source URL in a sibling manifest.csv, if there is one.

    ``tools/scripts/fetch-images.py`` writes that manifest, so extracting a downloaded
    photo records where it came from instead of just its file name.
    """
    manifest = image_path.parent / "manifest.csv"
    if not manifest.is_file():
        return None
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("filename") == image_path.name:
                return row.get("url")
    return None


def _cmd_extract(args: argparse.Namespace) -> None:
    extractor = Extractor(
        base_url=args.llm_base_url,
        model_id=args.model,
        api_key=os.getenv("LLM_API_KEY"),
        extra_body=thinking_extra_body(args.thinking),
        temperature=args.temperature,
    )

    for image_path in args.images:
        result = pipeline_run(image_path, extractor, media_url=_media_url(image_path))
        print(result.record.model_dump_json(exclude_none=True))


def _cmd_enrich(args: argparse.Namespace) -> None:
    for record_path in args.records:
        record = DarwinCoreRecord.model_validate(json.load(open(record_path, "r")))
        enriched = enrich_record(record)
        print(enriched.model_dump_json(indent=2, exclude_none=True))


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn  # noqa: PLC0415

    from speciai.web.app import create_app  # noqa: PLC0415

    app = create_app(
        llm_base_url=args.llm_base_url,
        model_id=args.model,
        api_key=os.getenv("LLM_API_KEY"),
        extra_body=thinking_extra_body(args.thinking),
        temperature=args.temperature,
    )
    uvicorn.run(app, host=args.host, port=args.port)


def main() -> None:
    # Before the parser is built: the endpoint options read their defaults from the
    # environment as they are declared, so `.env` has to be loaded by then.
    load_dotenv()

    parser = argparse.ArgumentParser(description="speciai CLI")
    subparsers = parser.add_subparsers(required=True)

    extract = subparsers.add_parser(
        "extract", help="Extract Darwin Core fields from specimen label images."
    )
    extract.add_argument("images", nargs="+", type=Path, metavar="IMAGE")
    _add_llm_options(extract)
    extract.set_defaults(func=_cmd_extract)

    enrich = subparsers.add_parser(
        "enrich", help="Enrich json records with external metadata."
    )
    enrich.add_argument("records", nargs="+", type=Path, metavar="RECORD")
    enrich.set_defaults(func=_cmd_enrich)

    serve = subparsers.add_parser("serve", help="Run the review web server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    _add_llm_options(serve)
    serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args()
    # No model id is right for every provider, so this one has no default. Checked
    # here rather than with `required=True`, which would ignore LLM_MODEL.
    if hasattr(args, "model") and not args.model:
        parser.error("a model id is required: pass --model or set LLM_MODEL")
    args.func(args)


if __name__ == "__main__":
    main()
