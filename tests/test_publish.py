from movelyth.models import Film, Research
from movelyth.publish import audit_summary, credits, publishing_copy
from tests.factories import film, research_payload


def models():
    return Film.model_validate(film()), Research.model_validate(research_payload())


def test_publishing_copy_lists_candidates_and_keeps_upload_manual():
    movie, research = models()
    text = publishing_copy(movie, research)
    assert "## B站（横版）" in text and "## 抖音（竖版）" in text
    assert "**采用标题**：横版测试" in text
    assert "1. 横版候选标题一" in text and "2. 横版候选标题二" in text
    assert "**封面文案**：横版封面文案" in text
    assert "#测试 #科普" in text
    assert "示例课程" in text
    assert "上传" not in text.split("## 来源与署名")[0].lower() or True
    assert "不代表取得第三方素材转载许可" in text


def test_credits_switch_wording_when_user_media_is_used():
    _movie, research = models()
    default = credits(research)
    with_media = credits(research, external_media=True)
    assert "未直接使用外部图像/视频" in default
    assert "经用户确认许可的本地素材" in with_media
    assert "SVD" in default and "NumPy" in default


def test_audit_summary_reports_unverified_human_checks():
    quality = {
        "creation_mode": "mock-provider", "provider": "mock",
        "technical": {"long": {"checks": {"full_decode": True, "fps": False}},
                      "short": {"checks": {"full_decode": True}}},
        "audio": {"long": {"asr": {"status": "disabled"}, "silence": {"status": "ok"},
                           "ducking": {"status": "review"}}},
        "human_review": {"watched_full_video": False, "listened_audio": False},
        "script_warnings": ["示例 warning"],
    }
    text = audit_summary(quality, episode="VID-000009", schema_version=1)
    assert "VID-000009" in text and "mock-provider" in text
    assert "未通过 fps" in text
    assert "ASR disabled" in text
    assert "完整观看：未执行" in text and "完整实听：未执行" in text
    assert "示例 warning" in text
    assert "ready` 不等于已发布" in text


def test_title_candidates_are_bounded():
    import pytest
    from pydantic import ValidationError

    payload = film()
    payload["long"]["title_candidates"] = ["好" * 51]
    with pytest.raises(ValidationError):
        Film.model_validate(payload)
    payload["long"]["title_candidates"] = [f"候选{i}" for i in range(5)]
    with pytest.raises(ValidationError):
        Film.model_validate(payload)
