from __future__ import annotations

import csv
import os
import re
import shutil
import sys
import tomllib
import unicodedata
import uuid
from pathlib import Path

from . import __version__
from .agents import CodexAgents
from .ledger import Ledger
from .media import ffmpeg, image_layers, prepare_cut
from .models import Film, Research, Review
from .quality import contact_sheet, encoded_stills, srt, validate_script, verify_video
from .util import atomic_json, file_hash, fingerprint, now, read_json, run


class VisualReviewError(RuntimeError):
    """Recoverable editorial feedback, distinct from execution/tool failures."""


def settings(root: Path) -> dict:
    return tomllib.loads((root / "movelyth.toml").read_text(encoding="utf-8"))


def intent_key(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    return fingerprint("".join(ch for ch in normalized if ch.isalnum()))


def safe_title(title: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title).strip(" .")[:40] or "未命名"


def browser() -> str | None:
    configured = os.getenv("MOVELYTH_BROWSER")
    if configured:
        if not Path(configured).is_file():
            raise ValueError("MOVELYTH_BROWSER 指向不存在的文件")
        return configured
    candidates = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    return next((p for p in candidates if Path(p).is_file()), None)


def manifest_valid(directory: Path) -> bool:
    try:
        data = read_json(directory / "manifest.json")
        entries = data["files"]
        if not entries or data.get("status") != "ready":
            return False
        for name, digest in entries.items():
            target = (directory / name).resolve()
            if not target.is_relative_to(directory.resolve()) or not target.is_file() or file_hash(target) != digest:
                return False
        return True
    except (OSError, KeyError, ValueError):
        return False


class Studio:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.config = settings(self.root)
        self.workspace = (self.root / self.config["paths"]["workspace"]).resolve()
        self.delivery = (self.root / self.config["paths"]["delivery"]).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.ledger = Ledger(self.workspace / "studio.sqlite")

    def close(self):
        self.ledger.close()

    def create(self, title: str, *, new: bool = False) -> dict:
        title = title.strip()
        if not 2 <= len(title) <= 80:
            raise ValueError("标题须为 2–80 个字符")
        episode = self.ledger.reserve(title, intent_key(title), new=new)
        folder = self.workspace / f"VID-{episode['id']:06d}"
        folder.mkdir(exist_ok=True)
        return episode

    def stage(self, episode: dict, name: str, inputs, action, *, freeze_approved_plan: bool = False):
        job = self.workspace / f"VID-{episode['id']:06d}"
        marker = job / "stages" / f"{name}.json"
        digest = fingerprint({"version": __version__, "inputs": inputs})
        if marker.exists():
            try:
                cached = read_json(marker)
                valid = ((cached["input_hash"] == digest or freeze_approved_plan) and bool(cached["outputs"])
                         and all(Path(p).is_file() and file_hash(Path(p)) == h
                                 for p, h in cached["outputs"].items()))
            except (OSError, ValueError, KeyError, TypeError):
                valid = False
            if valid:
                if freeze_approved_plan and cached["input_hash"] != digest:
                    self.ledger.event(episode["id"], name, "frozen-plan-reused",
                                      {"approved_input_hash": cached["input_hash"], "current_input_hash": digest})
                print(f"[缓存] {name}", flush=True)
                return cached["data"]
        self.ledger.status(episode["id"], name)
        self.ledger.event(episode["id"], name, "running", {"input_hash": digest})
        print(f"[开始] {name}", flush=True)
        try:
            data, outputs = action()
            if not outputs or any(not p.is_file() for p in outputs):
                raise RuntimeError(f"{name} 缺少阶段产物")
            atomic_json(marker, {"input_hash": digest, "outputs": {str(p): file_hash(p) for p in outputs},
                                 "data": data, "finished_at": now()})
            self.ledger.event(episode["id"], name, "passed", {"outputs": len(outputs)})
            print(f"[完成] {name}", flush=True)
            return data
        except BaseException as exc:
            self.ledger.event(episode["id"], name, "failed", {"type": type(exc).__name__, "message": str(exc)})
            raise

    def produce(self, episode_id: int, *, plan_only: bool = False, import_film: Path | None = None,
                import_research: Path | None = None) -> dict:
        episode = self.ledger.get(episode_id)
        if episode["status"] == "ready":
            if episode["delivery"] and manifest_valid(Path(episode["delivery"])):
                self.export_index()
                return {"id": episode_id, "status": "ready", "delivery": episode["delivery"], "reused": True}
            raise RuntimeError("已交付文件缺失或发生变化，未覆盖它；请检查目录或用 --new 创建新任务")
        if import_film and not import_research:
            raise ValueError("导入脚本时同时需要 --import-research，不能省略来源")
        job = self.workspace / f"VID-{episode_id:06d}"
        with self.ledger.claim(episode_id):
            try:
                for repair in range(self.config["studio"]["max_retries"] + 1):
                    try:
                        return self._produce(episode, job, plan_only, import_film, import_research)
                    except VisualReviewError:
                        if import_film or repair == self.config["studio"]["max_retries"]:
                            raise
                        print("[修复] 将实际抽帧反馈交给编导，重建受影响的下游阶段", flush=True)
                raise RuntimeError("制作未返回结果")
            except BaseException as exc:
                self.ledger.status(episode_id, "failed", error=f"{type(exc).__name__}: {exc}")
                raise

    def _produce(self, episode, job, plan_only, import_film, import_research):
        config = self.config["studio"]
        agents = CodexAgents(self.root, self.config["agents"])
        common = {"title": episode["title"], "long_seconds": config["long_seconds"],
                  "short_seconds": config["short_seconds"], "history": self.ledger.context(),
                  "renderer_capabilities": {"matrix": "单位网格/房子轮廓/单位正方形在4秒内线性变换到指定矩阵，显示实际行列式；不连续复合上一镜头的矩阵",
                    "vectors": "两个坐标方向分量与随时间变化的线性组合", "projection": "动态向量、指定方向上的正交投影和虚线残差",
                    "wave": "确定性谐波叠加示意", "network": "节点连接与信号流动示意，非实验数据",
                    "image_layers": "自身程序生成山水图，逐通道真实SVD的1/4/12/32阶重建",
                    "orbit": "旋转矩阵变换的三维结点云，非物理模拟"}}
        prompts = {p.name: file_hash(p) for p in Path(__file__).with_name("prompts").glob("*.md")}
        feedback_file = job / "visual-feedback.json"
        visual_feedback = read_json(feedback_file) if feedback_file.exists() else None

        def research_action():
            value = Research.model_validate(read_json(import_research)) if import_research else agents.call(
                "research", common, Research, job / "agents" / "research")
            path = job / "research.json"
            atomic_json(path, value.model_dump())
            return value.model_dump(), [path]

        research_data = self.stage(episode, "research", {"title": episode["title"], "prompts": prompts,
                                   "provider": self.config["agents"],
                                   "import": file_hash(import_research) if import_research else None}, research_action,
                                   freeze_approved_plan=not import_research)
        research = Research.model_validate(research_data)
        self.ledger.add_ideas(research.next_ideas, episode["id"])

        def script_action():
            issues = visual_feedback["issues"] if visual_feedback else []
            for attempt in range(config["max_retries"] + 1):
                if import_film:
                    film = Film.model_validate(read_json(import_film))
                else:
                    film = agents.call("director", {**common, "research": research_data, "review_issues": issues},
                                       Film, job / "agents" / f"director-{attempt}")
                film.title = episode["title"]
                try:
                    validate_script(film, research, config["long_seconds"], config["short_seconds"])
                except ValueError as exc:
                    issues = [str(exc)]
                    if import_film or attempt == config["max_retries"]:
                        raise
                    continue
                review = agents.call("reviewer", {"stage": "script", **common, "research": research_data,
                                      "film": film.model_dump()}, Review, job / "agents" / f"script-review-{attempt}")
                if review.passed and not review.issues:
                    path, report = job / "film.json", job / "script-review.json"
                    atomic_json(path, film.model_dump())
                    atomic_json(report, review.model_dump())
                    return film.model_dump(), [path, report]
                issues = review.issues or ["审片未通过，需重写"]
                if import_film:
                    break
            raise RuntimeError("脚本审片未通过：" + "；".join(issues))

        film = self.stage(episode, "script", {"research": research_data, "prompts": prompts,
                          "targets": [config["long_seconds"], config["short_seconds"]],
                          **({"visual_feedback": visual_feedback} if visual_feedback else {}),
                          "provider": self.config["agents"], "import": file_hash(import_film) if import_film else None}, script_action,
                          freeze_approved_plan=not visual_feedback and not import_film)
        film = Film.model_validate(film).model_dump()
        validate_script(Film.model_validate(film), research, config["long_seconds"], config["short_seconds"])
        if plan_only:
            self.ledger.status(episode["id"], "planned")
            return {"id": episode["id"], "status": "planned", "script": str(job / "film.json")}

        def sound_action():
            data, paths = {}, []
            for name in ["long", "short"]:
                data[name], generated = prepare_cut(film[name], config, self.workspace / "voice-cache",
                                                     job / "audio" / name, portrait=name == "short")
                target = config["long_seconds" if name == "long" else "short_seconds"]
                if not target * 0.55 <= data[name]["seconds"] <= target * 1.55:
                    raise RuntimeError(f"{name} 实际旁白时长 {data[name]['seconds']:.1f}s 偏离目标 {target}s")
                paths.extend(generated)
            out = job / "timelines.json"
            atomic_json(out, data)
            return data, list(set(paths + [out]))

        timelines = self.stage(episode, "sound", {"implementation": file_hash(Path(__file__).with_name("media.py")),
                               "film": film, "voice": {k: config[k] for k in
                               ["voice", "voice_rate", "fps", "max_retries"]}}, sound_action)

        def assets_action():
            names, paths, metrics = image_layers(job / "assets")
            return {"layers": names, "metrics": metrics}, paths

        assets = self.stage(episode, "assets", {"algorithm": "procedural-landscape-rgb-svd-v1"}, assets_action)
        studio_files = list((self.root / "studio" / "src").glob("*")) + [self.root / "studio" / "render.mjs",
                                                                 self.root / "studio" / "package-lock.json"]
        renderer_version = fingerprint({p.name: file_hash(p) for p in studio_files if p.is_file()})

        def render_action():
            cuts = []
            for name, composition in [("long", "Landscape"), ("short", "Portrait")]:
                props = {"title": film[name]["title"], "episode": f"VID-{episode['id']:06d}",
                         "fps": config["fps"], "scenes": timelines[name]["scenes"],
                         "sources": research_data["sources"], "layers": assets["layers"], "cover": False}
                cuts.append({"name": name, "composition": composition, "props": props,
                             "output": str(job / "renders" / name)})
            result = job / "render-result.json"
            spec = job / "render-spec.json"
            atomic_json(spec, {"cuts": cuts, "assets": str(job / "assets"), "browser": browser(),
                               "concurrency": config["render_concurrency"], "result": str(result),
                               "version": renderer_version})
            for cut in cuts:
                self.ledger.record_assets(episode["id"], cut["name"], cut["props"]["scenes"], renderer_version)
            run([shutil.which("node") or "node", str(self.root / "studio" / "render.mjs"), str(spec)],
                cwd=self.root / "studio", timeout=7200, log=job / "render.log")
            data = read_json(result)
            outputs = [spec, result]
            for cut in data.values():
                outputs.extend(Path(p) for p in [cut["video"], cut["cover"], *cut["stills"]])
            return data, outputs

        renders = self.stage(episode, "render", {"timelines": timelines, "assets": assets,
                             "renderer": renderer_version, "concurrency": config["render_concurrency"]}, render_action)

        def check_action():
            reports, outputs, images = {}, [], []
            for name in ["long", "short"]:
                video = job / "renders" / name / "final.mp4"
                run([ffmpeg(), "-y", "-v", "error", "-i", renders[name]["video"], "-i", timelines[name]["mix"],
                     "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-2:LRA=11",
                     "-ar", "48000", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(video)],
                    timeout=600, log=job / f"mux-{name}.log")
                metadata = renders[name]
                reports[name] = verify_video(video, width=metadata["width"], height=metadata["height"],
                                              fps=config["fps"], seconds=timelines[name]["seconds"])
                if not reports[name]["passed"]:
                    atomic_json(job / "quality-failed.json", reports)
                    raise RuntimeError(f"{name} 成片检查未通过：{reports[name]['checks']}")
                image = job / f"contact-{name}.jpg"
                actual_stills = encoded_stills(video, timelines[name], config["fps"], job / "encoded-stills" / name,
                                               portrait=name == "short")
                contact_sheet(actual_stills, image, portrait=name == "short")
                images.append(image)
                outputs.extend([video, image])
                outputs.extend(Path(p) for p in actual_stills)
            from .sources import collect_sources

            evidence = collect_sources(research_data["sources"], job / "source-evidence")
            visual = agents.call("reviewer", {"stage": "visual", "film": film, "research": research_data,
                                  "source_evidence": evidence, "technical_reports": reports,
                                  "image_order": ["long contact sheet", "short contact sheet"]},
                                 Review, job / "agents" / "visual-review", images=images)
            atomic_json(job / "visual-review.json", visual.model_dump())
            if not visual.passed or visual.issues:
                atomic_json(feedback_file, {"issues": visual.issues, "at": now(),
                                           "prior_film_hash": fingerprint(film)})
                raise VisualReviewError("实际画面审片未通过：" + "；".join(visual.issues))
            report = job / "quality.json"
            atomic_json(report, {"technical": reports, "script_review": read_json(job / "script-review.json"),
                                 "visual_review": visual.model_dump(), "checked_at": now(),
                                 "source_fetches": [{k: source[k] for k in ["url", "status", "content_sha256"] if k in source}
                                                    for source in evidence],
                                 "creation_mode": "imported-script" if import_film else "title-driven-codex-agents"})
            return read_json(report), outputs + [report, job / "visual-review.json"]

        self.stage(episode, "check", {"implementation": file_hash(Path(__file__).with_name("quality.py")),
                   "renders": renders, "timelines": timelines, "review_prompt": prompts["reviewer.md"]}, check_action)
        return self.deliver(episode, job, film, research_data, timelines)

    def deliver(self, episode, job, film, research, timelines):
        name = f"VID-{episode['id']:06d}_{safe_title(episode['title'])}"
        destination = self.delivery / "待上传" / name / f"r{episode['revision']:03d}"
        if destination.exists():
            if not manifest_valid(destination):
                raise RuntimeError(f"交付目标已存在且未通过校验，保留原文件：{destination}")
        else:
            staging = self.delivery / ".staging" / name / f"r{episode['revision']:03d}"
            staging.mkdir(parents=True, exist_ok=True)
            code = f"VID-{episode['id']:06d}"
            for cut, platform in [("long", "B站_横版"), ("short", "抖音_竖版")]:
                shutil.copy2(job / "renders" / cut / "final.mp4", staging / f"{code}_{platform}.mp4")
                shutil.copy2(job / "renders" / cut / "cover.png", staging / f"封面_{platform}.png")
                (staging / f"字幕_{platform}.srt").write_text(srt(timelines[cut], self.config["studio"]["fps"]), encoding="utf-8")
            shutil.copy2(job / "quality.json", staging / "质检报告.json")
            shutil.copy2(job / "film.json", staging / "脚本.json")
            shutil.copy2(job / "research.json", staging / "研究记录.json")
            atomic_json(staging / "制作溯源.json", {"engine_version": __version__, "python": sys.version.split()[0],
                         "settings": self.config, "render_source_hash": read_json(job / "render-spec.json")["version"],
                         "render_fingerprints": {k: v["fingerprint"] for k, v in read_json(job / "render-result.json").items()},
                         "source_checks": "AI research and independent script review; not human-certified",
                         "script_hash": file_hash(job / "film.json"), "research_hash": file_hash(job / "research.json")})
            copy = []
            for cut, platform in [("long", "B站"), ("short", "抖音")]:
                copy.extend([f"## {platform}\n", film[cut]["title"], "", film[cut]["description"], "",
                             " ".join("#" + tag.lstrip("#") for tag in film[cut]["tags"]), ""])
            source_lines = [f"- [{s['label']}]({s['url']})：{s['supports']}" for s in research["sources"]]
            credits = "\n".join(source_lines) + "\n\n画面：Movelyth 程序动画；山水图像为程序绘制，低秩重建由 NumPy SVD 计算。\n配乐和音效：Movelyth 原创程序合成。旁白：Edge TTS。\n制作：Movelyth — 幕绎 / Remotion。来源链接不代表取得第三方素材转载许可；本片未直接使用外部图像/视频。\n"
            (staging / "素材来源与署名.md").write_text(credits, encoding="utf-8")
            (staging / "发布文案.md").write_text("\n".join(copy) + "\n## 来源与署名\n" + credits, encoding="utf-8")
            files = {p.name: file_hash(p) for p in staging.iterdir() if p.is_file() and p.name != "manifest.json"}
            atomic_json(staging / "manifest.json", {"id": code, "title": episode["title"], "revision": episode["revision"],
                         "status": "ready", "published": False, "created_at": now(), "files": files,
                         "version": __version__, "durations": {k: v["seconds"] for k, v in timelines.items()}})
            if not manifest_valid(staging):
                raise RuntimeError("交付暂存目录 hash 检查未通过")
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging.rename(destination)
        self.ledger.status(episode["id"], "ready", delivery=str(destination))
        self.ledger.event(episode["id"], "delivery", "passed", {"path": str(destination)})
        self.export_index()
        return {"id": episode["id"], "status": "ready", "delivery": str(destination), "reused": False}

    def export_index(self):
        self.delivery.mkdir(parents=True, exist_ok=True)
        path = self.delivery / "交付清单.csv"
        temp = path.with_name(f".delivery-index-{uuid.uuid4().hex}.tmp")
        published = {(r["episode_id"], r["platform"]): r["url"] for r in
                     self.ledger.db.execute("SELECT episode_id,platform,url FROM publications")}
        with temp.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["编号", "标题", "制作状态", "版本", "交付目录", "更新时间", "B站发布链接", "抖音发布链接"])
            for row in reversed(self.ledger.list(10000)):
                writer.writerow([f"VID-{row['id']:06d}", row["title"], row["status"], row["revision"],
                                 row["delivery"] or "", row["updated_at"], published.get((row["id"], "bilibili"), ""),
                                 published.get((row["id"], "douyin"), "")])
        os.replace(temp, path)

    def asset_observations(self):
        # Reconstruct the index from actual render specs, including earlier/interrupted runs.
        for episode in self.ledger.list(10000):
            spec = self.workspace / f"VID-{episode['id']:06d}" / "render-spec.json"
            if spec.is_file():
                data = read_json(spec)
                for cut in data["cuts"]:
                    self.ledger.record_assets(episode["id"], cut["name"], cut["props"]["scenes"], data["version"])
        return self.ledger.asset_observations()
