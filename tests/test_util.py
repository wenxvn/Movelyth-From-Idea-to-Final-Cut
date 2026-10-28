import pytest

from movelyth.util import TimezoneError, display_timezone, now, resolve_timezone


def test_timestamps_are_configurable_and_offset_aware(monkeypatch):
    monkeypatch.delenv("MOVELYTH_TZ", raising=False)
    stamp = now()
    assert stamp[4] == "-" and stamp[10] == "T" and ("+" in stamp or "Z" in stamp)
    # Unset means the documented default, never the machine's local zone.
    assert now().endswith("+08:00")
    monkeypatch.setenv("MOVELYTH_TZ", "UTC")
    assert now().endswith("+00:00")
    assert display_timezone() == "UTC"


def test_invalid_timezone_is_a_configuration_error(monkeypatch):
    """An explicitly configured bad zone must not be silently replaced by +08:00."""
    monkeypatch.setenv("MOVELYTH_TZ", "Not/AZone")
    with pytest.raises(TimezoneError) as caught:
        now()
    assert "无效时区" in str(caught.value) and "MOVELYTH_TZ" in str(caught.value)
    with pytest.raises(TimezoneError):
        resolve_timezone()


def test_explicit_zone_argument_overrides_environment(monkeypatch):
    monkeypatch.setenv("MOVELYTH_TZ", "Not/AZone")
    assert str(resolve_timezone("UTC")) == "UTC"


def test_legacy_timestamps_keep_their_own_offset(monkeypatch):
    from datetime import datetime

    monkeypatch.setenv("MOVELYTH_TZ", "UTC")
    legacy = "2026-10-25T15:34:54+08:00"
    parsed = datetime.fromisoformat(legacy)
    current = datetime.fromisoformat(now())
    assert parsed.utcoffset().total_seconds() == 8 * 3600
    assert current.utcoffset().total_seconds() == 0
