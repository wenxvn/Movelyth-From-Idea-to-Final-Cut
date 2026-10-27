---
name: movelyth-video
description: Use Movelyth — 幕绎 to produce a narrated Bilibili/Douyin video from a title or a title plus a brief, preview a storyboard, revise specific scenes, or resume a Movelyth production. Do not launch production for internal JSON-only research, director or reviewer role requests.
---

# Movelyth — 幕绎

Find the project containing `movelyth.toml` and `studio/`: use `MOVELYTH_PROJECT` if set, otherwise the current directory or its `Movelyth/` child. Preserve the user's title and brief wording.

Use the project's Python interpreter (`.venv/Scripts/python.exe` on Windows). Commands below run from the project root; from elsewhere include `--root <project>` before the command.

1. Check `python -m movelyth doctor` if the environment has not been checked in this session. `codex: null` or `ready_for_generation: false` means real model calls will fail — say so instead of pretending to generate.
2. Read `python -m movelyth status` and `python -m movelyth ideas` for history and actual feedback.
3. Build the command from what the user actually gave:
   - title only → `python -m movelyth create "<title>"` (the default entry; no manual script needed).
   - title + background/audience/tone/emphasis → write those paragraphs to a small Markdown file and pass `--brief-file <path>`. Do not turn it into a long questionnaire.
   - explicit second production of the same title → add `--new`.
   - “生成今日份视频” without a title → run `python -m movelyth suggest --count 3` and show the candidates (question, visual plan, capability, risks). If the user accepts, run `python -m movelyth daily --preview` (or without `--preview` for the full cut); it uses the same create pipeline and refuses when every candidate needs capabilities we lack. Never schedule it in the background and never invent playback numbers.
4. For an expensive or unfamiliar topic, run `--preview` first: it renders representative stills plus a 12-second low-resolution clip and a `storyboard.json`, and never enters the delivery folder. Look at the storyboard, then run the full production.
5. Keep the user informed while long role calls or rendering run. The task's `render.log`, agent event logs and SQLite events identify the current stage; `workspace/metrics.csv` records stage seconds and cache hits. A role's `latest.json` points to its most recent attempt. Do not start a duplicate worker to check progress.
6. On failure, inspect the relevant report/log, fix a demonstrated issue within scope and use `python -m movelyth resume VID-000001`. Valid stages and voice requests are cached. Do not hide errors or switch to a fixture/imported script and claim title-driven automation succeeded.
7. When the user wants changes to specific shots, collect their notes verbatim into a file and run `python -m movelyth revise VID-000001 --notes <path>`. Notes must locate shots by "镜头 N" or a scene id; only those scenes are rewritten and a new revision is created.
8. Report the exact `delivery/待上传/VID-.../r.../` path only after status is ready and the manifest verifies. Link the two MP4s, covers and publishing copy. State any untested review limits recorded in `质检报告.json` (for example `asr_checked=false`, `audio_listened=false`, `human_review`). The V3 report also carries `composition` (subject height, empty cells), `rhythm` (caption-page coverage), `sound_design` (event density/sync) and `narrative` (offline craft warnings) — quote their warnings rather than describing a film as "professional".

The runtime already uses independent research, director and reviewer contexts. Do not separately delegate or launch additional role processes while it is running. If you are an internal role asked for schema-constrained JSON, return that JSON only; never run this workflow recursively.

## What the renderer can honestly show

Scene DSL v1 composes layers per shot: `text`, `math`, `shape`, `chart` (line/bar/scatter with real series or a bounded local JSON file, plus data annotations and a highlight range), `diagram` (arbitrary nodes/edges/steps), `image` (controlled local assets only), and `procedural` (matrix grid, vectors, projection, waves, networks, real SVD reconstruction, rotating point cloud). Layouts are `immersive` / `diagram` / `compare`; styles are `minimal` / `tech` / `documentary`. Shots also carry direction fields (`transition`, `camera`, `emphasis`, `cues`, `chapter`, `role`, `takeaway`, `metric`, `hero`); the renderer turns long shots into coverage beats and draws an insight card from real data. Details: `docs/scene-dsl.md`.

If a request needs live action, characters, real footage, or high-fidelity simulation, explain that concrete gap and propose a compatible angle or a future pipeline; do not relabel abstract graphs as the requested footage, and do not call an illustrative chart "measured data".

Paid visual/music generation is not configured. Edge TTS needs internet; Codex CLI needs a logged-in account and available usage. A missing dependency or service should leave a recoverable failure, never a silent “ready”. User uploads are manual; use `feedback` only for links and metrics the user actually provides. Missing metrics remain unknown. Never describe a preview, a mock-provider run, or an imported script as a verified real-model production.
