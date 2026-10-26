"""Publishing package text: platform-specific copy plus an audit summary.

Everything here is derived from data already produced by the pipeline (film,
research, quality report).  Uploading stays manual; nothing here claims a video
was published or performed well.
"""
from __future__ import annotations

from .models import Film, Research

PLATFORMS = [("long", "B站", "横版"), ("short", "抖音", "竖版")]


def credits(research: Research, *, external_media: bool = False) -> str:
    lines = [f"- [{source.label}]({source.url})：{source.supports}" for source in research.sources]
    media = ("本片使用了经用户确认许可的本地素材，授权依据见素材台账。"
             if external_media else
             "本片未直接使用外部图像/视频；山水图像为程序绘制，低秩重建由 NumPy SVD 计算。")
    return "\n".join(lines) + (
        "\n\n画面：Movelyth 程序动画与受控图层（图表数据由本地受控 JSON 提供，示意数据均已标注）。"
        f"\n{media}\n配乐和音效：Movelyth 原创程序合成。旁白：Edge TTS。"
        "\n制作：Movelyth — 幕绎 / Remotion。来源链接不代表取得第三方素材转载许可。\n")


def publishing_copy(film: Film, research: Research, *, external_media: bool = False) -> str:
    """Per-platform section with the chosen title, candidates, description and tags."""
    blocks = []
    for cut_name, platform, orientation in PLATFORMS:
        cut = getattr(film, cut_name)
        candidates = [title for title in cut.title_candidates if title.strip() and title != cut.title]
        block = [f"## {platform}（{orientation}）", "",
                 f"**采用标题**：{cut.title}", ""]
        if candidates:
            block.extend(["**备选标题**（人工确认后再用）："] +
                         [f"{index}. {title}" for index, title in enumerate(candidates, 1)] + [""])
        if cut.cover_caption:
            block.extend([f"**封面文案**：{cut.cover_caption}", ""])
        block.extend([f"**简介**：{cut.description}", "",
                      "**标签**：" + " ".join("#" + tag.lstrip("#") for tag in cut.tags), ""])
        blocks.append("\n".join(block))
    return "\n".join(blocks) + "\n## 来源与署名\n" + credits(research, external_media=external_media)


def audit_summary(quality: dict, *, episode: str, schema_version: int) -> str:
    """A human-readable checklist of what was and was not verified."""
    audio = quality.get("audio") or {}
    technical = quality.get("technical") or {}
    lines = [f"# 交付审计 · {episode}", "",
             f"- 制作模式：{quality.get('creation_mode')}（provider: {quality.get('provider')}）",
             f"- Scene DSL 版本：{schema_version}",
             "- 机器检查："]
    for cut, report in technical.items():
        failed = [name for name, ok in (report.get("checks") or {}).items() if not ok]
        loud = report.get("loudness") or {}
        lufs, peak = loud.get("integrated_lufs"), loud.get("true_peak_db")
        if lufs is None:
            measured = "响度未测"
        elif peak is None:
            measured = f"{lufs:.1f} LUFS"
        else:
            measured = f"{lufs:.1f} LUFS / 峰值 {peak:.1f} dBTP"
        lines.append(f"  - {cut}：{'全部通过' if not failed else '未通过 ' + ', '.join(failed)}；{measured}")
        motion = report.get("motion") or {}
        if not motion:
            lines.append("    - 运动分析：未执行")
        elif motion.get("status") == "unavailable":
            lines.append(f"    - 运动分析：未执行（{motion.get('reason')}）")
        else:
            frozen = len(motion.get("frozen_scenes") or [])
            runs = len(motion.get("full_frame_runs") or [])
            detail = (f"连续静止 ≥5 秒的镜头 {frozen} 个" if frozen
                      else "无连续静止 ≥5 秒的镜头")
            if runs:
                detail += f"，整帧运动 {runs} 段（需人工确认是否为设计意图）"
            lines.append(f"    - 运动分析：{detail}")
    lines.append("- 音频机器检查：")
    for cut, report in audio.items():
        terms = report.get("key_terms") or {}
        lines.append(f"  - {cut}：ASR {report.get('asr', {}).get('status')}、"
                     f"长静音 {report.get('silence', {}).get('status')}、"
                     f"混音/原声 {report.get('ducking', {}).get('status')}、"
                     f"关键术语 {terms.get('status')}")
    human = quality.get("human_review") or {}
    lines.extend([
        "- 人工验证：",
        f"  - 完整观看：{'是' if human.get('watched_full_video') else '未执行'}",
        f"  - 完整实听：{'是' if human.get('listened_audio') else '未执行'}",
        "- 来源：见 `质检报告.json` 的 `source_fetches`（抓取成功不等于事实已核验）",
        "- 上传：由用户手动完成；`ready` 不等于已发布",
    ])
    warnings = quality.get("script_warnings") or []
    if warnings:
        lines.append("- 脚本校验 warnings：" + "；".join(warnings[:5]))
    return "\n".join(lines) + "\n"
