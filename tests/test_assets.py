import shutil
from pathlib import Path

import pytest

from movelyth.assets import (
    AssetError,
    credit_lines,
    load_library,
    register,
    resolve,
    stage_for_render,
)


def png(tmp_path: Path, name: str = "photo.png") -> Path:
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    return path


def test_register_records_hash_and_provenance(tmp_path):
    source = png(tmp_path)
    entry = register(tmp_path, source, asset_id="my_photo", source="用户拍摄", author="wenxvn",
                     license="自有素材", scope="本片使用")
    assert entry["sha256"] and entry["bytes"] > 0
    library = load_library(tmp_path)
    assert "my_photo" in library["assets"]
    resolved = resolve(tmp_path, "my_photo")
    assert resolved.is_file() and resolved.name == "my_photo.png"
    assert "自有素材" in credit_lines(tmp_path, ["my_photo"])[0]


def test_register_refuses_overwrite_and_missing_license(tmp_path):
    source = png(tmp_path)
    register(tmp_path, source, asset_id="shot", source="用户拍摄", author="a", license="自有素材")
    with pytest.raises(AssetError, match="已存在"):
        register(tmp_path, source, asset_id="shot", source="用户拍摄", author="a", license="自有素材")
    with pytest.raises(AssetError, match="license"):
        register(tmp_path, source, asset_id="other", source="用户拍摄", author="a", license="  ")
    with pytest.raises(AssetError, match="小写"):
        register(tmp_path, source, asset_id="MyPhoto", source="x", author="a", license="b")


def test_unknown_type_and_oversized_asset_are_rejected(tmp_path):
    bad = tmp_path / "clip.mp4"
    bad.write_bytes(b"0")
    with pytest.raises(AssetError, match="不支持"):
        register(tmp_path, bad, asset_id="clip", source="x", author="a", license="b")
    big = tmp_path / "big.png"
    big.write_bytes(b"0" * (40 * 1024 * 1024 + 1))
    with pytest.raises(AssetError, match="40MB"):
        register(tmp_path, big, asset_id="big", source="x", author="a", license="b")


def test_tampered_file_is_detected(tmp_path):
    source = png(tmp_path)
    register(tmp_path, source, asset_id="shot", source="用户拍摄", author="a", license="自有素材")
    target = tmp_path / "assets" / "files" / "shot.png"
    target.write_bytes(b"changed")
    with pytest.raises(AssetError, match="hash"):
        resolve(tmp_path, "shot")


def test_missing_license_field_in_hand_edited_library_is_rejected(tmp_path):
    import json

    source = png(tmp_path)
    register(tmp_path, source, asset_id="shot", source="用户拍摄", author="a", license="自有素材")
    path = tmp_path / "assets" / "library.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["assets"]["shot"]["license"] = ""
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(AssetError, match="授权信息"):
        resolve(tmp_path, "shot")


def test_unknown_asset_is_reported_not_silently_skipped(tmp_path):
    with pytest.raises(AssetError, match="asset-add"):
        resolve(tmp_path, "not_registered")


def test_stage_for_render_copies_into_public_dir(tmp_path):
    source = png(tmp_path)
    register(tmp_path, source, asset_id="shot", source="用户拍摄", author="a", license="自有素材")
    destination = tmp_path / "job" / "assets"
    name = stage_for_render(tmp_path, "shot", destination)
    assert name == "asset-shot.png" and (destination / name).is_file()
    assert shutil.os.path.getsize(destination / name) == source.stat().st_size
