"""SQLite owns IDs, active-run exclusion and an append-only event history."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from .util import canonical, fingerprint, now


class BusyError(RuntimeError):
    pass


def alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = wintypes.DWORD()
        result = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(result and code.value == 259)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class Ledger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                intent TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1, delivery TEXT, error TEXT,
                pid INTEGER, token TEXT, UNIQUE(intent, revision)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, episode_id INTEGER NOT NULL, stage TEXT NOT NULL,
                state TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL UNIQUE, state TEXT NOT NULL,
                origin_episode INTEGER, reason TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY, episode_id INTEGER NOT NULL, platform TEXT NOT NULL,
                url TEXT NOT NULL, observed_at TEXT NOT NULL, metrics TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS publications (
                episode_id INTEGER NOT NULL, platform TEXT NOT NULL, url TEXT NOT NULL,
                recorded_at TEXT NOT NULL, PRIMARY KEY(episode_id,platform)
            );
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, source_version TEXT NOT NULL,
                parameters TEXT NOT NULL, credit TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS asset_usage (
                asset_id TEXT NOT NULL, episode_id INTEGER NOT NULL, cut TEXT NOT NULL,
                scene_id TEXT NOT NULL, PRIMARY KEY(episode_id,cut,scene_id)
            );
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(ideas)")}
        if "production_episode" not in columns:
            self.db.execute("ALTER TABLE ideas ADD COLUMN production_episode INTEGER")
            self.db.execute("INSERT OR IGNORE INTO ideas(title,state,production_episode) "
                            "SELECT title,CASE WHEN status='ready' THEN 'completed' ELSE 'selected' END,id FROM episodes")
        self.db.executescript("""
            CREATE TRIGGER IF NOT EXISTS proposed_idea_is_not_a_finished_film
            BEFORE UPDATE OF state ON ideas
            WHEN NEW.state='completed' AND OLD.production_episode IS NULL AND OLD.state='backlog'
            BEGIN SELECT RAISE(IGNORE); END;
        """)
        self.db.execute("UPDATE ideas SET state='completed' WHERE production_episode IN "
                        "(SELECT id FROM episodes WHERE status='ready')")
        self.db.commit()

    def get(self, episode_id: int) -> dict:
        row = self.db.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        if not row:
            raise ValueError(f"未知视频编号：VID-{episode_id:06d}")
        return dict(row)

    def reserve(self, title: str, intent: str, *, new: bool = False) -> dict:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT * FROM episodes WHERE intent=? ORDER BY revision DESC LIMIT 1",
                                  (intent,)).fetchone()
            if row and not new:
                self.db.execute("INSERT OR IGNORE INTO ideas(title,state,production_episode) VALUES (?,?,?)",
                                (row["title"], "completed" if row["status"] == "ready" else "selected", row["id"]))
                self.db.commit()
                return dict(row)
            revision = row["revision"] + 1 if row else 1
            stamp = now()
            cursor = self.db.execute(
                "INSERT INTO episodes(title,intent,created_at,updated_at,revision) VALUES (?,?,?,?,?)",
                (title, intent, stamp, stamp, revision))
            self.db.execute("INSERT OR IGNORE INTO ideas(title,state,production_episode) VALUES (?,'selected',?)",
                            (title, cursor.lastrowid))
            self.db.execute("UPDATE ideas SET state='selected',production_episode=? WHERE title=?",
                            (cursor.lastrowid, title))
            self.db.commit()
            return self.get(cursor.lastrowid)
        except BaseException:
            self.db.rollback()
            raise

    @contextmanager
    def claim(self, episode_id: int):
        token = uuid.uuid4().hex
        self.db.execute("BEGIN IMMEDIATE")
        row = self.get(episode_id)
        if row["token"] and alive(row["pid"] or 0):
            self.db.rollback()
            raise BusyError(f"{episode_id} 正由进程 {row['pid']} 制作，请勿重复运行")
        self.db.execute("UPDATE episodes SET token=?,pid=?,updated_at=? WHERE id=?",
                        (token, os.getpid(), now(), episode_id))
        self.db.commit()
        try:
            yield
        finally:
            self.db.execute("UPDATE episodes SET token=NULL,pid=NULL WHERE id=? AND token=?",
                            (episode_id, token))
            self.db.commit()

    def event(self, episode_id: int, stage: str, state: str, detail=None):
        self.db.execute("INSERT INTO events(episode_id,stage,state,at,detail) VALUES (?,?,?,?,?)",
                        (episode_id, stage, state, now(), canonical(detail or {})))
        self.db.commit()

    def status(self, episode_id: int, status: str, *, error=None, delivery=None):
        self.db.execute("UPDATE episodes SET status=?,error=?,updated_at=?,delivery=COALESCE(?,delivery) WHERE id=?",
                        (status, error, now(), delivery, episode_id))
        if status == "ready":
            self.db.execute("UPDATE ideas SET state='completed' WHERE production_episode=?", (episode_id,))
        self.db.commit()

    def list(self, limit: int = 30) -> list[dict]:
        return [dict(row) for row in self.db.execute("SELECT * FROM episodes ORDER BY id DESC LIMIT ?", (limit,))]

    def history(self, episode_id: int) -> list[dict]:
        return [dict(row) | {"detail": json.loads(row["detail"])} for row in self.db.execute(
            "SELECT * FROM events WHERE episode_id=? ORDER BY id", (episode_id,))]

    def context(self) -> dict:
        ideas = [dict(r) for r in self.db.execute("SELECT * FROM ideas ORDER BY id DESC LIMIT 30")]
        feedback = [dict(r) for r in self.db.execute("SELECT * FROM feedback ORDER BY id DESC LIMIT 20")]
        for row in feedback:
            row["metrics"] = json.loads(row["metrics"])
        publications = [dict(r) for r in self.db.execute("SELECT * FROM publications ORDER BY recorded_at DESC LIMIT 30")]
        failures = [dict(r) | {"detail": json.loads(r["detail"])} for r in self.db.execute(
            "SELECT * FROM events WHERE state='failed' ORDER BY id DESC LIMIT 20")]
        return {"episodes": self.list(20), "ideas": ideas, "feedback": feedback,
                "publications": publications, "failures": failures}

    def add_ideas(self, titles: list[str], origin: int):
        self.db.executemany("INSERT OR IGNORE INTO ideas(title,state,origin_episode) VALUES (?,'backlog',?)",
                            [(t, origin) for t in titles])
        self.db.commit()

    def add_feedback(self, episode_id: int, platform: str, url: str, metrics: dict):
        self.get(episode_id)
        self.db.execute("INSERT INTO feedback(episode_id,platform,url,observed_at,metrics) VALUES (?,?,?,?,?)",
                        (episode_id, platform, url, now(), canonical(metrics)))
        self.db.execute("INSERT INTO publications(episode_id,platform,url,recorded_at) VALUES (?,?,?,?) "
                        "ON CONFLICT(episode_id,platform) DO UPDATE SET url=excluded.url,recorded_at=excluded.recorded_at",
                        (episode_id, platform, url, now()))
        self.db.commit()

    def record_assets(self, episode_id: int, cut: str, scenes: list[dict], version: str):
        for scene in scenes:
            params = {k: scene[k] for k in ["visual", "matrix", "color"]}
            key = fingerprint({"parameters": params, "source_version": version})[:24]
            self.db.execute("INSERT OR IGNORE INTO assets(id,kind,source_version,parameters,credit) VALUES (?,?,?,?,?)",
                            (key, scene["visual"], version, canonical(params), "Movelyth original procedural visuals"))
            self.db.execute("INSERT INTO asset_usage(asset_id,episode_id,cut,scene_id) VALUES (?,?,?,?) "
                            "ON CONFLICT(episode_id,cut,scene_id) DO UPDATE SET asset_id=excluded.asset_id",
                            (key, episode_id, cut, scene["id"]))
        self.db.commit()

    def asset_observations(self) -> list[dict]:
        result = []
        for row in self.db.execute("SELECT * FROM assets ORDER BY kind,id"):
            item = dict(row)
            item["parameters"] = json.loads(item["parameters"])
            item["usage"] = [dict(r) for r in self.db.execute(
                "SELECT episode_id,cut,scene_id FROM asset_usage WHERE asset_id=?", (row["id"],))]
            observations = self.db.execute(
                "SELECT DISTINCT f.* FROM feedback f JOIN asset_usage u ON f.episode_id=u.episode_id "
                "WHERE u.asset_id=? ORDER BY f.observed_at", (row["id"],))
            item["feedback_observations"] = []
            for observation in observations:
                value = dict(observation)
                value["metrics"] = json.loads(value["metrics"])
                item["feedback_observations"].append(value)
            item["popularity"] = "unknown" if not item["feedback_observations"] else "associated-video-data-only"
            result.append(item)
        return result

    def close(self):
        self.db.close()
