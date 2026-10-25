---
name: movelyth-video
description: Use Movelyth — 幕绎 to produce a narrated Bilibili/Douyin video from a title or a request such as 生成今日份视频, or resume a Movelyth production. Do not launch production for internal JSON-only research, director or reviewer role requests.
---

# Movelyth — 幕绎

Find the project containing `movelyth.toml` and `studio/`: use `MOVELYTH_PROJECT` if set, otherwise the current directory or its `Movelyth/` child. Preserve the user's title. When they say “生成今日份视频”, inspect `ideas` and `status`, then choose a concrete, uncompleted topic with a clear visual question. Compare recent themes and cases; do not merely rename an existing video.

Use the project's Python interpreter (`.venv/Scripts/python.exe` on Windows). Commands below run from the project root; from elsewhere include `--root <project>` before the command.

1. Check `python -m movelyth doctor` if the environment has not been checked in this session.
2. Read `python -m movelyth status` and `python -m movelyth ideas` for history and actual feedback.
3. Run `python -m movelyth create "<title>"`. A title starts the complete chain; no manual script is required. Do not add `--new` unless the user explicitly wants another production of the same title.
4. Keep the user informed while long role calls or rendering run. The task's `render.log`, agent event logs and SQLite events identify the current stage. Do not start a duplicate worker to check progress.
5. On failure, inspect the relevant report/log, fix a demonstrated issue within scope and use `python -m movelyth resume VID-000001`. Valid stages and voice requests are cached. Do not hide errors or switch to a fixture/imported script and claim title-driven automation succeeded.
6. Report the exact `delivery/待上传/VID-.../r.../` path only after status is ready and the manifest verifies. Link the two MP4s, covers and publishing copy. State any untested review limits recorded in `质检报告.json`.

The runtime already uses independent research, director and reviewer contexts. Do not separately delegate or launch additional role processes while it is running. If you are an internal role asked for schema-constrained JSON, return that JSON only; never run this workflow recursively.

Current renderer supports matrix grids, vectors, orthogonal projection, waves, networks, real SVD image reconstruction and rotating 3D point clouds. Use it for compatible visual explainers. If a request needs live action, characters or footage the engine cannot create, explain that concrete gap and extend/select an appropriate route; do not relabel abstract graphs as the requested footage.

Paid visual/music generation is not configured. Edge TTS needs internet; Codex CLI needs a logged-in account and available usage. A missing dependency or service should leave a recoverable failure, never a silent “ready”. User uploads are manual; use `feedback` only for links and metrics the user actually provides. Missing metrics remain unknown.
