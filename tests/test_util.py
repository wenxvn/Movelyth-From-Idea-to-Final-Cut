from movelyth.util import display_timezone, now


def test_timestamps_are_configurable_and_offset_aware(monkeypatch):
    monkeypatch.delenv("MOVELYTH_TZ", raising=False)
    stamp = now()
    assert stamp[4] == "-" and stamp[10] == "T" and ("+" in stamp or "Z" in stamp)
    monkeypatch.setenv("MOVELYTH_TZ", "UTC")
    assert now().endswith("+00:00")
    assert display_timezone() == "UTC"
    monkeypatch.setenv("MOVELYTH_TZ", "Not/AZone")
    fallback = now()
    assert fallback.endswith("+08:00")


def test_legacy_timestamps_keep_their_own_offset(monkeypatch):
    from datetime import datetime

    monkeypatch.setenv("MOVELYTH_TZ", "UTC")
    legacy = "2026-10-25T15:34:54+08:00"
    parsed = datetime.fromisoformat(legacy)
    current = datetime.fromisoformat(now())
    assert parsed.utcoffset().total_seconds() == 8 * 3600
    assert current.utcoffset().total_seconds() == 0
    assert current > parsed.replace(tzinfo=parsed.tzinfo) - (current - current)
