"""The model endpoint is configurable, and every setting resolves as documented.

The pipeline talks to any OpenAI-compatible provider. That holds only while a flag
beats the environment beats the default, and while a field only some providers
understand is sent only when asked for.
"""

import argparse
import ast
import inspect
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from speciai.cli import DEFAULT_LLM_BASE_URL, _add_llm_options, _cmd_serve, _env
from speciai.extract import (
    DEFAULT_TEMPERATURE,
    DEFAULT_THINKING,
    DISABLE_THINKING,
    ENABLE_THINKING,
    Extractor,
    _LabelReading,
    parse_temperature,
    thinking_extra_body,
)
from speciai.web.app import create_app


def _parse(argv: list[str]):
    parser = argparse.ArgumentParser()
    _add_llm_options(parser)
    return parser.parse_args(argv)


def test_base_url_falls_back_to_the_default(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert _parse([]).llm_base_url == DEFAULT_LLM_BASE_URL


def test_environment_sets_the_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    args = _parse([])
    assert args.llm_base_url == "https://api.openai.com/v1"
    assert args.model == "gpt-4o-mini"


def test_a_flag_beats_the_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    args = _parse(["--llm-base-url", "http://localhost:8000/v1"])
    assert args.llm_base_url == "http://localhost:8000/v1"


def test_a_blank_variable_is_unset_not_an_empty_endpoint(monkeypatch):
    # Compose passes an unset variable through as "", which must not win.
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_MODEL", "")
    args = _parse([])
    assert args.llm_base_url == DEFAULT_LLM_BASE_URL
    assert args.model is None
    assert _env("LLM_MODEL") is None


def test_model_has_no_default(monkeypatch):
    # No model id suits every provider, so main() rejects a missing one.
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert _parse([]).model is None


def test_thinking_is_disabled_by_default(monkeypatch):
    # Nothing configured must still mean no thinking: it costs time per image and
    # adds nothing when the reply is a fixed schema.
    monkeypatch.delenv("LLM_THINKING", raising=False)
    assert _parse([]).thinking == DEFAULT_THINKING
    assert thinking_extra_body(_parse([]).thinking) == DISABLE_THINKING
    assert thinking_extra_body(None) == DISABLE_THINKING


def test_a_blank_thinking_variable_is_still_the_default(monkeypatch):
    monkeypatch.setenv("LLM_THINKING", "")
    assert thinking_extra_body(_parse([]).thinking) == DISABLE_THINKING


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("off", DISABLE_THINKING), ("on", ENABLE_THINKING), ("none", {})],
)
def test_thinking_choices_map_onto_the_vllm_toggle(choice, expected):
    assert thinking_extra_body(choice) == expected


def test_thinking_none_sends_no_field_at_all(monkeypatch):
    # The escape hatch for a provider that rejects fields it does not know.
    args = _parse(["--thinking", "none"])
    sent = _capture_request(monkeypatch, extra_body=thinking_extra_body(args.thinking))
    assert sent["extra_body"] == {}


def test_an_unknown_thinking_choice_raises():
    # Quietly sending no toggle would look like a slow model, not a typo.
    with pytest.raises(ValueError, match="unknown thinking choice"):
        thinking_extra_body("enabled")


def _capture_request(monkeypatch, **extractor_kwargs) -> dict:
    """Run one extraction against a stub client and return the request kwargs."""
    sent: dict = {}
    extractor = Extractor(
        base_url="http://localhost/v1", model_id="m", api_key="k", **extractor_kwargs
    )

    def parse(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        parsed=_LabelReading(), refusal=None, content=None
                    )
                )
            ],
            usage=None,
        )

    extractor._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))
    )
    monkeypatch.setattr("speciai.extract.image_data_url", lambda path: "data:,")
    extractor.run(Path("specimen.jpg"))
    return sent


def test_extractor_itself_defaults_to_no_extra_body(monkeypatch):
    # The Extractor stays provider-neutral. Choosing the toggle is the CLI's job.
    assert _capture_request(monkeypatch)["extra_body"] == {}


def test_extractor_forwards_the_extra_body_it_was_given(monkeypatch):
    sent = _capture_request(monkeypatch, extra_body=DISABLE_THINKING)
    assert sent["extra_body"] == DISABLE_THINKING


def test_temperature_defaults_to_zero_for_reproducibility(monkeypatch):
    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    assert _parse([]).temperature == DEFAULT_TEMPERATURE


def test_temperature_can_be_omitted_entirely():
    # The Claude models refuse the field at any value, so it has to go.
    assert _parse(["--temperature", "none"]).temperature is None
    assert _parse(["--temperature", "NONE"]).temperature is None


def test_temperature_reads_a_number(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "0.2")
    assert _parse([]).temperature == pytest.approx(0.2)
    assert _parse(["--temperature", "1"]).temperature == pytest.approx(1.0)


def test_a_blank_temperature_is_the_default(monkeypatch):
    monkeypatch.setenv("LLM_TEMPERATURE", "")
    assert _parse([]).temperature == DEFAULT_TEMPERATURE


def test_an_unparseable_temperature_raises():
    # Reading a typo as "use the model's default" quietly loses repeatability.
    with pytest.raises(ValueError, match="must be a number"):
        parse_temperature("cold")


def test_temperature_is_sent_by_default(monkeypatch):
    assert _capture_request(monkeypatch)["temperature"] == DEFAULT_TEMPERATURE


def test_no_temperature_field_is_sent_when_it_is_none(monkeypatch):
    # Not `temperature=None`: a provider that refuses the field refuses any value.
    assert "temperature" not in _capture_request(monkeypatch, temperature=None)


def test_serve_only_passes_options_create_app_accepts():
    """`serve` and `create_app` must not drift apart.

    Nothing else catches this. The web tests use a fake extractor, so a setting added
    to the CLI but not to the factory only fails when a real server starts, which
    means in the container and not in CI.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(_cmd_serve)))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_app"
    ]
    assert len(calls) == 1, "_cmd_serve no longer calls create_app exactly once"
    passed = {keyword.arg for keyword in calls[0].keywords if keyword.arg}
    accepted = set(inspect.signature(create_app).parameters)
    assert passed <= accepted, f"create_app rejects: {sorted(passed - accepted)}"

    # And every endpoint option the CLI offers reaches the factory, so a new flag
    # cannot be quietly dropped on the way to the server.
    parser = argparse.ArgumentParser()
    _add_llm_options(parser)
    options = {"llm_base_url", "model", "thinking", "temperature"}
    assert options <= {action.dest for action in parser._actions}
    assert {"llm_base_url", "temperature"} <= passed
