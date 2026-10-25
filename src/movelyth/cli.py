from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .ledger import BusyError
from .media import ffmpeg, ffprobe
from .pipeline import Studio, browser
from .util import now, run


def number(value: str) -> int:
    try:
        result = int(value.upper().removeprefix("VID-"))
        if result <= 0:
            raise ValueError
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("编号格式：VID-000001 或 1") from exc


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def doctor(root: Path) -> dict:
    binary = ffmpeg()
    node = shutil.which("node")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    codex = shutil.which("codex")
    check = {
        "project": str(root), "python": sys.version.split()[0], "node": node,
        "npm": npm, "codex": codex, "browser": browser(), "ffmpeg": binary,
        "ffprobe": ffprobe(),
        "renderer_installed": (root / "studio/node_modules/@remotion/renderer/package.json").is_file(),
        "config": (root / "movelyth.toml").is_file(),
        "checked_at": now(), "tts": "Edge TTS（联网，doctor 尚未调用语音服务）",
    }
    if node:
        check["node_version"] = run([node, "--version"], timeout=15).stdout.strip()
    check["ffmpeg_version"] = run([binary, "-version"], timeout=15).stdout.splitlines()[0]
    check["ready_for_generation"] = bool(node and codex and check["renderer_installed"] and check["config"])
    check["note"] = "环境检查不等同于 Codex 配额、TTS 连通性或视频生成验证"
    return check


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="movelyth", description="Movelyth — 幕绎 · From Idea to Final Cut.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Movelyth 项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="检查本地工具和配置")
    create = sub.add_parser("create", help="从一个标题自动制作完整上传包")
    create.add_argument("title")
    create.add_argument("--new", action="store_true", help="明确要求同题另做一个新任务")
    create.add_argument("--plan-only", action="store_true", help="完成真实研究/编导/审稿后停在脚本阶段")
    create.add_argument("--import-film", type=Path)
    create.add_argument("--import-research", type=Path)
    resume = sub.add_parser("resume", help="从失败/中断阶段继续，复用有效缓存")
    resume.add_argument("id", type=number)
    resume.add_argument("--plan-only", action="store_true")
    status = sub.add_parser("status", help="查看任务、失败和交付记录")
    status.add_argument("id", nargs="?", type=number)
    sub.add_parser("ideas", help="查看尚未制作的 idea 和历史反馈")
    sub.add_parser("assets", help="查看程序素材使用记录和关联成片的真实反馈")
    feedback = sub.add_parser("feedback", help="记录手动上传后的真实链接与数据")
    feedback.add_argument("id", type=number)
    feedback.add_argument("--platform", choices=["bilibili", "douyin"], required=True)
    feedback.add_argument("--url", required=True)
    feedback.add_argument("--views", type=int)
    feedback.add_argument("--likes", type=int)
    feedback.add_argument("--completion-rate", type=float)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    studio = None
    try:
        if args.command == "doctor":
            result = doctor(root)
            emit(result)
            return 0 if result["ready_for_generation"] else 1
        studio = Studio(root)
        if args.command == "create":
            episode = studio.create(args.title, new=args.new)
            print(f"Movelyth · VID-{episode['id']:06d} · {episode['title']}", flush=True)
            emit(studio.produce(episode["id"], plan_only=args.plan_only,
                                import_film=args.import_film.resolve() if args.import_film else None,
                                import_research=args.import_research.resolve() if args.import_research else None))
        elif args.command == "resume":
            emit(studio.produce(args.id, plan_only=args.plan_only))
        elif args.command == "status":
            result = studio.ledger.get(args.id) if args.id else studio.ledger.list()
            if args.id:
                result["history"] = studio.ledger.history(args.id)
            emit(result)
        elif args.command == "ideas":
            emit(studio.ledger.context())
        elif args.command == "assets":
            emit(studio.asset_observations())
        elif args.command == "feedback":
            metrics = {k: v for k, v in {"views": args.views, "likes": args.likes,
                       "completion_rate": args.completion_rate}.items() if v is not None}
            if not args.url.startswith("https://"):
                raise ValueError("发布链接需以 https:// 开头")
            if any(v < 0 for v in metrics.values()) or (args.completion_rate is not None and args.completion_rate > 1):
                raise ValueError("计数不可为负，完播率范围为 0–1")
            studio.ledger.add_feedback(args.id, args.platform, args.url, metrics)
            studio.export_index()
            emit({"recorded": True, "metrics": metrics, "missing_metrics": "unknown"})
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f"Movelyth 停在可恢复状态：{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 130 if isinstance(exc, KeyboardInterrupt) else (3 if isinstance(exc, BusyError) else 1)
    finally:
        if studio:
            studio.close()


if __name__ == "__main__":
    raise SystemExit(main())
