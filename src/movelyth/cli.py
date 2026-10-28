from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .ledger import BusyError
from .media import ffmpeg, ffprobe, tool_version
from .openai_compat import probe_endpoint
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


CHINESE_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def file_version(path: str | None) -> str | None:
    """Product version of a GUI binary without launching it.

    ``chrome.exe -version`` opens a browser window on Windows, so the executable
    metadata is read instead of executing the program.
    """
    if not path:
        return None
    if os.name == "nt":
        try:
            result = run(["powershell", "-NoProfile", "-Command",
                          f"(Get-Item -LiteralPath '{path}').VersionInfo.ProductVersion"], timeout=20)
            return (result.stdout or "").strip() or None
        except (OSError, RuntimeError):
            return None
    return tool_version(path)


def font_status() -> dict:
    """Which CJK fonts the renderer can actually fall back to on this machine."""
    found = [path for path in CHINESE_FONT_CANDIDATES if Path(path).is_file()]
    return {"found": found, "missing": [p for p in CHINESE_FONT_CANDIDATES if p not in found],
            "ok": bool(found)}


def doctor(root: Path) -> dict:
    """Environment table with actionable reasons; a missing tool is reported, not raised."""
    from .agents import resolve_codex
    from .audioqc import asr_status
    from .media import ffprobe_candidates, tool_version
    from .pipeline import settings
    from .scenedsl import renderer_contract
    from .util import TimezoneError, display_timezone, resolve_timezone

    binary = ffmpeg()
    node = shutil.which("node")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    codex = resolve_codex()
    config = settings(root) if (root / "movelyth.toml").is_file() or os.getenv("MOVELYTH_CONFIG") else {}
    provider = (config.get("agents") or {}).get("provider", "codex")
    try:
        probe_binary, probe_error = ffprobe(), None
    except RuntimeError as exc:
        probe_binary, probe_error = None, str(exc)
    reasons: list[str] = []
    if probe_error:
        reasons.append(probe_error)
    fonts = font_status()
    if not fonts["ok"]:
        reasons.append("未找到可用的中文字体；字幕与图表文字会回退到不可控字体")
    try:
        zone = resolve_timezone()
        timezone_status = {"configured": display_timezone(), "resolved": str(zone),
                           "offset": now()[-6:], "ok": True}
        checked_at = now()
    except TimezoneError as exc:
        # A bad MOVELYTH_TZ must be reported, not turned into a crash or a fake +08:00.
        from datetime import datetime, timezone

        timezone_status = {"configured": display_timezone(), "ok": False, "error": str(exc)}
        reasons.append(str(exc))
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        browser_path = browser()
    except ValueError as exc:
        browser_path = None
        reasons.append(str(exc))
    check = {
        "project": str(root), "python": sys.version.split()[0], "node": node,
        "npm": npm, "codex": codex, "browser": browser_path, "ffmpeg": binary,
        "ffprobe": probe_binary,
        "renderer_installed": (root / "studio/node_modules/@remotion/renderer/package.json").is_file(),
        "config": bool(config),
        "provider": provider,
        "schema_version": renderer_contract()["schema_version"],
        "asr": asr_status(),
        "checked_at": checked_at, "tts": "Edge TTS（联网，doctor 尚未调用语音服务）",
        "fonts": fonts,
        "timezone": timezone_status,
        "tools": {
            "ffmpeg": {"path": binary, "version": tool_version(binary)},
            "ffprobe": {"path": probe_binary,
                        "version": tool_version(probe_binary) if probe_binary else None,
                        "searched": [str(p) for p in ffprobe_candidates()]},
            "browser": {"path": browser_path, "version": file_version(browser_path)},
        },
    }
    if node:
        check["node_version"] = run([node, "--version"], timeout=15).stdout.strip()
    check["ffmpeg_version"] = check["tools"]["ffmpeg"]["version"]
    needs_codex = provider == "codex"
    check["ready_for_generation"] = bool(node and check["renderer_installed"] and check["config"]
                                        and fonts["ok"] and timezone_status["ok"]
                                        and (codex if needs_codex else True))
    if provider == "openai":
        agents = (config.get("agents") or {})
        env_name = str(agents.get("api_key_env") or "OPENAI_API_KEY")
        endpoint = {
            "base_url": agents.get("base_url"),
            "model": agents.get("model"),
            "api_key_env": env_name,
            "api_key_present": bool(os.getenv(env_name)),
            "structured_output": agents.get("structured_output", "auto"),
            "vision": agents.get("vision", "auto"),
        }
        check["endpoint"] = endpoint
        missing = [name for name in ("base_url", "model") if not agents.get(name)]
        if missing:
            endpoint["reason"] = "缺少 " + "、".join(f"agents.{name}" for name in missing)
        elif not endpoint["api_key_present"]:
            endpoint["reason"] = f"环境变量 {env_name} 未设置"
        if endpoint.get("reason"):
            reasons.append(endpoint["reason"])
        check["ready_for_generation"] = bool(check["ready_for_generation"] and not endpoint.get("reason"))
        check["endpoint_note"] = "doctor 只检查配置与密钥是否存在；连通性请运行 movelyth probe"
    if provider == "codex" and not codex:
        reasons.append('provider=codex 但未找到 codex 可执行文件；安装 Codex 或改用 [agents].provider = "openai"')
    if provider == "mock":
        check["mock_note"] = "provider=mock：只用于离线测试与预览，产物不是真实模型创作"
    check["reasons"] = reasons
    check["note"] = "环境检查不等同于 Codex 配额、TTS 连通性或视频生成验证"
    return check


def read_brief(path: Path | None) -> str | None:
    if path is None:
        return None
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"brief 文件不存在：{path}")
    if path.stat().st_size > 64 * 1024:
        raise ValueError("brief 文件超过 64KB，请只保留背景、受众、风格与重点")
    return path.read_text(encoding="utf-8-sig")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="movelyth", description="Movelyth — 幕绎 · From Idea to Final Cut.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Movelyth 项目根目录")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="检查本地工具和配置")
    probe = sub.add_parser("probe", help="探测 [OI] 兼容端点：连通性、JSON 输出与图片能力")
    probe.add_argument("--base-url", help="默认取 agents.base_url")
    probe.add_argument("--model", help="默认取 agents.model")
    probe.add_argument("--api-key-env", help="默认取 agents.api_key_env")
    probe.add_argument("--image", type=Path, help="可选：附带一张图片验证视觉能力")
    create = sub.add_parser("create", help="从一个标题（可选 brief）自动制作完整上传包")
    create.add_argument("title")
    create.add_argument("--new", action="store_true", help="明确要求同题另做一个新任务")
    create.add_argument("--plan-only", action="store_true", help="完成真实研究/编导/审稿后停在脚本阶段")
    create.add_argument("--preview", action="store_true", help="只生成故事板与低分辨率片段，不渲染成片")
    create.add_argument("--brief-file", type=Path, help="可选：背景/受众/风格/重点的文本或 Markdown 文件")
    create.add_argument("--import-film", type=Path)
    create.add_argument("--import-research", type=Path)
    resume = sub.add_parser("resume", help="从失败/中断阶段继续，复用有效缓存")
    resume.add_argument("id", type=number)
    resume.add_argument("--plan-only", action="store_true")
    resume.add_argument("--preview", action="store_true")
    resume.add_argument("--reuse-script", action="store_true",
                        help="复用已审 film.json（仅渲染器修复时用），不重新调用编导")
    preview = sub.add_parser("preview", help="生成故事板与短预览（低成本预检）")
    preview.add_argument("id", type=number)
    revise = sub.add_parser("revise", help="按审阅意见局部修改镜头，生成新 revision")
    revise.add_argument("id", type=number)
    revise.add_argument("--notes", type=Path, required=True, help="审阅意见文本，需包含镜头编号或 scene id")
    status = sub.add_parser("status", help="查看任务、失败和交付记录")
    status.add_argument("id", nargs="?", type=number)
    sub.add_parser("ideas", help="查看尚未制作的 idea 和历史反馈")
    suggest = sub.add_parser("suggest", help="根据历史与当前能力提出候选选题（不制作）")
    suggest.add_argument("--count", type=int, default=3, help="候选数量 1–5")
    daily = sub.add_parser("daily", help="选一个可支持的候选并调用同一制作流水线（不自动定时）")
    daily.add_argument("--count", type=int, default=3)
    daily.add_argument("--preview", action="store_true", help="只生成故事板预览")
    sub.add_parser("assets", help="查看程序素材使用记录和关联成片的真实反馈")
    asset_add = sub.add_parser("asset-add", help="登记本地素材（记录 hash、作者、许可），不自动下载")
    asset_add.add_argument("file", type=Path)
    asset_add.add_argument("--id", required=True, help="小写标识符，脚本里用 data_ref 引用")
    asset_add.add_argument("--source", required=True, help="素材来源说明")
    asset_add.add_argument("--author", required=True)
    asset_add.add_argument("--license", required=True, help="授权依据，例如 自有素材 / CC BY 4.0")
    asset_add.add_argument("--scope", default="本片使用")
    sub.add_parser("asset-check", help="重新校验素材库（hash/授权/有效性）并标记失效项")
    sub.add_parser("schema", help="输出 Scene DSL v1 的 JSON Schema")
    sub.add_parser("components", help="输出可视化组件元数据（用途/必需字段/限制/横竖适配）")
    check = sub.add_parser("check", help="离线校验脚本 JSON（不调用模型、不渲染）")
    check.add_argument("--film", type=Path, required=True, help="Film JSON 路径")
    check.add_argument("--research", type=Path, required=True, help="Research JSON 路径")
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
        if args.command == "probe":
            from .pipeline import settings

            config = settings(root) if (root / "movelyth.toml").is_file() else {}
            agents = (config.get("agents") or {})
            base_url = args.base_url or agents.get("base_url")
            model = args.model or agents.get("model")
            env_name = args.api_key_env or agents.get("api_key_env") or "OPENAI_API_KEY"
            if not base_url or not model:
                raise SystemExit("需要 --base-url 与 --model，或在 movelyth.toml 的 [agents] 中配置")
            result = probe_endpoint(base_url, env_name, model, image=args.image)
            emit(result)
            return 0 if result.get("reachable") and result.get("json_output") else 1
        if args.command == "schema":
            from .models import Film

            emit(Film.model_json_schema())
            return 0
        if args.command == "components":
            from .components import registry

            emit(registry())
            return 0
        if args.command == "check":
            from .models import Film, Research
            from .quality import validate_script
            from .util import read_json

            config = Studio(root).config["studio"]
            film = Film.model_validate(read_json(args.film.resolve()))
            research = Research.model_validate(read_json(args.research.resolve()))
            try:
                warnings = validate_script(film, research, config["long_seconds"], config["short_seconds"])
            except ValueError as exc:
                emit({"passed": False, "errors": str(exc).split("；"), "warnings": []})
                return 1
            emit({"passed": True, "errors": [], "warnings": warnings,
                  "note": "离线契约校验通过；未调用模型、未渲染、未检查声音与观感"})
            return 0
        studio = Studio(root)
        if args.command == "create":
            brief = read_brief(args.brief_file)
            episode = studio.create(args.title, brief=brief, new=args.new)
            print(f"Movelyth · VID-{episode['id']:06d} · {episode['title']}"
                  f"{' · 已附 brief' if brief else ''}", flush=True)
            emit(studio.produce(episode["id"], plan_only=args.plan_only, preview_only=args.preview,
                                import_film=args.import_film.resolve() if args.import_film else None,
                                import_research=args.import_research.resolve() if args.import_research else None))
        elif args.command == "resume":
            emit(studio.produce(args.id, plan_only=args.plan_only, preview_only=args.preview,
                                reuse_script=args.reuse_script))
        elif args.command == "preview":
            emit(studio.preview(args.id))
        elif args.command == "revise":
            notes = args.notes.read_text(encoding="utf-8-sig")
            emit(studio.revise(args.id, notes))
        elif args.command == "status":
            result = studio.ledger.get(args.id) if args.id else studio.ledger.list()
            if args.id:
                result["history"] = studio.ledger.history(args.id)
            emit(result)
        elif args.command == "ideas":
            emit(studio.ledger.context())
        elif args.command == "suggest":
            emit(studio.suggest(count=args.count))
        elif args.command == "daily":
            emit(studio.daily(count=args.count, preview_only=args.preview))
        elif args.command == "assets":
            emit(studio.asset_observations())
        elif args.command == "asset-add":
            from .assets import register

            entry = register(studio.workspace, args.file, asset_id=args.id, source=args.source,
                             author=args.author, license=args.license, scope=args.scope)
            emit({"registered": args.id, **entry,
                  "note": "已复制到 workspace/assets/files；脚本中用 image 图层 data_ref 引用该 id"})
        elif args.command == "asset-check":
            from .assets import check_library

            report = check_library(studio.workspace)
            emit({"assets": report,
                  "invalid": [item["id"] for item in report if item["status"] != "valid"],
                  "note": "失效素材会在渲染前被拒绝，不会静默替换"})
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
