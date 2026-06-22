"""Generate the Darwin Core record JSON Schema artifact.

The committed ``schemas/darwincore-record.schema.json`` is generated from
:class:`speciai.schema.DarwinCoreRecord`. Run this module to regenerate it
after changing the model or the term classification::

    uv run python -m speciai.generate_schema

Pass ``--check`` to verify the committed file is up to date without writing
(used by the test suite / CI to catch drift)::

    uv run python -m speciai.generate_schema --check
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from speciai.schema import json_schema_with_terms

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "darwincore-record.schema.json"
)


def schema_json_text() -> str:
    """Return the canonical serialized schema text (the exact file contents)."""
    return json.dumps(json_schema_with_terms(), indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    text = schema_json_text()

    if "--check" in argv:
        current = SCHEMA_PATH.read_text() if SCHEMA_PATH.exists() else ""
        if current != text:
            print(
                f"{SCHEMA_PATH} is out of date. Run: uv run python -m speciai.generate_schema",
                file=sys.stderr,
            )
            return 1
        print(f"{SCHEMA_PATH} is up to date.")
        return 0

    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(text)
    print(f"Wrote {SCHEMA_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
