from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TIMEZONE = "Asia/Shanghai"


class TimezoneError(ValueError):
    """An explicitly configured timezone could not be resolved."""


def display_timezone() -> str:
    """Local timezone for human-facing timestamps (configurable, not hardcoded)."""
    return os.getenv("MOVELYTH_TZ") or DEFAULT_TIMEZONE


def resolve_timezone(zone: str | None = None) -> ZoneInfo:
    """Resolve an IANA timezone, failing loudly instead of silently using +08:00.

    Windows has no system tz database, so ``tzdata`` is a declared dependency; a
    missing database is reported as such rather than disguised as a valid offset.
    An unset ``MOVELYTH_TZ`` still means the documented default (Asia/Shanghai).
    """
    name = zone or display_timezone()
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        if zone is None and not os.getenv("MOVELYTH_TZ"):
            raise TimezoneError(
                f"默认时区 {name} 无法解析：缺少 IANA 时区数据（请安装 tzdata）") from exc
        raise TimezoneError(
            f"无效时区 {name!r}：请设置 IANA 时区名（如 UTC、Asia/Taipei），"
            "或删除 MOVELYTH_TZ 以使用默认 Asia/Shanghai；若时区名正确请安装 tzdata") from exc


def now() -> str:
    """Timezone-aware ISO timestamp.

    Historical rows keep whatever offset they were written with (all ``+08:00``),
    so switching the display timezone never invalidates stored records.
    """
    return datetime.now(resolve_timezone()).isoformat(timespec="seconds")


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".write-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def run(command: list[str], *, cwd: Path | None = None, timeout: int = 600, log: Path | None = None):
    """Never invoke a shell; keep child output in a task-local log."""
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
    stream = log.open("w", encoding="utf-8") if log else None
    try:
        proc = subprocess.Popen(command, cwd=cwd, stdout=stream if stream else subprocess.PIPE,
                                stderr=subprocess.STDOUT if stream else subprocess.PIPE,
                                text=True, encoding="utf-8", errors="replace",
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                start_new_session=os.name != "nt")
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            if proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW, check=False)
                else:
                    os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=15)
            raise
        if proc.returncode:
            if log:
                raise RuntimeError(f"外部程序失败，退出码 {proc.returncode}；详见 {log}")
            raise subprocess.CalledProcessError(proc.returncode, command, stdout, stderr)
        return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
    finally:
        if stream:
            stream.close()
