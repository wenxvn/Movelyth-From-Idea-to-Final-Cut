import pytest

from movelyth.pipeline import VisualReviewError
from tests.conftest import make_studio


def test_visual_feedback_retries_are_bounded_and_release_lock(tmp_path, monkeypatch):
    studio = make_studio(tmp_path)
    try:
        episode = studio.create("实际审片失败")
        calls = []

        def rejected(*args):
            calls.append(1)
            raise VisualReviewError("字幕遮挡")

        monkeypatch.setattr(studio, "_produce", rejected)
        with pytest.raises(VisualReviewError):
            studio.produce(episode["id"])
        assert len(calls) == 3
        row = studio.ledger.get(episode["id"])
        assert row["status"] == "failed" and row["token"] is None
    finally:
        studio.close()


def test_execution_error_is_not_blindly_repeated(tmp_path, monkeypatch):
    studio = make_studio(tmp_path)
    try:
        episode = studio.create("执行程序失败")
        calls = []

        def failed(*args):
            calls.append(1)
            raise RuntimeError("工具缺失")

        monkeypatch.setattr(studio, "_produce", failed)
        with pytest.raises(RuntimeError):
            studio.produce(episode["id"])
        assert len(calls) == 1
        assert studio.ledger.get(episode["id"])["status"] == "failed"
    finally:
        studio.close()
