"""Local asset library with explicit provenance and license bookkeeping.

Only files the user deliberately registered are usable by the renderer.  Every
entry records the file hash, origin, author, license and scope, and is verified
before a render.  Nothing is downloaded automatically.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .util import atomic_json, file_hash, now, read_json

LIBRARY = "library.json"
ASSET_DIR = "files"
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
REQUIRED_FIELDS = ("source", "author", "license", "scope")
MAX_BYTES = 40 * 1024 * 1024


class AssetError(RuntimeError):
    pass


def library_root(workspace: Path) -> Path:
    return workspace / "assets"


def load_library(workspace: Path) -> dict:
    """Read the library, defaulting fields added after earlier registrations."""
    path = library_root(workspace) / LIBRARY
    if not path.is_file():
        return {"version": 1, "assets": {}}
    data = read_json(path)
    if not isinstance(data.get("assets"), dict):
        raise AssetError("素材库格式无效：assets 必须是对象")
    for entry in data["assets"].values():
        entry.setdefault("valid", True)
        entry.setdefault("used_by_episodes", [])
    return data


def verify_entry(workspace: Path, asset_id: str, entry: dict) -> Path:
    """Return the verified file path, or raise with the concrete reason."""
    if entry.get("valid") is False:
        raise AssetError(f"素材 {asset_id} 已被标记为失效：{entry.get('invalid_reason') or '需重新登记'}")
    missing = [field for field in REQUIRED_FIELDS if not str(entry.get(field) or "").strip()]
    if missing:
        raise AssetError(f"素材 {asset_id} 缺少授权信息：{', '.join(missing)}")
    target = (library_root(workspace) / ASSET_DIR / str(entry.get("file") or "")).resolve()
    if not target.is_relative_to((library_root(workspace) / ASSET_DIR).resolve()):
        raise AssetError(f"素材 {asset_id} 的路径逃逸出素材目录")
    if not target.is_file():
        raise AssetError(f"素材 {asset_id} 的文件不存在：{target.name}")
    if target.suffix.lower() not in ALLOWED_SUFFIXES:
        raise AssetError(f"素材 {asset_id} 的类型不受支持：{target.suffix}")
    if file_hash(target) != entry.get("sha256"):
        raise AssetError(f"素材 {asset_id} 的文件已变化，与登记 hash 不一致")
    return target


def register(workspace: Path, source_file: Path, *, asset_id: str, source: str, author: str,
             license: str, scope: str = "本片使用", subject: str = "", action: str = "",
             setting: str = "", tags: list[str] | None = None, focus: tuple[float, float] | None = None,
             subject_box: dict | None = None, authenticity: str = "illustration") -> dict:
    """Copy a user-confirmed file into the controlled library and record provenance."""
    if not asset_id or not asset_id.replace("_", "").isalnum() or not asset_id[0].isalpha():
        raise AssetError("素材 id 只能是小写字母开头、字母/数字/下划线")
    if not asset_id.islower():
        raise AssetError("素材 id 必须小写")
    source_file = Path(source_file).resolve()
    if not source_file.is_file():
        raise AssetError(f"素材文件不存在：{source_file}")
    if source_file.suffix.lower() not in ALLOWED_SUFFIXES:
        raise AssetError(f"不支持的素材类型：{source_file.suffix}（支持 png/jpg/webp/svg）")
    if source_file.stat().st_size > MAX_BYTES:
        raise AssetError("素材超过 40MB 上限")
    for field, value in (("source", source), ("author", author), ("license", license), ("scope", scope)):
        if not str(value or "").strip():
            raise AssetError(f"素材需要 {field}")
    root = library_root(workspace)
    files = root / ASSET_DIR
    files.mkdir(parents=True, exist_ok=True)
    data = load_library(workspace)
    if asset_id in data["assets"]:
        raise AssetError(f"素材 id 已存在：{asset_id}（不会静默覆盖）")
    target = files / f"{asset_id}{source_file.suffix.lower()}"
    shutil.copy2(source_file, target)
    entry = {"file": target.name, "sha256": file_hash(target), "source": source, "author": author,
             "license": license, "scope": scope, "added_at": now(),
             "bytes": target.stat().st_size, "valid": True, "used_by_episodes": [],
             # Optional shot-matching metadata: without it a picture can only be found
             # by file name, and a keyword hit cannot be checked against the sentence.
             "subject": str(subject or "").strip(), "action": str(action or "").strip(),
             "setting": str(setting or "").strip(), "tags": [str(tag) for tag in (tags or [])][:8],
             "authenticity": authenticity if authenticity in {"evidence", "atmosphere", "illustration"}
             else "illustration"}
    if focus:
        entry["focus"] = [float(focus[0]), float(focus[1])]
    if subject_box:
        entry["subject_box"] = {key: float(subject_box[key]) for key in ("x", "y", "w", "h")}
    data["assets"][asset_id] = entry
    atomic_json(root / LIBRARY, data)
    return entry


def resolve(workspace: Path, asset_id: str) -> Path:
    data = load_library(workspace)
    entry = data["assets"].get(asset_id)
    if not entry:
        raise AssetError(f"素材库中没有 {asset_id}；先运行 movelyth asset-add 登记并确认授权")
    return verify_entry(workspace, asset_id, entry)


def credit_lines(workspace: Path, asset_ids: list[str]) -> list[str]:
    data = load_library(workspace)
    lines = []
    for asset_id in sorted(set(asset_ids)):
        entry = data["assets"].get(asset_id)
        if not entry:
            continue
        lines.append(f"- 素材 `{asset_id}`：{entry['author']} · {entry['license']} · 来源 {entry['source']}")
    return lines


def mark_used(workspace: Path, asset_ids: list[str], episode_id: int) -> list[str]:
    """Record which episodes reference each asset (the 引用任务 column)."""
    data = load_library(workspace)
    touched = []
    for asset_id in sorted(set(asset_ids)):
        entry = data["assets"].get(asset_id)
        if not entry:
            continue
        used = list(entry.get("used_by_episodes") or [])
        if episode_id not in used:
            used.append(episode_id)
            entry["used_by_episodes"] = sorted(used)
            touched.append(asset_id)
    if touched:
        atomic_json(library_root(workspace) / LIBRARY, data)
    return touched


def check_library(workspace: Path) -> list[dict]:
    """Re-verify every registered asset and persist the 有效性 result."""
    data = load_library(workspace)
    report = []
    changed = False
    for asset_id, entry in sorted(data["assets"].items()):
        try:
            verify_entry(workspace, asset_id, entry)
            status, reason = "valid", ""
        except AssetError as exc:
            status, reason = "invalid", str(exc)
        if (entry.get("valid") is not False) != (status == "valid"):
            entry["valid"] = status == "valid"
            entry["invalid_reason"] = reason
            changed = True
        report.append({"id": asset_id, "status": status, "reason": reason,
                       "used_by_episodes": entry.get("used_by_episodes") or []})
    if changed:
        atomic_json(library_root(workspace) / LIBRARY, data)
    return report


def stage_for_render(workspace: Path, asset_id: str, destination: Path) -> str:
    """Copy a verified library asset into the Remotion public directory."""
    source = resolve(workspace, asset_id)
    destination.mkdir(parents=True, exist_ok=True)
    name = f"asset-{asset_id}{source.suffix.lower()}"
    shutil.copy2(source, destination / name)
    return name
