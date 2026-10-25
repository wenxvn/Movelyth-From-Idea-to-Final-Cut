import json
from pathlib import Path

import pytest

from movelyth.agents import CodexAgents, MockProvider, create_provider, resolve_codex
from movelyth.models import Review
from tests.factories import review_payload


def test_mock_provider_validates_contract_and_records_calls(tmp_path):
    provider = MockProvider({"reviewer": review_payload()})
    result = provider.call("reviewer", {"stage": "script"}, Review, tmp_path / "reviewer")
    assert isinstance(result, Review) and result.passed
    assert provider.calls == ["reviewer"]
    assert (tmp_path / "reviewer" / "prompt.txt").is_file()
    assert (tmp_path / "reviewer" / "response.json").is_file()
    with pytest.raises(RuntimeError, match="缺少"):
        provider.call("director", {}, Review, tmp_path / "director")


def test_mock_provider_rejects_invalid_payload(tmp_path):
    provider = MockProvider({"reviewer": {"passed": True}})
    with pytest.raises(Exception):
        provider.call("reviewer", {}, Review, tmp_path / "reviewer")


def test_create_provider_resolves_mock_directory(tmp_path):
    directory = tmp_path / "mock"
    directory.mkdir()
    (directory / "reviewer.json").write_text(json.dumps(review_payload()), encoding="utf-8")
    provider = create_provider(tmp_path, {"provider": "mock", "mock_dir": "mock"})
    assert isinstance(provider, MockProvider) and "reviewer" in provider.responses
    with pytest.raises(ValueError, match="目录不存在"):
        create_provider(tmp_path, {"provider": "mock", "mock_dir": "missing"})
    with pytest.raises(ValueError, match="未知 provider"):
        create_provider(tmp_path, {"provider": "some-cloud"})


def test_codex_usage_is_parsed_from_event_log(tmp_path):
    log = tmp_path / "events.log"
    log.write_text("\n".join([
        json.dumps({"type": "started"}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 34}}),
        "not json",
    ]), encoding="utf-8")
    assert CodexAgents._usage(log) == {"input_tokens": 12, "output_tokens": 34}


def test_codex_executable_can_be_configured(monkeypatch, tmp_path):
    fake = tmp_path / "codex.exe"
    fake.write_bytes(b"stub")
    monkeypatch.setenv("MOVELYTH_CODEX", str(fake))
    assert resolve_codex() == str(fake)
    monkeypatch.setenv("MOVELYTH_CODEX", str(tmp_path / "missing.exe"))
    assert resolve_codex() is None


def test_codex_provider_is_the_default_and_never_silently_switches(tmp_path, monkeypatch):
    monkeypatch.setattr("movelyth.agents.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="Codex"):
        create_provider(tmp_path, {"provider": "codex"})
    with pytest.raises(ValueError, match="codex provider"):
        CodexAgents(Path(tmp_path), {"provider": "mock"})
