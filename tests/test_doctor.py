"""S1-01: tool discovery, doctor reporting and timezone strictness."""
import json
import shutil
from datetime import datetime

import pytest

from movelyth import media
from movelyth.cli import doctor, font_status


def test_ffprobe_candidates_prefers_the_configured_path(monkeypatch, tmp_path):
    configured = tmp_path / "ffprobe-custom"
    monkeypatch.setenv("MOVELYTH_FFPROBE", str(configured))
    candidates = media.ffprobe_candidates()
    assert candidates[0] == configured
    # The Remotion compositor binary stays a documented fallback, not a silent default.
    assert any("compositor-" in str(path) for path in candidates)


def test_missing_ffprobe_names_every_checked_location(monkeypatch, tmp_path):
    missing = tmp_path / "nope" / "ffprobe"
    monkeypatch.setattr(media, "ffprobe_candidates", lambda: [missing])
    with pytest.raises(RuntimeError) as caught:
        media.ffprobe()
    message = str(caught.value)
    assert str(missing) in message and "npm ci --prefix studio" in message


def test_ffprobe_resolves_the_compositor_binary(monkeypatch, tmp_path):
    binary = tmp_path / "ffprobe"
    binary.write_bytes(b"stub")
    monkeypatch.setattr(media, "ffprobe_candidates", lambda: [tmp_path / "absent", binary])
    assert media.ffprobe() == str(binary)


def _doctor_root(tmp_path):
    config = tmp_path / "movelyth.toml"
    shutil.copy(Path(__file__).parents[1] / "movelyth.toml", config)
    return tmp_path


def test_doctor_reports_missing_ffprobe_instead_of_raising(monkeypatch, tmp_path):
    root = _doctor_root(tmp_path)
    monkeypatch.setattr(media, "ffprobe_candidates", lambda: [tmp_path / "absent" / "ffprobe"])
    monkeypatch.delenv("MOVELYTH_TZ", raising=False)
    report = doctor(root)
    assert report["ffprobe"] is None
    assert report["tools"]["ffprobe"]["version"] is None
    assert any("ffprobe" in reason for reason in report["reasons"])
    assert report["ready_for_generation"] is False
    json.dumps(report)  # the report stays serialisable for CI logs


def test_doctor_reports_tools_fonts_and_timezone(monkeypatch, tmp_path):
    root = _doctor_root(tmp_path)
    monkeypatch.delenv("MOVELYTH_TZ", raising=False)
    report = doctor(root)
    assert report["timezone"]["ok"] is True
    assert report["timezone"]["resolved"] == "Asia/Shanghai"
    assert report["fonts"]["ok"] is True
    assert report["tools"]["ffmpeg"]["path"]
    assert report["tools"]["ffmpeg"]["version"]
    assert report["tools"]["ffprobe"]["path"]
    assert report["tools"]["ffprobe"]["searched"]


def test_doctor_turns_a_bad_timezone_into_a_reason(monkeypatch, tmp_path):
    root = _doctor_root(tmp_path)
    monkeypatch.setenv("MOVELYTH_TZ", "Not/AZone")
    report = doctor(root)
    assert report["timezone"]["ok"] is False
    assert "无效时区" in report["timezone"]["error"]
    assert report["ready_for_generation"] is False
    assert any("无效时区" in reason for reason in report["reasons"])
    # The report itself still has a usable timestamp, in UTC, instead of crashing.
    assert datetime.fromisoformat(report["checked_at"]).utcoffset().total_seconds() == 0


def test_font_status_is_a_plain_capability_report():
    status = font_status()
    assert set(status) == {"found", "missing", "ok"}
    assert status["ok"] == bool(status["found"])


from pathlib import Path  # noqa: E402  (used by _doctor_root, kept after the imports for readability)
